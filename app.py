import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import matplotlib.pyplot as plt
import io
from streamlit_folium import st_folium
from folium.plugins import Fullscreen

# Konfigurasi Halaman
st.set_page_config(page_title="Peta Penjualan Rokok", layout="wide")

st.title("🗺️ Peta Interaktif & Export Vector")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_excel = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    uploaded_map = st.file_uploader("Upload Peta (.geojson/.shp)", type=["geojson", "json", "shp"])

    st.header("2. Pengaturan Tampilan")
    # Pilihan Palet Warna
    color_palette = st.selectbox(
        "Pilih Tema Warna:",
        ["YlOrRd", "PuBu", "YlGn", "OrRd", "RdPu", "Spectral", "coolwarm"],
        index=0
    )
    
    # Pilihan Mode Klasifikasi
    classification_mode = st.radio(
        "Metode Pembagian Kelas (Legend):",
        ["Otomatis (Quantile)", "Manual (Custom)"]
    )

# --- PROSES UTAMA ---
if uploaded_excel and uploaded_map:
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
        # LOGIKA BINS (PERBAIKAN UTAMA)
        # -----------------------------------------------------------
        min_val = final_map_data['Total_Penjualan'].min()
        max_val = final_map_data['Total_Penjualan'].max()
        bins_list = None 

        if classification_mode == "Otomatis (Quantile)":
            # Hitung 6 titik pembagi untuk mendapatkan 5 kelas warna (0%, 20%, 40%, 60%, 80%, 100%)
            # Ini menjamin pembagian warna merata (Quantile)
            try:
                quantiles = list(final_map_data['Total_Penjualan'].quantile([0, 0.2, 0.4, 0.6, 0.8, 1.0]))
                # Hapus duplikat jika datanya banyak yang 0
                bins_list = sorted(list(set(quantiles)))
                # Jika hasil quantile kurang dari 3 kelas, fallback ke linear
                if len(bins_list) < 4:
                    bins_list = None 
            except:
                bins_list = None # Gunakan default folium jika gagal

        elif classification_mode == "Manual (Custom)":
            st.sidebar.info(f"Rentang Data: {min_val:,.0f} s/d {max_val:,.0f}")
            
            # Default value untuk input box
            default_bins = f"{min_val}, {min_val + (max_val-min_val)/3:.0f}, {min_val + 2*(max_val-min_val)/3:.0f}, {max_val}"
            
            user_bins = st.sidebar.text_input("Masukkan batas nilai (pisahkan koma):", value=default_bins)
            
            try:
                custom_bins = [float(x.strip()) for x in user_bins.split(',')]
                custom_bins = sorted(list(set(custom_bins))) # Urutkan & Hapus duplikat
                
                # Pastikan mencakup min & max
                if custom_bins[0] > min_val: custom_bins.insert(0, min_val)
                if custom_bins[-1] < max_val: custom_bins.append(max_val)
                
                # CEK ERROR MINIMAL WARNA
                if len(custom_bins) < 4:
                    st.sidebar.warning("⚠️ Minimal harus ada 4 angka batas untuk menghasilkan 3 warna. Menggunakan mode otomatis sementara.")
                    bins_list = None
                else:
                    bins_list = custom_bins
                    st.sidebar.success(f"Menggunakan {len(bins_list)-1} kelas warna.")
            except:
                st.sidebar.error("Format angka salah.")

        # -----------------------------------------------------------
        # VISUALISASI FOLIUM (INTERAKTIF)
        # -----------------------------------------------------------
        centroid = final_map_data.geometry.centroid
        m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=8, tiles="CartoDB positron")

        folium.Choropleth(
            geo_data=final_map_data,
            data=final_map_data,
            columns=[region_col, "Total_Penjualan"],
            key_on=f"feature.properties.{region_col}",
            fill_color=color_palette,
            fill_opacity=0.7,
            line_opacity=0.2,
            legend_name="Total Penjualan (Z)",
            bins=bins_list, 
            highlight=True
        ).add_to(m)

        folium.GeoJson(
            final_map_data,
            style_function=lambda x: {'fillColor': '#00000000', 'color': '#00000000'},
            tooltip=folium.GeoJsonTooltip(
                fields=[region_col, 'Total_Penjualan'],
                aliases=['Kecamatan:', 'Total:'],
                localize=True
            )
        ).add_to(m)

        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"Peta Interaktif: {pilihan_provinsi}")
            st_folium(m, use_container_width=True)

        with col2:
            st.subheader("Statistik")
            st.metric("Total Penjualan", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
            st.dataframe(final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(10), hide_index=True)

            # -----------------------------------------------------------
            # FITUR BARU: EXPORT VECTOR (PNG/SVG) TRANSPARAN
            # -----------------------------------------------------------
            st.markdown("---")
            st.subheader("⬇️ Download Peta")
            st.write("Download peta statis resolusi tinggi dengan background transparan.")
            
            format_file = st.selectbox("Format:", ["PNG", "SVG", "PDF"])
            
            if st.button("Generate File Download"):
                with st.spinner("Sedang membuat file vector..."):
                    # Membuat Plot Matplotlib (Backend untuk Vector)
                    fig, ax = plt.subplots(figsize=(10, 6))
                    
                    # Plot Peta
                    final_map_data.plot(
                        column='Total_Penjualan',
                        cmap=color_palette,
                        legend=True,
                        legend_kwds={'label': "Total Penjualan (Z)", 'orientation': "horizontal"},
                        ax=ax,
                        edgecolor='black',
                        linewidth=0.5
                    )
                    
                    # Hilangkan Axis (Kotak Koordinat) agar bersih
                    ax.set_axis_off()
                    ax.set_title(f"Peta Penjualan - {pilihan_provinsi}", fontsize=15)
                    
                    # Simpan ke Buffer (Memori)
                    img_buffer = io.BytesIO()
                    plt.savefig(img_buffer, format=format_file.lower(), transparent=True, dpi=300, bbox_inches='tight')
                    img_buffer.seek(0)
                    
                    st.download_button(
                        label=f"Klik untuk Download {format_file}",
                        data=img_buffer,
                        file_name=f"peta_penjualan_{pilihan_provinsi}.{format_file.lower()}",
                        mime=f"image/{format_file.lower()}" if format_file != "PDF" else "application/pdf"
                    )

    except Exception as e:
        st.error(f"Terjadi kesalahan: {e}")
else:
    st.info("Silakan upload data Excel dan Shapefile di sidebar.")
