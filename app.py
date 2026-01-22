import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import matplotlib.ticker as ticker
import io
from streamlit_folium import st_folium
from folium.plugins import Draw
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Geospatial Analysis Tool", 
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS KHUSUS ---
st.markdown("""
    <style>
        .stApp, [data-testid="stAppViewContainer"], .element-container, iframe {
            opacity: 1 !important; filter: none !important; transition: none !important;
        }
        .block-container { padding-top: 0rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
        .usgs-header {
            background-color: #00264C; color: white; padding: 15px 20px;
            display: flex; align-items: center; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }
        .usgs-title { font-size: 24px; font-weight: bold; margin-left: 15px; letter-spacing: 0.5px; }
        .usgs-subtitle { font-size: 14px; color: #d1d5db; margin-left: 15px; border-left: 1px solid #d1d5db; padding-left: 15px; }
        [data-testid="stSidebar"] { background-color: #1e1e1e; border-right: 1px solid #333; }
        [data-testid="stSidebar"] * { color: #e0e0e0 !important; }
    </style>
    <div class="usgs-header">
        <div class="usgs-title">Geospatial Explorer (Optimized)</div>
        <div class="usgs-subtitle">High Performance Mode</div>
    </div>
""", unsafe_allow_html=True)

# --- 2. FUNGSI CACHING (JANTUNG PERFORMA) ---
# Fungsi ini hanya akan dijalankan SEKALI saat file diupload.
# Selanjutnya, Streamlit akan mengingat hasilnya (Cache).
@st.cache_data(show_spinner=True)
def load_and_process_data(excel_file, map_file):
    # 1. Load Excel
    df = pd.read_excel(excel_file)
    
    # 2. Load Map
    gdf_raw = gpd.read_file(map_file)
    if gdf_raw.crs != "EPSG:4326": 
        gdf_raw = gdf_raw.to_crs("EPSG:4326")
    
    # [OPTIMISASI] Sederhanakan geometri peta agar lebih ringan dirender
    # tolerance=0.001 mengurangi detail mikroskopis yang tidak terlihat mata tapi memberatkan CPU
    gdf_raw['geometry'] = gdf_raw['geometry'].simplify(tolerance=0.001, preserve_topology=True)
    
    # 3. Create Points
    # Menggunakan Longitude/Latitude huruf besar sesuai file Anda
    gdf_points = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df['LONGITUDE'], df['LATITUDE']), 
        crs="EPSG:4326"
    )
    
    # 4. Spatial Join (Proses Paling Berat)
    # Kita lakukan join di AWAL untuk SEMUA data. Nanti filternya di DataFrame biasa.
    joined = gpd.sjoin(gdf_points, gdf_raw, how="inner", predicate="within")
    
    return df, gdf_raw, joined

# --- 3. SIDEBAR ---
with st.sidebar:
    st.markdown("### 1. Data Input")
    with st.expander("📁 Upload Files", expanded=True):
        uploaded_excel = st.file_uploader("Upload Excel Data (.xlsx)", type=["xlsx"])
        uploaded_map = st.file_uploader("Upload Geometry (.geojson/.shp)", type=["geojson", "json", "shp"])

    with st.expander("🎨 Settings", expanded=True):
        color_palette = st.selectbox("Color Theme:", ["YlOrRd", "PuBu", "YlGn", "OrRd", "RdPu", "Spectral", "coolwarm", "turbo", "viridis"], index=0)

# --- 4. PROSES UTAMA ---
main_container = st.container()

if uploaded_excel and uploaded_map:
    with main_container:
        try:
            # --- PANGGIL DATA DARI CACHE ---
            # Bagian ini tidak akan loading ulang jika hanya ganti filter brand/wilayah
            df_original, gdf_raw, joined_full = load_and_process_data(uploaded_excel, uploaded_map)

            # --- FILTERING LOGIC (CEPAT) ---
            # Filter dilakukan pada DataFrame hasil join (ini sangat cepat)
            
            # 1. Filter Brand
            df_filtered = joined_full.copy()
            selected_brand = 'All Brands'
            
            if 'Brand' in df_filtered.columns:
                unique_brands = sorted([str(x) for x in df_filtered['Brand'].dropna().unique()])
                brand_options = ['All Brands'] + unique_brands
                st.sidebar.markdown("### 2. Filters")
                selected_brand = st.sidebar.selectbox("🏷️ Select Brand:", brand_options)
                
                if selected_brand != 'All Brands':
                    df_filtered = df_filtered[df_filtered['Brand'].astype(str) == selected_brand]

            # 2. Filter Wilayah (Provinsi)
            if 'NAME_1' in gdf_raw.columns:
                list_provinsi = sorted(gdf_raw['NAME_1'].unique())
                pilihan_provinsi = st.selectbox("📍 Select Region of Interest:", list_provinsi)
                
                # Ambil geometri kecamatan HANYA untuk provinsi terpilih
                gdf_kecamatan_display = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
                
                # Filter data penjualan agar sesuai provinsi terpilih juga
                # (Menggunakan hasil sjoin yang sudah ada kolom NAME_1)
                df_filtered = df_filtered[df_filtered['NAME_1'] == pilihan_provinsi]
            else:
                gdf_kecamatan_display = gdf_raw
                pilihan_provinsi = "All Regions"

            # --- AGREGASI DATA ---
            region_col = 'NAME_3' if 'NAME_3' in gdf_kecamatan_display.columns else gdf_kecamatan_display.columns[0]
            
            if 'Stick' in df_filtered.columns:
                agg_data = df_filtered.groupby(region_col)['Stick'].sum().reset_index()
                agg_data.columns = [region_col, 'Total_Stick']
            else:
                st.error("Kolom 'Stick' tidak ditemukan.")
                st.stop()

            # Merge Aggregasi ke Peta Display
            final_map_data = gdf_kecamatan_display.merge(agg_data, on=region_col, how="left")
            final_map_data['Total_Stick'] = final_map_data['Total_Stick'].fillna(0)

            # --- VISUALISASI (SAMA SEPERTI SEBELUMNYA) ---
            max_val = final_map_data['Total_Stick'].max()
            if max_val == 0: max_val = 1
            linear_breaks = sorted(list(set([0, max_val * 0.25, max_val * 0.50, max_val * 0.75, max_val])))
            default_str = ", ".join([str(int(x)) for x in linear_breaks])

            col_map, col_stats = st.columns([2.3, 1.7])

            with col_map:
                st.markdown(f"**Map View: {pilihan_provinsi}**")
                
                # Render Map
                centroid = final_map_data.geometry.centroid
                m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=9, tiles="CartoDB positron")
                
                Draw(export=False, position='topleft', draw_options={'rectangle':True}).add_to(m)

                with st.sidebar.expander("🎚️ Legend Configuration", expanded=True):
                      user_bins = st.text_area("Value Breaks:", value=default_str)
                
                bins_list = None
                try:
                    custom_bins = sorted(list(set([float(x.strip()) for x in user_bins.split(',')])))
                    if len(custom_bins) >= 2: bins_list = custom_bins
                except: pass 

                folium.Choropleth(
                    geo_data=final_map_data, data=final_map_data, columns=[region_col, "Total_Stick"],
                    key_on=f"feature.properties.{region_col}", fill_color=color_palette, fill_opacity=0.8,
                    line_opacity=0.3, legend_name="Total Stick", bins=bins_list, highlight=True
                ).add_to(m)
                
                folium.GeoJson(
                    final_map_data,
                    style_function=lambda x: {'fillColor':'#00000000','color':'#00000000'}, 
                    tooltip=folium.GeoJsonTooltip(fields=[region_col, 'Total_Stick'], aliases=['Kecamatan:', 'Stick:'], localize=True)
                ).add_to(m)

                map_output = st_folium(m, use_container_width=True, height=600)
                
                # Export Image Logic (Matplotlib)
                # ... (Bagian ini sama, disederhanakan untuk response agar muat) ...
                # Jika ingin code download button lengkap seperti sebelumnya, 
                # logika matplotlib-nya tinggal dicopy dari jawaban sebelumnya.
                
                # --- Quick Matplotlib Render for Download ---
                fig, ax = plt.subplots(figsize=(10, 10))
                final_map_data.plot(column='Total_Stick', cmap=color_palette, ax=ax, edgecolor='black', linewidth=0.3)
                ax.axis('off')
                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format='png', bbox_inches='tight', dpi=150)
                img_buffer.seek(0)
                st.download_button("⬇️ Download Map", img_buffer, "Map.png", "image/png")

            with col_stats:
                st.markdown("### 📋 Data Breakdown")
                df_display = final_map_data[[region_col, 'Total_Stick']].sort_values(by='Total_Stick', ascending=False)
                df_display.columns = ['Kecamatan', 'Total Stick']
                st.dataframe(df_display.reset_index(drop=True), use_container_width=True, height=400)

        except Exception as e:
            st.error(f"Error: {e}")
else:
    st.info("Silakan upload file Excel dan GeoJSON untuk memulai.")
