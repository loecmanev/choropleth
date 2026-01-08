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

# --- 1. KONFIGURASI HALAMAN & CSS MODERN ---
st.set_page_config(
    page_title="Dashboard Penjualan Rokok", 
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject CSS untuk tampilan yang lebih bersih (Top Bar style & Metric Box)
st.markdown("""
    <style>
        /* Mengurangi padding atas agar header lebih naik */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        /* Style untuk metric box agar ada border halus */
        div[data-testid="stMetric"] {
            background-color: #f0f2f6;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #d6d6d6;
        }
        /* Mengatur warna background header sidebar (opsional) */
        section[data-testid="stSidebar"] {
            background-color: #f9f9f9;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. HEADER / TOP BAR AREA ---
# Menggunakan kolom untuk menaruh Logo dan Judul berdampingan
col_logo, col_title = st.columns([1, 8])

with col_logo:
    # GANTI URL INI DENGAN PATH LOGO ANDA SENDIRI
    # Jika ada file lokal: st.image("logo.png", width=80)
    st.image("https://cdn-icons-png.flaticon.com/512/854/854878.png", width=70) 

with col_title:
    st.title("Dashboard Analisis Geospasial")
    st.caption("Monitoring Penjualan Rokok Surya 16 - Wilayah Maluku")

st.markdown("---") # Divider tipis di bawah header

# --- 3. SIDEBAR (INPUT DATA) ---
with st.sidebar:
    st.header("📂 Data Input")
    
    with st.expander("Upload File", expanded=True):
        uploaded_excel = st.file_uploader("Data Penjualan (.xlsx)", type=["xlsx"])
        uploaded_map = st.file_uploader("Peta Wilayah (.geojson/.shp)", type=["geojson", "json", "shp"])

    st.header("🎨 Visualisasi")
    color_palette = st.selectbox(
        "Tema Warna Peta:",
        ["YlOrRd", "PuBu", "YlGn", "OrRd", "RdPu", "Spectral", "coolwarm", "turbo", "viridis"],
        index=0
    )

# --- 4. PROSES UTAMA ---
if uploaded_excel and uploaded_map:
    try:
        # --- PRE-PROCESSING DATA ---
        df = pd.read_excel(uploaded_excel)
        gdf_raw = gpd.read_file(uploaded_map)

        # Pastikan CRS standar GPS (Lat/Long)
        if gdf_raw.crs != "EPSG:4326":
            gdf_raw = gdf_raw.to_crs("EPSG:4326")

        # FILTER PROVINSI
        if 'NAME_1' in gdf_raw.columns:
            list_provinsi = sorted(gdf_raw['NAME_1'].unique())
            pilihan_provinsi = st.sidebar.selectbox("🔎 Fokus Wilayah (Provinsi):", list_provinsi)
            gdf_kecamatan = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
        else:
            gdf_kecamatan = gdf_raw
            pilihan_provinsi = "Semua Wilayah"

        # SPATIAL JOIN (Titik ke Poligon)
        gdf_points = gpd.GeoDataFrame(
            df, 
            geometry=gpd.points_from_xy(df.longitude, df.latitude),
            crs="EPSG:4326"
        )
        joined = gpd.sjoin(gdf_points, gdf_kecamatan, how="inner", predicate="within")

        # AGREGASI DATA
        region_col = 'NAME_3'
        if region_col not in gdf_kecamatan.columns:
             region_col = st.selectbox("Pilih Kolom Kecamatan:", gdf_kecamatan.columns)

        agg_data = joined.groupby(region_col)['Z'].sum().reset_index()
        agg_data.columns = [region_col, 'Total_Penjualan']

        final_map_data = gdf_kecamatan.merge(agg_data, on=region_col, how="left")
        final_map_data['Total_Penjualan'] = final_map_data['Total_Penjualan'].fillna(0)

        # --- LOGIKA BINS (LEGEND) ---
        min_val = final_map_data['Total_Penjualan'].min()
        max_val = final_map_data['Total_Penjualan'].max()
        
        # Hitung default (Quantile) untuk saran
        try:
            default_quantiles = list(final_map_data['Total_Penjualan'].quantile([0, 0.25, 0.5, 0.75, 1.0]))
            default_quantiles = sorted(list(set(default_quantiles)))
            default_str = ", ".join([str(int(x)) for x in default_quantiles])
        except:
            default_str = f"{int(min_val)}, {int(max_val)}"

        # Input Box Custom Legend di Sidebar
        st.sidebar.markdown("### 🎚️ Klasifikasi Legend")
        user_bins = st.sidebar.text_area(
            "Atur Batas Nilai (pisahkan koma):", 
            value=default_str,
            help="Masukkan angka urut dari kecil ke besar untuk membagi warna peta."
        )
        
        bins_list = None
        try:
            custom_bins = [float(x.strip()) for x in user_bins.split(',')]
            custom_bins = sorted(list(set(custom_bins)))
            if custom_bins[0] > min_val: custom_bins.insert(0, min_val)
            if custom_bins[-1] < max_val: custom_bins.append(max_val)
            
            if len(custom_bins) >= 2:
                bins_list = custom_bins
        except:
            pass 

        # --- LAYOUT DASHBOARD UTAMA ---
        # Kita bagi layar: Kiri (Peta Besar) - Kanan (Panel Info & Export)
        col_map, col_info = st.columns([3, 1.2])

        with col_map:
            st.subheader(f"📍 Peta Sebaran: {pilihan_provinsi}")
            
            # Setup Folium Map
            centroid = final_map_data.geometry.centroid
            m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=9, tiles="CartoDB positron")

            folium.Choropleth(
                geo_data=final_map_data,
                data=final_map_data,
                columns=[region_col, "Total_Penjualan"],
                key_on=f"feature.properties.{region_col}",
                fill_color=color_palette,
                fill_opacity=0.8,
                line_opacity=0.3,
                legend_name="Total Penjualan (Z)",
                bins=bins_list, 
                highlight=True
            ).add_to(m)

            # Tooltip Interaktif
            folium.GeoJson(
                final_map_data,
                style_function=lambda x: {'fillColor': '#00000000', 'color': '#00000000'},
                tooltip=folium.GeoJsonTooltip(
                    fields=[region_col, 'Total_Penjualan'],
                    aliases=['Kecamatan:', 'Omzet:'],
                    localize=True
                )
            ).add_to(m)

            # Render Map
            map_output = st_folium(m, use_container_width=True, height=500)

        with col_info:
            st.subheader("📊 Statistik")
            
            # Highlight Angka Besar
            total_sales = final_map_data['Total_Penjualan'].sum()
            st.metric(label="Total Penjualan Wilayah", value=f"Rp {total_sales:,.0f}")
            
            st.markdown("**Top 5 Kecamatan:**")
            top_5 = final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(5)
            st.dataframe(
                top_5, 
                hide_index=True, 
                column_config={
                    region_col: "Kecamatan",
                    "Total_Penjualan": st.column_config.NumberColumn("Penjualan", format="Rp %d")
                }
            )

            # --- BAGIAN EXPORT YANG DIPERBAHARUI ---
            st.markdown("---")
            st.subheader("🖨️ Export Peta")
            
            with st.expander("⚙️ Pengaturan Gambar", expanded=True):
                format_file = st.selectbox("Format File:", ["PNG", "SVG", "PDF"])
                
                if st.button("📸 Generate Canvas View", type="primary", use_container_width=True):
                    with st.spinner("Sedang menggambar ulang peta HQ..."):
                        
                        # Ambil Bounding Box dari View Terakhir User
                        bounds = map_output.get("bounds")
                        if bounds:
                            south, north = bounds['_southWest']['lat'], bounds['_northEast']['lat']
                            west, east = bounds['_southWest']['lng'], bounds['_northEast']['lng']
                        else:
                            minx, miny, maxx, maxy = final_map_data.total_bounds
                            west, south, east, north = minx, miny, maxx, maxy

                        # SETUP PLOT MATPLOTLIB (High Quality)
                        fig, ax = plt.subplots(figsize=(12, 8))
                        
                        # Colormap
                        cmap_base = plt.get_cmap(color_palette)
                        if bins_list:
                            norm = mcolors.BoundaryNorm(bins_list, cmap_base.N)
                        else:
                            norm = mcolors.Normalize(vmin=min_val, vmax=max_val)

                        # Plotting
                        final_map_data.plot(
                            column='Total_Penjualan',
                            cmap=cmap_base,
                            norm=norm,
                            ax=ax,
                            edgecolor='black',
                            linewidth=0.4
                        )
                        
                        # Crop sesuai view user
                        ax.set_xlim(west, east)
                        ax.set_ylim(south, north)
                        ax.set_axis_off()
                        
                        # LEGEND YANG LEBIH CANTIK
                        cax = inset_axes(ax, width="40%", height="3%", loc='upper right')
                        cb = fig.colorbar(
                            cm.ScalarMappable(norm=norm, cmap=cmap_base),
                            cax=cax, orientation='horizontal', spacing='uniform'
                        )
                        cb.ax.tick_params(labelsize=7, color='black', labelcolor='black') 
                        cb.set_label('Total Penjualan (Rupiah)', size=9, weight='bold', labelpad=5)
                        
                        # Transparansi
                        fig.patch.set_alpha(0.0)
                        ax.patch.set_alpha(0.0)

                        # Simpan ke Buffer
                        img_buffer = io.BytesIO()
                        plt.savefig(
                            img_buffer, 
                            format=format_file.lower(), 
                            transparent=True, 
                            dpi=300, 
                            bbox_inches='tight'
                        )
                        img_buffer.seek(0)
                        
                        st.success("Gambar siap!")
                        st.download_button(
                            label=f"⬇️ Download {format_file}",
                            data=img_buffer,
                            file_name=f"Map_Penjualan_{pilihan_provinsi}.{format_file.lower()}",
                            mime=f"image/{format_file.lower() if format_file != 'SVG' else 'svg+xml'}",
                            use_container_width=True
                        )

    except Exception as e:
        st.error(f"Terjadi kesalahan saat memproses data: {e}")
else:
    # Tampilan awal saat belum ada data (Landing Page Sederhana)
    st.info("👋 Selamat datang! Silakan upload file Excel dan Peta (GeoJSON/SHP) di sidebar sebelah kiri untuk memulai analisis.")
