import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import branca.colormap as cm
import io
from streamlit_folium import st_folium
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

# 1. KONFIGURASI HALAMAN
st.set_page_config(page_title="Peta Penjualan Rokok", layout="wide")

# CSS: Background Putih & Hapus Loading Gelap
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #000000; }
    .stSpinner > div { border-top-color: #333 !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🗺️ Peta Penjualan Rokok Surya 16")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_excel = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    uploaded_map = st.file_uploader("Upload Peta (.geojson/.shp)", type=["geojson", "json", "shp"])

    st.header("2. Pengaturan Tampilan")
    
    # DAFTAR WARNA (Sederhana, tanpa label QGIS)
    daftar_warna = [
        "turbo", "viridis", "magma", "plasma", "inferno",
        "Reds", "Blues", "Greens", "Oranges", "Purples", 
        "YlOrRd", "YlGnBu", "RdYlGn", "Spectral", "coolwarm"
    ]
    
    color_palette = st.selectbox("Pilih Tema Warna:", daftar_warna, index=0)

# --- PROSES UTAMA ---
if uploaded_excel and uploaded_map:
    # Notifikasi proses tanpa menggelapkan layar
    status_text = st.empty()
    
    try:
        # 1. BACA DATA
        df = pd.read_excel(uploaded_excel)
        gdf_raw = gpd.read_file(uploaded_map)

        if gdf_raw.crs != "EPSG:4326":
            gdf_raw = gdf_raw.to_crs("EPSG:4326")

        # FILTER PROVINSI
        if 'NAME_1' in gdf_raw.columns:
            list_provinsi = sorted(gdf_raw['NAME_1'].unique())
            st.sidebar.markdown("---")
            pilihan_provinsi = st.sidebar.selectbox("Fokus Provinsi:", list_provinsi)
            gdf_kecamatan = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
        else:
            gdf_kecamatan = gdf_raw
            pilihan_provinsi = "Semua Wilayah"

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
             region_col = st.selectbox("Pilih Kolom Nama Kecamatan:", gdf_kecamatan.columns)

        agg_data = joined.groupby(region_col)['Z'].sum().reset_index()
        agg_data.columns = [region_col, 'Total_Penjualan']

        final_map_data = gdf_kecamatan.merge(agg_data, on=region_col, how="left")
        final_map_data['Total_Penjualan'] = final_map_data['Total_Penjualan'].fillna(0)

        # -----------------------------------------------------------
        # LOGIKA DEFAULT BINS (0%, 25%, 50%, 75%, 100%)
        # -----------------------------------------------------------
        min_val = final_map_data['Total_Penjualan'].min()
        max_val = final_map_data['Total_Penjualan'].max()
        
        # Hitung Percentile (Quartile)
        try:
            # Ini akan menghasilkan 5 angka: Min, Q1, Median, Q3, Max
            default_quantiles = list(final_map_data['Total_Penjualan'].quantile([0, 0.25, 0.5, 0.75, 1.0]))
            
            # Ubah ke Integer (Bulat) & Hapus duplikat jika datanya sedikit
            clean_quantiles = sorted(list(set([int(x) for x in default_quantiles])))
            
            # Gabungkan jadi string untuk ditampilkan di input box
            default_str = ", ".join([str(x) for x in clean_quantiles])
        except:
            default_str = f"{int(min_val)}, {int(max_val)}"

        # TAMPILKAN INPUT BOX
        st.sidebar.markdown("### Batas Nilai (Legend)")
        st.sidebar.caption("Default: 0% - 25% - 50% - 75% - 100%")
        
        user_bins = st.sidebar.text_area(
            "Edit batas nilai (pisahkan koma):", 
            value=default_str,
            height=80
        )
        
        # PROSES NILAI DARI INPUT BOX
        bins_list = None
        try:
            custom_bins = [float(x.strip()) for x in user_bins.split(',')]
            custom_bins = sorted(list(set(custom_bins)))
            
            # Pastikan range aman
            if custom_bins[0] > min_val: custom_bins.insert(0, min_val)
            if custom_bins[-1] < max_val: custom_bins.append(max_val)
            
            # Validasi minimal 4 angka (3 zona warna)
            if len(custom_bins) < 4:
                st.sidebar.warning("⚠️ Minimal 4 batas angka diperlukan.")
                bins_list = None 
            else:
                bins_list = custom_bins
        except:
            st.sidebar.error("⚠️ Format angka salah.")

        # -----------------------------------------------------------
        # MEMBUAT WARNA & LEGENDA (BRANCA)
        # -----------------------------------------------------------
        if bins_list:
            # 1. Ambil Palette Matplotlib (misal: Turbo)
            mpl_cmap = plt.get_cmap(color_palette)
            
            # 2. Ambil sampel warna sebanyak jumlah zona (bins - 1)
            n_colors = len(bins_list) - 1
            colors_hex = []
            for i in range(n_colors):
                # Ambil warna dari posisi 0.0 sampai 1.0
                rgb = mpl_cmap(i / (n_colors - 1) if n_colors > 1 else 0.5) 
                colors_hex.append(mcolors.to_hex(rgb))
            
            # 3. Buat Colormap object untuk Folium/Branca
            colormap = cm.StepColormap(
                colors=colors_hex,
                index=bins_list,
                vmin=bins_list[0],
                vmax=bins_list[-1],
                caption="Total Penjualan (Z)"
            )
            
            # 4. Fungsi Style untuk GeoJSON
            def style_function(feature):
                val = feature['properties']['Total_Penjualan']
                return {
                    'fillColor': colormap(val), # Pakai warna dari colormap
                    'color': 'black',
                    'weight': 0.5,
                    'fillOpacity': 0.8
                }
        else:
            # Fallback jika error
            colormap = None
            def style_function(feature):
                return {'fillColor': 'gray', 'color': 'black', 'weight': 0.5}

        # -----------------------------------------------------------
        # VISUALISASI FOLIUM
        # -----------------------------------------------------------
        centroid = final_map_data.geometry.centroid
        m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=8, tiles="CartoDB positron")

        # Tambahkan Layer Peta
        folium.GeoJson(
            final_map_data,
            style_function=style_function,
            tooltip=folium.GeoJsonTooltip(
                fields=[region_col, 'Total_Penjualan'],
                aliases=['Kecamatan:', 'Total:'],
                localize=True
            )
        ).add_to(m)

        # TAMBAHKAN LEGENDA KE PETA
        if colormap:
            colormap.add_to(m)

        # Hapus status
        status_text.empty()

        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"Peta Interaktif: {pilihan_provinsi}")
            map_output = st_folium(m, use_container_width=True)

        with col2:
            st.subheader("Statistik")
            st.metric("Total Penjualan", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
            st.dataframe(final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(10), hide_index=True)

            # -----------------------------------------------------------
            # FITUR EXPORT (Tetap mempertahankan fungsi export)
            # -----------------------------------------------------------
            st.markdown("---")
            st.subheader("⬇️ Export View")
            format_file = st.selectbox("Format:", ["PNG", "SVG"])
            
            if st.button("Generate from Current View"):
                st.toast("Sedang merender gambar...")
                
                bounds = map_output.get("bounds")
                if bounds:
                    south, north = bounds['_southWest']['lat'], bounds['_northEast']['lat']
                    west, east = bounds['_southWest']['lng'], bounds['_northEast']['lng']
                else:
                    minx, miny, maxx, maxy = final_map_data.total_bounds
                    west, south, east, north = minx, miny, maxx, maxy

                fig, ax = plt.subplots(figsize=(12, 7))
                
                # Setup warna untuk Matplotlib agar SAMA dengan Folium
                mpl_cmap = plt.get_cmap(color_palette)
                if bins_list:
                    norm = mcolors.BoundaryNorm(bins_list, mpl_cmap.N)
                else:
                    norm = mcolors.Normalize(vmin=min_val, vmax=max_val)

                final_map_data.plot(
                    column='Total_Penjualan',
                    cmap=mpl_cmap,
                    norm=norm,
                    ax=ax,
                    edgecolor='black',
                    linewidth=0.3
                )
                
                ax.set_xlim(west, east)
                ax.set_ylim(south, north)
                ax.set_axis_off()
                
                # Legend Export
                cax = inset_axes(ax, width="35%", height="2.5%", loc='upper right',
                                bbox_to_anchor=(0, -0.05, 1, 1), 
                                bbox_transform=ax.transAxes, borderpad=0)
                
                cb = fig.colorbar(
                    plt.cm.ScalarMappable(norm=norm, cmap=mpl_cmap),
                    cax=cax, orientation='horizontal', spacing='uniform' 
                )
                cb.ax.tick_params(labelsize=6, color='black', labelcolor='black')
                if bins_list:
                    cb.set_ticks(bins_list)
                    cb.set_ticklabels([f"{int(x):,}" for x in bins_list])
                cb.set_label('Total Penjualan (Z)', size=8, weight='bold', labelpad=7) 
                
                fig.patch.set_alpha(0.0)
                ax.patch.set_alpha(0.0)

                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format=format_file.lower(), transparent=True, dpi=200, bbox_inches='tight', pad_inches=0.1)
                img_buffer.seek(0)
                
                st.download_button(
                    label=f"Download {format_file}",
                    data=img_buffer,
                    file_name=f"peta_canvas_{pilihan_provinsi}.{format_file.lower()}",
                    mime=f"image/{format_file.lower()}" if format_file != "SVG" else "image/svg+xml"
                )

    except Exception as e:
        status_text.empty()
        st.error(f"Terjadi kesalahan: {e}")
else:
    st.info("Silakan upload data Excel dan Shapefile di sidebar.")
