import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
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

# --- 2. INJECT CSS KHUSUS (ANTI REDUP + USGS STYLE) ---
st.markdown("""
    <style>
        /* Anti-Dimming */
        .stApp, [data-testid="stAppViewContainer"], .element-container, iframe {
            opacity: 1 !important; filter: none !important; transition: none !important;
        }
        /* Layout Fixes */
        .block-container { padding-top: 0rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
        
        /* USGS Header */
        .usgs-header {
            background-color: #00264C; color: white; padding: 15px 20px;
            display: flex; align-items: center; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }
        .usgs-title { font-size: 24px; font-weight: bold; margin-left: 15px; letter-spacing: 0.5px; }
        .usgs-subtitle { font-size: 14px; color: #d1d5db; margin-left: 15px; border-left: 1px solid #d1d5db; padding-left: 15px; }
        
        /* Dark Sidebar */
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
    st.markdown("### 1. Enter Search Criteria")
    with st.expander("📁 Data Import", expanded=True):
        uploaded_excel = st.file_uploader("Upload Excel Data (.xlsx)", type=["xlsx"])
        uploaded_map = st.file_uploader("Upload Geometry (.geojson/.shp)", type=["geojson", "json", "shp"])

    with st.expander("🎨 Visualization Settings", expanded=True):
        color_palette = st.selectbox("Color Theme:", ["YlOrRd", "PuBu", "YlGn", "OrRd", "RdPu", "Spectral", "coolwarm", "turbo", "viridis"], index=0)

# --- 4. PROSES UTAMA ---
main_container = st.container()

if uploaded_excel and uploaded_map:
    with main_container:
        try:
            # --- DATA PREP ---
            df = pd.read_excel(uploaded_excel)
            gdf_raw = gpd.read_file(uploaded_map)
            if gdf_raw.crs != "EPSG:4326": gdf_raw = gdf_raw.to_crs("EPSG:4326")

            # Filter
            if 'NAME_1' in gdf_raw.columns:
                list_provinsi = sorted(gdf_raw['NAME_1'].unique())
                pilihan_provinsi = st.selectbox("📍 Select Region of Interest:", list_provinsi)
                gdf_kecamatan = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
            else:
                gdf_kecamatan = gdf_raw
                pilihan_provinsi = "All Regions"

            # Join
            gdf_points = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs="EPSG:4326")
            joined = gpd.sjoin(gdf_points, gdf_kecamatan, how="inner", predicate="within")

            region_col = 'NAME_3' if 'NAME_3' in gdf_kecamatan.columns else st.selectbox("Select Region Column:", gdf_kecamatan.columns)
            
            agg_data = joined.groupby(region_col)['Z'].sum().reset_index()
            agg_data.columns = [region_col, 'Total_Penjualan']
            final_map_data = gdf_kecamatan.merge(agg_data, on=region_col, how="left")
            final_map_data['Total_Penjualan'] = final_map_data['Total_Penjualan'].fillna(0)

            # Bins (0, 25, 50, 75, 100%)
            max_val = final_map_data['Total_Penjualan'].max()
            linear_breaks = sorted(list(set([0, max_val * 0.25, max_val * 0.50, max_val * 0.75, max_val])))
            default_str = ", ".join([str(int(x)) for x in linear_breaks])

            # --- LAYOUT DASHBOARD ---
            col_map, col_stats = st.columns([3, 1])

            with col_map:
                st.markdown(f"**Map View: {pilihan_provinsi}**")
                
                # Peta (Micro-Zoom)
                centroid = final_map_data.geometry.centroid
                m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=9, tiles="CartoDB positron", zoom_snap=0.1, zoom_delta=0.1)
                
                # Draw Tool
                draw = Draw(export=False, position='topleft', draw_options={'polyline':False,'polygon':False,'circle':False,'marker':False,'circlemarker':False,'rectangle':True})
                draw.add_to(m)

                # Legend Sidebar Input
                with st.sidebar.expander("🎚️ Legend Configuration", expanded=True):
                     user_bins = st.text_area("Value Breaks:", value=default_str)
                
                bins_list = None
                try:
                    custom_bins = sorted(list(set([float(x.strip()) for x in user_bins.split(',')])))
                    if custom_bins[0] > 0: custom_bins.insert(0, 0)
                    if custom_bins[-1] < max_val: custom_bins.append(max_val)
                    if len(custom_bins) >= 2: bins_list = custom_bins
                except: pass 

                folium.Choropleth(
                    geo_data=final_map_data, data=final_map_data, columns=[region_col, "Total_Penjualan"],
                    key_on=f"feature.properties.{region_col}", fill_color=color_palette, fill_opacity=0.8,
                    line_opacity=0.3, legend_name="Total Value (Z)", bins=bins_list, highlight=True
                ).add_to(m)

                folium.GeoJson(final_map_data, style_function=lambda x: {'fillColor':'#00000000','color':'#00000000'}, tooltip=folium.GeoJsonTooltip(fields=[region_col, 'Total_Penjualan'], aliases=['Area:', 'Value:'], localize=True)).add_to(m)

                map_output = st_folium(m, use_container_width=True, height=600)

            with col_stats:
                st.markdown("### Results Summary")
                st.metric("Total Observed Value", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
                st.markdown("---")
                
                # --- EXPORT SECTION ---
                st.markdown("### Export Map")
                st.caption("Gunakan alat 'Kotak' di peta untuk memilih area print.")
                format_file = st.selectbox("Format:", ["PNG", "PDF"])
                
                if st.button("Generate Download Link"):
                    with st.spinner("Rendering Canvas..."):
                        
                        # 1. Tentukan Koordinat Crop
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

                        # 2. Setup Figure Matplotlib
                        fig, ax = plt.subplots(figsize=(10, 10)) 
                        cmap_base = plt.get_cmap(color_palette)
                        norm = mcolors.BoundaryNorm(bins_list, cmap_base.N) if bins_list else mcolors.Normalize(vmin=0, vmax=max_val)

                        final_map_data.plot(column='Total_Penjualan', cmap=cmap_base, norm=norm, ax=ax, edgecolor='black', linewidth=0.5)
                        
                        # 3. Crop Area
                        ax.set_xlim(west, east)
                        ax.set_ylim(south, north)
                        ax.set_axis_off() 

                        # 4. LEGENDA (FIXED: 4-TUPLE UNTUK MENGHINDARI ERROR RELATIVE UNITS)
                        # Koordinat (x, y, width, height)
                        cax = inset_axes(
                            ax,
                            width="100%",    
                            height="100%",   
                            loc='upper center',
                            bbox_to_anchor=(0.2, -0.08, 0.6, 0.03), # Posisi fix di bawah peta
                            bbox_transform=ax.transAxes,
                            borderpad=0
                        )
                        
                        cb = fig.colorbar(
                            cm.ScalarMappable(norm=norm, cmap=cmap_base),
                            cax=cax,
                            orientation='horizontal',
                            spacing='uniform'
                        )
                        cb.set_label('Total Penjualan (Rupiah)', size=10, weight='bold', labelpad=5)
                        cb.ax.tick_params(labelsize=8)

                        # 5. Simpan
                        img_buffer = io.BytesIO()
                        plt.savefig(img_buffer, format=format_file.lower(), transparent=True, bbox_inches='tight', dpi=300)
                        img_buffer.seek(0)
                        
                        # FIX "DUPLICATE ID": TAMBAHKAN KEY UNIK
                        st.download_button(
                            label=f"⬇️ Download {format_file}",
                            data=img_buffer,
                            file_name=f"Map_Export.{format_file.lower()}",
                            mime=f"image/{format_file.lower()}",
                            key="btn_download_map_final"  # <--- INI KUNCINYA
                        )

        except Exception as e:
            st.error(f"Error: {e}")
else:
    st.markdown("<div style='text-align: center; padding: 50px; color: #666;'><h2>No Data Loaded</h2></div>", unsafe_allow_html=True)
