import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import io
from streamlit_folium import st_folium
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="Geospatial Analysis Tool", 
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. INJECT CSS KHUSUS (USGS STYLE + DARK SIDEBAR) ---
st.markdown("""
    <style>
        /* 1. Menghilangkan Padding Bawaan Streamlit supaya Header nempel atas */
        .block-container {
            padding-top: 0rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        
        /* 2. Custom Header ala USGS (Biru Tua) */
        .usgs-header {
            background-color: #00264C; /* Warna Biru Khas USGS/Gov */
            color: white;
            padding: 15px 20px;
            display: flex;
            align-items: center;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }
        .usgs-title {
            font-size: 24px;
            font-weight: bold;
            margin-left: 15px;
            letter-spacing: 0.5px;
        }
        .usgs-subtitle {
            font-size: 14px;
            color: #d1d5db;
            margin-left: 15px;
            border-left: 1px solid #d1d5db;
            padding-left: 15px;
        }

        /* 3. Memaksa Sidebar Berwarna Gelap (Dark Mode Override) */
        [data-testid="stSidebar"] {
            background-color: #1e1e1e; /* Abu-abu sangat gelap */
            border-right: 1px solid #333;
        }
        
        /* Mengubah warna teks di sidebar agar terbaca di background gelap */
        [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
            color: #e0e0e0 !important;
        }

        /* 4. Styling Expander agar mirip menu akordeon USGS */
        .streamlit-expanderHeader {
            background-color: #2d2d2d !important;
            color: white !important;
            font-weight: 600;
            border-radius: 5px;
        }
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

# --- 3. SIDEBAR (SEARCH CRITERIA STYLE) ---
with st.sidebar:
    st.markdown("### 1. Enter Search Criteria")
    
    # Menggunakan Expander agar mirip menu dropdown USGS
    with st.expander("📁 Data Import", expanded=True):
        uploaded_excel = st.file_uploader("Upload Excel Data (.xlsx)", type=["xlsx"])
        uploaded_map = st.file_uploader("Upload Geometry (.geojson/.shp)", type=["geojson", "json", "shp"])

    with st.expander("🎨 Visualization Settings", expanded=True):
        color_palette = st.selectbox(
            "Color Theme:",
            ["YlOrRd", "PuBu", "YlGn", "OrRd", "RdPu", "Spectral", "coolwarm", "turbo", "viridis"],
            index=0
        )
        
    st.info("💡 Pastikan format koordinat EPSG:4326 (Latitude/Longitude).")

# --- 4. PROSES UTAMA ---
# Container utama
main_container = st.container()

if uploaded_excel and uploaded_map:
    with main_container:
        try:
            # --- PRE-PROCESSING ---
            df = pd.read_excel(uploaded_excel)
            gdf_raw = gpd.read_file(uploaded_map)

            if gdf_raw.crs != "EPSG:4326":
                gdf_raw = gdf_raw.to_crs("EPSG:4326")

            # FILTER PROVINSI (Jika ada)
            if 'NAME_1' in gdf_raw.columns:
                list_provinsi = sorted(gdf_raw['NAME_1'].unique())
                # Pilihan provinsi ditaruh di atas peta agar lebih aksesibel
                pilihan_provinsi = st.selectbox("📍 Select Region of Interest:", list_provinsi)
                gdf_kecamatan = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
            else:
                gdf_kecamatan = gdf_raw
                pilihan_provinsi = "All Regions"

            # SPATIAL JOIN
            gdf_points = gpd.GeoDataFrame(
                df, 
                geometry=gpd.points_from_xy(df.longitude, df.latitude),
                crs="EPSG:4326"
            )
            joined = gpd.sjoin(gdf_points, gdf_kecamatan, how="inner", predicate="within")

            # AGREGASI
            region_col = 'NAME_3'
            if region_col not in gdf_kecamatan.columns:
                 region_col = st.selectbox("Select Region Column:", gdf_kecamatan.columns)

            agg_data = joined.groupby(region_col)['Z'].sum().reset_index()
            agg_data.columns = [region_col, 'Total_Penjualan']
            final_map_data = gdf_kecamatan.merge(agg_data, on=region_col, how="left")
            final_map_data['Total_Penjualan'] = final_map_data['Total_Penjualan'].fillna(0)

            # --- LOGIKA BINS ---
            min_val = final_map_data['Total_Penjualan'].min()
            max_val = final_map_data['Total_Penjualan'].max()
            
            try:
                default_quantiles = list(final_map_data['Total_Penjualan'].quantile([0, 0.25, 0.5, 0.75, 1.0]))
                default_quantiles = sorted(list(set(default_quantiles)))
                default_str = ", ".join([str(int(x)) for x in default_quantiles])
            except:
                default_str = f"{int(min_val)}, {int(max_val)}"

            # --- LAYOUT DASHBOARD ---
            # Kolom Kiri (Peta Besar) dan Kolom Kanan (Statistik/Result Panel)
            col_map, col_stats = st.columns([3, 1])

            with col_map:
                st.markdown(f"**Map View: {pilihan_provinsi}**")
                
                # Setup Folium
                centroid = final_map_data.geometry.centroid
                m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=9, tiles="CartoDB positron")

                # Input Legend di Sidebar, tapi diproses di sini
                with st.sidebar.expander("🎚️ Legend Configuration"):
                     user_bins = st.text_area("Value Breaks (Comma separated):", value=default_str)
                
                bins_list = None
                try:
                    custom_bins = [float(x.strip()) for x in user_bins.split(',')]
                    custom_bins = sorted(list(set(custom_bins)))
                    if custom_bins[0] > min_val: custom_bins.insert(0, min_val)
                    if custom_bins[-1] < max_val: custom_bins.append(max_val)
                    if len(custom_bins) >= 2: bins_list = custom_bins
                except:
                    pass 

                folium.Choropleth(
                    geo_data=final_map_data,
                    data=final_map_data,
                    columns=[region_col, "Total_Penjualan"],
                    key_on=f"feature.properties.{region_col}",
                    fill_color=color_palette,
                    fill_opacity=0.8,
                    line_opacity=0.3,
                    legend_name="Total Value (Z)",
                    bins=bins_list, 
                    highlight=True
                ).add_to(m)

                folium.GeoJson(
                    final_map_data,
                    style_function=lambda x: {'fillColor': '#00000000', 'color': '#00000000'},
                    tooltip=folium.GeoJsonTooltip(fields=[region_col, 'Total_Penjualan'], aliases=['Area:', 'Value:'], localize=True)
                ).add_to(m)

                st_folium(m, use_container_width=True, height=600)

            with col_stats:
                st.markdown("### Results Summary")
                
                # Kotak Statistik Sederhana
                st.metric("Total Observed Value", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
                
                st.markdown("---")
                st.markdown("**Top Areas:**")
                top_data = final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(10)
                st.dataframe(top_data, hide_index=True, use_container_width=True)

                # --- EXPORT SECTION ---
                st.markdown("### Export Map")
                format_file = st.selectbox("Format:", ["PNG", "PDF"])
                
                if st.button("Generate Download Link"):
                    with st.spinner("Processing..."):
                        # Logic Export Matplotlib (Sama seperti sebelumnya)
                        fig, ax = plt.subplots(figsize=(12, 8))
                        cmap_base = plt.get_cmap(color_palette)
                        norm = mcolors.BoundaryNorm(bins_list, cmap_base.N) if bins_list else mcolors.Normalize(vmin=min_val, vmax=max_val)

                        final_map_data.plot(column='Total_Penjualan', cmap=cmap_base, norm=norm, ax=ax, edgecolor='black', linewidth=0.4)
                        ax.set_axis_off()
                        
                        # Legend
                        cax = inset_axes(ax, width="40%", height="3%", loc='upper right')
                        cb = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap_base), cax=cax, orientation='horizontal', spacing='uniform')
                        cb.set_label('Total Value', size=9, weight='bold')
                        
                        img_buffer = io.BytesIO()
                        plt.savefig(img_buffer, format=format_file.lower(), transparent=True, bbox_inches='tight', dpi=300)
                        img_buffer.seek(0)
                        
                        st.download_button(
                            label=f"⬇️ Download {format_file}",
                            data=img_buffer,
                            file_name=f"Map_Result.{format_file.lower()}",
                            mime=f"image/{format_file.lower()}"
                        )

        except Exception as e:
            st.error(f"Error: {e}")
else:
    # Tampilan Awal (Placeholder Style)
    st.markdown("""
        <div style="text-align: center; padding: 50px; color: #666;">
            <h2>No Data Loaded</h2>
            <p>Please upload your Excel and Geometry files in the sidebar to begin analysis.</p>
        </div>
    """, unsafe_allow_html=True)
