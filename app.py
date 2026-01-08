import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen

st.set_page_config(page_title="Peta Penjualan Rokok", layout="wide")

st.title("🗺️ Peta Interaktif Penjualan Rokok - Filter Provinsi")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_excel = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    uploaded_map = st.file_uploader("Upload Peta (.geojson/.shp)", type=["geojson", "json", "shp"])

# --- PROSES UTAMA ---
if uploaded_excel and uploaded_map:
    try:
        # 1. BACA DATA
        df = pd.read_excel(uploaded_excel)
        gdf_raw = gpd.read_file(uploaded_map)

        # Pastikan CRS ke WGS84 (Standar Web)
        if gdf_raw.crs != "EPSG:4326":
            gdf_raw = gdf_raw.to_crs("EPSG:4326")

        # -----------------------------------------------------------
        # FITUR BARU: FILTER PROVINSI
        # -----------------------------------------------------------
        # Kita cari kolom yang berisi nama Provinsi. Di GADM biasanya 'NAME_1'
        # Jika tidak ada, kita coba cari kolom lain.
        if 'NAME_1' in gdf_raw.columns:
            list_provinsi = sorted(gdf_raw['NAME_1'].unique())
            
            st.sidebar.header("2. Fokus Wilayah")
            pilihan_provinsi = st.sidebar.selectbox("Pilih Provinsi:", list_provinsi)
            
            # Filter peta hanya ambil provinsi yang dipilih
            gdf_kecamatan = gdf_raw[gdf_raw['NAME_1'] == pilihan_provinsi].copy()
            st.success(f"Menampilkan peta khusus: {pilihan_provinsi}")
        else:
            # Jika kolom NAME_1 tidak ditemukan, pakai semua data
            gdf_kecamatan = gdf_raw
            st.warning("Kolom 'NAME_1' (Provinsi) tidak ditemukan. Menampilkan seluruh peta.")

        # Konversi Excel ke Titik Koordinat
        gdf_points = gpd.GeoDataFrame(
            df, 
            geometry=gpd.points_from_xy(df.longitude, df.latitude),
            crs="EPSG:4326"
        )

        # 2. SPATIAL JOIN (Gabungkan Titik ke Peta yang sudah difilter)
        joined = gpd.sjoin(gdf_points, gdf_kecamatan, how="inner", predicate="within")

        # 3. AGREGASI DATA
        # Gunakan NAME_3 untuk Kecamatan (sesuai standar GADM Level 3)
        region_col = 'NAME_3' 
        
        # Cek apakah kolom NAME_3 ada, jika tidak, minta user pilih
        if region_col not in gdf_kecamatan.columns:
             region_col = st.selectbox("Pilih Kolom Nama Kecamatan:", gdf_kecamatan.columns)

        agg_data = joined.groupby(region_col)['Z'].sum().reset_index()
        agg_data.columns = [region_col, 'Total_Penjualan']

        # Gabungkan hasil hitungan ke Peta Wilayah
        final_map_data = gdf_kecamatan.merge(agg_data, on=region_col, how="left")
        final_map_data['Total_Penjualan'] = final_map_data['Total_Penjualan'].fillna(0)

        # -----------------------------------------------------------
        # FITUR BARU: AUTO ZOOM (Mencari titik tengah provinsi)
        # -----------------------------------------------------------
        # Hitung titik tengah dari wilayah yang dipilih
        centroid = final_map_data.geometry.centroid
        tengah_y = centroid.y.mean()
        tengah_x = centroid.x.mean()

        # --- VISUALISASI ---
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader(f"Peta Sebaran: {pilihan_provinsi if 'NAME_1' in gdf_raw.columns else 'Semua'}")
            
            # Set peta agar langsung zoom ke titik tengah provinsi
            m = folium.Map(location=[tengah_y, tengah_x], zoom_start=8, tiles="CartoDB positron")

            folium.Choropleth(
                geo_data=final_map_data,
                data=final_map_data,
                columns=[region_col, "Total_Penjualan"],
                key_on=f"feature.properties.{region_col}",
                fill_color="YlOrRd",
                fill_opacity=0.7,
                line_opacity=0.2,
                legend_name="Total Penjualan (Z)",
                highlight=True
            ).add_to(m)

            # Tooltip
            folium.GeoJson(
                final_map_data,
                style_function=lambda x: {'fillColor': '#00000000', 'color': '#00000000'},
                tooltip=folium.GeoJsonTooltip(
                    fields=[region_col, 'Total_Penjualan'],
                    aliases=['Kecamatan:', 'Total Penjualan:'],
                    localize=True
                )
            ).add_to(m)

            st_folium(m, use_container_width=True)

        with col2:
            st.subheader("Statistik Wilayah")
            total_sales = final_map_data['Total_Penjualan'].sum()
            st.metric("Total Penjualan", f"{total_sales:,.0f}")
            
            # Tampilkan Top 10 Kecamatan di provinsi tersebut
            top_kec = final_map_data[[region_col, 'Total_Penjualan']].sort_values(by='Total_Penjualan', ascending=False).head(10)
            st.dataframe(top_kec, hide_index=True)

    except Exception as e:
        st.error(f"Terjadi kesalahan: {e}")
else:
    st.info("Silakan upload file Excel dan File Peta (GeoJSON/SHP).")