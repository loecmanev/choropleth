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

# --- 2. INJECT CSS KHUSUS ---
st.markdown("""
    <style>
        .stApp, [data-testid="stAppViewContainer"], .element-container, iframe {
            opacity: 1 !important; filter: none !important; transition: none !important;
        }
        .block-container { padding-top: 0rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
        
        /* USGS Header Style */
        .usgs-header {
            background-color: #00264C; color: white; padding: 15px 20px;
            display: flex; align-items: center; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }
        .usgs-title { font-size: 24px; font-weight: bold; margin-left: 15px; letter-spacing: 0.5px; }
        .usgs-subtitle { font-size: 14px; color: #d1d5db; margin-left: 15px; border-left: 1px solid #d1d5db; padding-left: 15px; }
        
        [data-testid="stSidebar"] { background-color: #1e1e1e; border-right: 1px solid #333; }
        [data-testid="stSidebar"] * { color: #e0e0e0 !important; }
        .streamlit-expanderHeader { background-color: #2d2d2d !important; color: white !important; }
    </style>
    
    <div class="usgs-header">
        <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="2" y1="12" x2="22" y2="12"></line>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
        </svg>
        <div class="usgs-title">Geospatial Explorer</div>
        <div class="usgs-subtitle">Data Visualization Interface</div>
    </div>
""", unsafe_allow_html=True)

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
            # --- READ DATA ---
            df = pd.read_excel(uploaded_excel)
            gdf_raw = gpd.read_file(uploaded_map)
            
            # Standardize CRS
            if gdf_raw.crs != "EPSG:4326": gdf_raw = gdf_raw.to_crs("EPSG:4326")

            # --- [BARU] FILTER BRAND ---
            # Cek apakah kolom Brand ada
            if 'Brand' in df.columns:
                # Ambil list unik brand, hilangkan nilai kosong, urutkan
                unique_brands = sorted([str(x) for x in df['Brand'].dropna().unique()])
                # Tambahkan opsi 'All Brands' di paling atas
                brand_options = ['All Brands'] + unique_brands
                
                # Tampilkan Dropdown di Sidebar
                st.sidebar.markdown("### 2. Filters")
                selected_brand = st.sidebar.selectbox("🏷️ Select Brand:", brand_options)
                
                # Filter Dataframe Excel SEBELUM proses mapping
                if selected_brand != 'All Brands':
                    df = df[df['Brand'].astype(str) == selected_brand]
                    st.toast(f"Menampilkan data untuk Brand: {selected_brand}", icon="✅")
            else:
                st.sidebar.warning("Kolom 'Brand' tidak ditemukan di Excel.")

            # --- FILTER WILAYAH (GEOMETRY) ---
            if 'NAME_1' in gdf_raw.columns:
                list_provinsi = sorted(gdf_raw['NAME_1'].unique())
                pilihan_provinsi = st.selectbox("📍 Select Region of Interest:", list_provinsi)
                gdf_kecamatan = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
            else:
                gdf_kecamatan = gdf_raw
                pilihan_provinsi = "All Regions"

            # --- BUAT GEODATAFRAME DARI EXCEL ---
            # Menggunakan header 'LATITUDE' & 'LONGITUDE' (Huruf Besar Sesuai Excel Anda)
            gdf_points = gpd.GeoDataFrame(
                df, 
                geometry=gpd.points_from_xy(df['LONGITUDE'], df['LATITUDE']), 
                crs="EPSG:4326"
            )
            
            # --- SPATIAL JOIN ---
            # Menggabungkan titik penjualan dengan peta wilayah
            joined = gpd.sjoin(gdf_points, gdf_kecamatan, how="inner", predicate="within")

            # Tentukan kolom nama kecamatan (biasanya NAME_3 untuk level kecamatan di GADM)
            region_col = 'NAME_3' if 'NAME_3' in gdf_kecamatan.columns else st.selectbox("Select Region Column:", gdf_kecamatan.columns)
            
            # --- AGREGASI DATA (SUM STICK) ---
            # Menjumlahkan kolom 'Stick' berdasarkan wilayah
            if 'Stick' in joined.columns:
                agg_data = joined.groupby(region_col)['Stick'].sum().reset_index()
                agg_data.columns = [region_col, 'Total_Stick']
            else:
                st.error("Kolom 'Stick' tidak ditemukan. Pastikan nama kolom di Excel adalah 'Stick'.")
                st.stop()

            # Gabungkan hasil hitungan kembali ke peta wilayah
            final_map_data = gdf_kecamatan.merge(agg_data, on=region_col, how="left")
            final_map_data['Total_Stick'] = final_map_data['Total_Stick'].fillna(0)

            # --- LOGIKA WARNA (BINS) ---
            max_val = final_map_data['Total_Stick'].max()
            if max_val == 0: max_val = 1
                
            linear_breaks = sorted(list(set([0, max_val * 0.25, max_val * 0.50, max_val * 0.75, max_val])))
            default_str = ", ".join([str(int(x)) for x in linear_breaks])

            # --- LAYOUT DASHBOARD ---
            col_map, col_stats = st.columns([2.3, 1.7])

            # ==========================
            # PANEL KIRI: PETA
            # ==========================
            with col_map:
                st.markdown(f"**Map View: {pilihan_provinsi}**")
                if 'Brand' in df.columns and selected_brand != 'All Brands':
                    st.caption(f"Filter: {selected_brand}")
                
                # Siapkan peta dasar
                centroid = final_map_data.geometry.centroid
                m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=9, tiles="CartoDB positron", zoom_snap=0.1, zoom_delta=0.1)
                
                # Tambahkan alat gambar
                draw = Draw(export=False, position='topleft', draw_options={'polyline':False,'polygon':False,'circle':False,'marker':False,'circlemarker':False,'rectangle':True})
                draw.add_to(m)

                # Legend Setting
                with st.sidebar.expander("🎚️ Legend Configuration", expanded=True):
                      user_bins = st.text_area("Value Breaks:", value=default_str)
                
                bins_list = None
                try:
                    custom_bins = sorted(list(set([float(x.strip()) for x in user_bins.split(',')])))
                    if custom_bins[0] > 0: custom_bins.insert(0, 0)
                    if custom_bins[-1] < max_val: custom_bins.append(max_val)
                    if len(custom_bins) >= 2: bins_list = custom_bins
                except: pass 

                # Layer Choropleth
                folium.Choropleth(
                    geo_data=final_map_data, data=final_map_data, columns=[region_col, "Total_Stick"],
                    key_on=f"feature.properties.{region_col}", fill_color=color_palette, fill_opacity=0.8,
                    line_opacity=0.3, legend_name="Total Penjualan (Stick)", bins=bins_list, highlight=True
                ).add_to(m)
                
                # Tooltip interaktif
                folium.GeoJson(
                    final_map_data, 
                    style_function=lambda x: {'fillColor':'#00000000','color':'#00000000'}, 
                    tooltip=folium.GeoJsonTooltip(fields=[region_col, 'Total_Stick'], aliases=['Kecamatan:', 'Total Stick:'], localize=True)
                ).add_to(m)

                map_output = st_folium(m, use_container_width=True, height=600)
                
                # --- DOWNLOAD MAP (Matplotlib) ---
                st.caption("Peta siap diunduh")
                
                # Dapatkan batas peta (bounds)
                minx, miny, maxx, maxy = final_map_data.total_bounds
                west, south, east, north = minx, miny, maxx, maxy
                if map_output['all_drawings']:
                    coords = map_output['all_drawings'][-1]['geometry']['coordinates'][0]
                    lons, lats = [c[0] for c in coords], [c[1] for c in coords]
                    west, east, south, north = min(lons), max(lons), min(lats), max(lats)
                elif map_output['bounds']:
                    b = map_output['bounds']
                    south, north = b['_southWest']['lat'], b['_northEast']['lat']
                    west, east = b['_southWest']['lng'], b['_northEast']['lng']

                # Render Matplotlib
                fig, ax = plt.subplots(figsize=(10, 10))
                cmap_base = plt.get_cmap(color_palette)
                norm = mcolors.BoundaryNorm(bins_list, cmap_base.N) if bins_list else mcolors.Normalize(vmin=0, vmax=max_val)
                
                final_map_data.plot(column='Total_Stick', cmap=cmap_base, norm=norm, ax=ax, edgecolor='black', linewidth=0.5)
                ax.set_xlim(west, east); ax.set_ylim(south, north); ax.set_axis_off()

                cax = inset_axes(ax, width="100%", height="100%", loc='upper center', bbox_to_anchor=(0.2, -0.25, 0.6, 0.05), bbox_transform=ax.transAxes, borderpad=0)
                cb = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap_base), cax=cax, orientation='horizontal', spacing='uniform')
                cb.ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
                cb.set_label(f'Total Penjualan (Stick) - {selected_brand if "Brand" in df.columns else ""}', size=10, weight='bold', labelpad=10)
                cb.ax.xaxis.set_ticks_position('bottom')
                cb.ax.tick_params(labelsize=8)

                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format='png', transparent=True, bbox_inches='tight', dpi=300, pad_inches=0.2)
                img_buffer.seek(0)
                plt.close(fig)
                
                st.download_button(
                    label="⬇️ Download Map (PNG)", 
                    data=img_buffer, 
                    file_name=f"Map_Export_{selected_brand if 'Brand' in df.columns else 'All'}.png", 
                    mime="image/png", 
                    key="dl_map_direct"
                )

            # ==========================
            # PANEL KANAN: TABEL
            # ==========================
            with col_stats:
                st.markdown("### 📋 Data Breakdown")
                
                # Siapkan tabel display
                df_display = final_map_data[[region_col, 'Total_Stick']].copy()
                df_display = df_display.sort_values(by='Total_Stick', ascending=False).reset_index(drop=True)
                df_display.columns = ['Kecamatan', 'Total Stick']
                df_display.index = df_display.index + 1
                
                st.dataframe(
                    df_display, 
                    use_container_width=True, 
                    height=400,
                    column_config={"Total Stick": st.column_config.NumberColumn(format="%d")}
                )
                
                st.markdown("---")
                st.markdown("### 📸 Export Table (Top 10)")
                
                # Render Gambar Tabel
                df_export = df_display.head(10).reset_index() 
                df_export.columns = ['No', 'Kecamatan', 'Total Stick'] 
                
                rows = len(df_export)
                h = min(max(rows * 0.5 + 1.2, 3), 10) 
                
                fig_tbl, ax_tbl = plt.subplots(figsize=(6, h))
                ax_tbl.axis('tight'); ax_tbl.axis('off')
                
                cell_text = []
                for row in df_export.values:
                    no, kec, val = row
                    cell_text.append([int(no), kec, f"{val:,.0f}"])
                
                col_widths = [0.1, 0.5, 0.4] 

                table_obj = ax_tbl.table(
                    cellText=cell_text, 
                    colLabels=df_export.columns, 
                    colWidths=col_widths,
                    loc='center', cellLoc='left', 
                    colColours=['#00264C', '#00264C', '#00264C']
                )
                
                table_obj.auto_set_font_size(False)
                table_obj.set_fontsize(11)
                table_obj.scale(1.2, 2)
                
                for (row, col), cell in table_obj.get_celld().items():
                    if row == 0:
                        cell.set_text_props(color='white', weight='bold')
                        cell.set_linewidth(0)
                    else:
                        cell.set_linewidth(0.5)
                        cell.set_edgecolor("#d1d5db")
                        if col == 0: cell.set_text_props(ha='center')
                
                plt.title(f"Top 10 Wilayah - {pilihan_provinsi}\n({selected_brand if 'Brand' in df.columns else 'All Brands'})", y=1.0, pad=2, fontsize=12, fontweight='bold', color='#333')
                
                buf_tbl = io.BytesIO()
                plt.savefig(buf_tbl, format='png', bbox_inches='tight', dpi=200, transparent=False)
                buf_tbl.seek(0)
                plt.close(fig_tbl)
                
                st.download_button(
                    label="⬇️ Download Top 10 Table (PNG)",
                    data=buf_tbl,
                    file_name="Top10_Table.png",
                    mime="image/png",
                    key="dl_table_direct"
                )
        except Exception as e:
            st.error(f"Error Detail: {e}")
else:
    st.markdown("<div style='text-align: center; padding: 50px; color: #666;'><h2>No Data Loaded</h2></div>", unsafe_allow_html=True)
