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
        <div class="usgs-title">Geospatial Explorer</div>
        <div class="usgs-subtitle">Data Visualization Interface</div>
    </div>
""", unsafe_allow_html=True)

# --- 2. FUNGSI CACHING (AGAR CEPAT) ---
@st.cache_data(show_spinner=True)
def load_and_process_data(excel_file, map_file):
    df = pd.read_excel(excel_file)
    gdf_raw = gpd.read_file(map_file)
    
    if gdf_raw.crs != "EPSG:4326": 
        gdf_raw = gdf_raw.to_crs("EPSG:4326")
    
    # Optimisasi: Sederhanakan geometri sedikit
    gdf_raw['geometry'] = gdf_raw['geometry'].simplify(tolerance=0.001, preserve_topology=True)
    
    gdf_points = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df['LONGITUDE'], df['LATITUDE']), 
        crs="EPSG:4326"
    )
    
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
            # Load Data (Cached)
            df_original, gdf_raw, joined_full = load_and_process_data(uploaded_excel, uploaded_map)

            # --- FILTERING ---
            df_filtered = joined_full.copy()
            selected_brand = 'All Brands'
            
            # Filter Brand
            if 'Brand' in df_filtered.columns:
                unique_brands = sorted([str(x) for x in df_filtered['Brand'].dropna().unique()])
                brand_options = ['All Brands'] + unique_brands
                st.sidebar.markdown("### 2. Filters")
                selected_brand = st.sidebar.selectbox("🏷️ Select Brand:", brand_options)
                
                if selected_brand != 'All Brands':
                    df_filtered = df_filtered[df_filtered['Brand'].astype(str) == selected_brand]

            # Filter Wilayah
            if 'NAME_1' in gdf_raw.columns:
                list_provinsi = sorted(gdf_raw['NAME_1'].unique())
                pilihan_provinsi = st.selectbox("📍 Select Region of Interest:", list_provinsi)
                
                gdf_kecamatan_display = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
                df_filtered = df_filtered[df_filtered['NAME_1'] == pilihan_provinsi]
            else:
                gdf_kecamatan_display = gdf_raw
                pilihan_provinsi = "All Regions"

            # --- AGREGASI ---
            region_col = 'NAME_3' if 'NAME_3' in gdf_kecamatan_display.columns else gdf_kecamatan_display.columns[0]
            
            if 'Stick' in df_filtered.columns:
                agg_data = df_filtered.groupby(region_col)['Stick'].sum().reset_index()
                agg_data.columns = [region_col, 'Total_Stick']
            else:
                st.error("Kolom 'Stick' tidak ditemukan.")
                st.stop()

            final_map_data = gdf_kecamatan_display.merge(agg_data, on=region_col, how="left")
            final_map_data['Total_Stick'] = final_map_data['Total_Stick'].fillna(0)

            # --- VISUALISASI ---
            max_val = final_map_data['Total_Stick'].max()
            if max_val == 0: max_val = 1
            linear_breaks = sorted(list(set([0, max_val * 0.25, max_val * 0.50, max_val * 0.75, max_val])))
            default_str = ", ".join([str(int(x)) for x in linear_breaks])

            col_map, col_stats = st.columns([2.3, 1.7])

            # ==========================
            # PANEL KIRI: PETA
            # ==========================
            with col_map:
                st.markdown(f"**Map View: {pilihan_provinsi}**")
                
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

                # --- EXPORT MAP LOGIC ---
                st.caption("Peta siap diunduh (Sesuai tampilan di atas)")
                
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

                # Matplotlib Plot
                fig, ax = plt.subplots(figsize=(10, 10))
                cmap_base = plt.get_cmap(color_palette)
                norm = mcolors.BoundaryNorm(bins_list, cmap_base.N) if bins_list else mcolors.Normalize(vmin=0, vmax=max_val)
                
                final_map_data.plot(column='Total_Stick', cmap=cmap_base, norm=norm, ax=ax, edgecolor='black', linewidth=0.5)
                ax.set_xlim(west, east); ax.set_ylim(south, north); ax.set_axis_off()

                # Legend Bawah
                cax = inset_axes(ax, width="100%", height="100%", loc='upper center', bbox_to_anchor=(0.2, -0.25, 0.6, 0.05), bbox_transform=ax.transAxes, borderpad=0)
                cb = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap_base), cax=cax, orientation='horizontal', spacing='uniform')
                cb.ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
                cb.set_label(f'Total Penjualan (Stik) - {selected_brand}', size=10, weight='bold', labelpad=10)
                cb.ax.xaxis.set_ticks_position('bottom')
                cb.ax.tick_params(labelsize=8)

                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format='png', transparent=True, bbox_inches='tight', dpi=300, pad_inches=0.2)
                img_buffer.seek(0)
                plt.close(fig)
                
                st.download_button(
                    label="⬇️ Download Map (PNG)", 
                    data=img_buffer, 
                    file_name="Map_Export.png", 
                    mime="image/png", 
                    key="dl_map_direct"
                )

            # ==========================
            # PANEL KANAN: TABEL
            # ==========================
            with col_stats:
                st.markdown("### 📋 Data Breakdown")
                
                df_display = final_map_data[[region_col, 'Total_Stick']].copy()
                df_display = df_display.sort_values(by='Total_Stick', ascending=False).reset_index(drop=True)
                df_display.columns = ['Kecamatan', 'Total Stick']
                df_display.index = df_display.index + 1
                
                # --- [BARU] HITUNG & TAMPILKAN TOTAL DI WEB ---
                total_all_sales = df_display['Total Stick'].sum()
                st.metric(label="Total Penjualan (Semua Kecamatan)", value=f"{total_all_sales:,.0f}")
                # ----------------------------------------------
                
                st.dataframe(df_display, use_container_width=True, height=400, column_config={"Total Stick": st.column_config.NumberColumn(format="%d")})

                # --- EXPORT TABLE LOGIC ---
                st.markdown("---")
                st.markdown("### 📸 Export Table (Top 10)")
                
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
                
                # --- [BARU] UPDATE JUDUL EXPORT UNTUK MENAMPILKAN TOTAL ---
                plt.title(
                    f"Top 10 Wilayah - {pilihan_provinsi}\n({selected_brand})\nTotal Penjualan : {total_all_sales:,.0f}", 
                    y=1.0, pad=15, fontsize=12, fontweight='bold', color='#333'
                )
                # ---------------------------------------------------------
                
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
            st.error(f"Error: {e}")
else:
    st.info("Silakan upload file Excel dan GeoJSON untuk memulai.")

