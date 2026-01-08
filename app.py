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

# 1. KONFIGURASI HALAMAN (Wajib Paling Atas)
st.set_page_config(page_title="Peta Penjualan Rokok", layout="wide")

# CSS HACK: Memaksa Background Putih & Menghapus Efek Gelap Loading
st.markdown("""
    <style>
    /* Paksa background putih */
    .stApp {
        background-color: #FFFFFF;
        color: #000000;
    }
    /* Sembunyikan dekorasi loading bawaan yang bikin gelap */
    .stSpinner > div {
        border-top-color: #333 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🗺️ Peta Interaktif & Export Canvas Style")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_excel = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    uploaded_map = st.file_uploader("Upload Peta (.geojson/.shp)", type=["geojson", "json", "shp"])

    st.header("2. Pengaturan Tampilan")
    
    # Daftar Warna Lengkap (Matplotlib Style)
    daftar_warna = [
        "turbo", "viridis", "magma", "plasma", "inferno", # Modern High Contrast
        "Reds", "Blues", "Greens", "Oranges", "Purples", "Greys", # Single Hue
        "YlOrRd", "YlGnBu", "RdYlGn", "Spectral", "coolwarm", "seismic" # Diverging
    ]
    
    color_palette = st.selectbox(
        "Pilih Tema Warna:",
        daftar_warna,
        index=0 # Default Turbo
    )

# --- PROSES UTAMA ---
if uploaded_excel and uploaded_map:
    # Ganti st.spinner dengan st.empty agar tidak menggelapkan layar
    status_text = st.empty()
    status_text.info("⏳ Sedang memproses data... (Mohon tunggu)")

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
        # LOGIKA BINS (QUARTILE DEFAULT)
        # -----------------------------------------------------------
        min_val = final_map_data['Total_Penjualan'].min()
        max_val = final_map_data['Total_Penjualan'].max()
        
        # Hitung Default
        try:
            default_quantiles = list(final_map_data['Total_Penjualan'].quantile([0, 0.25, 0.5, 0.75, 1.0]))
            clean_quantiles = sorted(list(set([int(x) for x in default_quantiles])))
            default_str = ", ".join([str(x) for x in clean_quantiles])
        except:
            default_str = f"{int(min_val)}, {int(max_val)}"

        # Input Box
        st.sidebar.markdown("### Batas Nilai (Legend)")
        st.sidebar.caption(f"Rentang Data: {int(min_val):,} - {int(max_val):,}")
        
        user_bins = st.sidebar.text_area(
            "Edit batas nilai (pisahkan koma):", 
            value=default_str,
            height=80
        )
        
        # Proses Input Bins
        bins_list = None
        try:
            custom_bins = [float(x.strip()) for x in user_bins.split(',')]
            custom_bins = sorted(list(set(custom_bins)))
            if custom_bins[0] > min_val: custom_bins.insert(0, min_val)
            if custom_bins[-1] < max_val: custom_bins.append(max_val)
            
            if len(custom_bins) < 4:
                st.sidebar.warning("⚠️ Minimal 4 angka batas.")
                bins_list = None 
            else:
                bins_list = custom_bins
        except:
            st.sidebar.error("⚠️ Format angka salah.")

        # -----------------------------------------------------------
        # TEKNIK WARNA MANUAL (Agar Turbo Muncul di Peta Interaktif)
        # -----------------------------------------------------------
        # Kita hitung warna HEX untuk setiap kecamatan menggunakan Matplotlib
        # lalu kita 'tempel' warna itu ke Peta Folium.
        
        cmap = plt.get_cmap(color_palette) # Ambil tema warna (misal: turbo)
        
        if bins_list:
            norm = mcolors.BoundaryNorm(bins_list, cmap.N)
        else:
            norm = mcolors.Normalize(vmin=min_val, vmax=max_val)

        # Fungsi konversi Nilai -> Hex Color
        def get_hex_color(val):
            if pd.isna(val) or val == 0:
                return "#FFF8DC" # Warna krem muda untuk data 0/Kosong
            return mcolors.to_hex(cmap(norm(val)))

        # Terapkan ke GeoDataFrame
        final_map_data['color_hex'] = final_map_data['Total_Penjualan'].apply(get_hex_color)

        # -----------------------------------------------------------
        # VISUALISASI FOLIUM
        # -----------------------------------------------------------
        centroid = final_map_data.geometry.centroid
        m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=8, tiles="CartoDB positron")

        # Kita pakai GeoJson biasa (bukan Choropleth) supaya bisa pakai warna 'turbo' kita
        folium.GeoJson(
            final_map_data,
            style_function=lambda feature: {
                'fillColor': feature['properties']['color_hex'], # <--- Pakai warna turbo yg sudah dihitung
                'color': 'black',       # Warna garis pinggir
                'weight': 0.5,          # Tebal garis
                'fillOpacity': 0.8
            },
            tooltip=folium.GeoJsonTooltip(
                fields=[region_col, 'Total_Penjualan'],
                aliases=['Kecamatan:', 'Total:'],
                localize=True
            )
        ).add_to(m)

        # Hapus status loading setelah peta siap
        status_text.empty()

        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"Peta Interaktif: {pilihan_provinsi}")
            # Tangkap interaksi user
            map_output = st_folium(m, use_container_width=True)

        with col2:
            st.subheader("Statistik")
            st.metric("Total Penjualan", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
            st.dataframe(final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(10), hide_index=True)

            # -----------------------------------------------------------
            # FITUR EXPORT (Tetap Sama, karena sudah bagus)
            # -----------------------------------------------------------
            st.markdown("---")
            st.subheader("⬇️ Export View")
            format_file = st.selectbox("Format:", ["PNG", "SVG"])
            
            if st.button("Generate from Current View"):
                # Ganti spinner dengan toast kecil di pojok
                st.toast("Sedang merender gambar...") 
                
                # 1. Ambil Koordinat
                bounds = map_output.get("bounds")
                if bounds:
                    south, north = bounds['_southWest']['lat'], bounds['_northEast']['lat']
                    west, east = bounds['_southWest']['lng'], bounds['_northEast']['lng']
                else:
                    minx, miny, maxx, maxy = final_map_data.total_bounds
                    west, south, east, north = minx, miny, maxx, maxy

                # 2. Setup Plot
                fig, ax = plt.subplots(figsize=(12, 7))
                
                # Plot Peta (Warna pasti cocok karena pakai cmap & norm yg sama)
                final_map_data.plot(
                    column='Total_Penjualan',
                    cmap=cmap,
                    norm=norm,
                    ax=ax,
                    edgecolor='black',
                    linewidth=0.3
                )
                
                # 3. Potong Canvas
                ax.set_xlim(west, east)
                ax.set_ylim(south, north)
                ax.set_axis_off()
                
                # 4. Legend
                cax = inset_axes(ax, width="35%", height="2.5%", loc='upper right',
                                bbox_to_anchor=(0, -0.05, 1, 1), 
                                bbox_transform=ax.transAxes, borderpad=0)
                
                cb = fig.colorbar(
                    cm.ScalarMappable(norm=norm, cmap=cmap),
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
