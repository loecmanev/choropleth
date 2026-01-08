import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen

st.set_page_config(page_title="Peta Penjualan Rokok", layout="wide")

st.title("🗺️ Peta Interaktif Penjualan Rokok - Kustomisasi Legenda")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_excel = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    uploaded_map = st.file_uploader("Upload Peta (.geojson/.shp)", type=["geojson", "json", "shp"])

    st.header("2. Pengaturan Tampilan")
    # Pilihan Palet Warna
    color_palette = st.selectbox(
        "Pilih Tema Warna:",
        ["YlOrRd", "PuBu", "YlGn", "OrRd", "RdPu"],
        index=0,
        help="YlOrRd = Kuning ke Merah, PuBu = Ungu ke Biru, YlGn = Kuning ke Hijau"
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
        # LOGIKA KUSTOMISASI BINS (BATAS NILAI)
        # -----------------------------------------------------------
        min_val = final_map_data['Total_Penjualan'].min()
        max_val = final_map_data['Total_Penjualan'].max()
        
        # Default bins = None (biarkan Folium menghitung otomatis)
        bins_list = None 
        
        if classification_mode == "Manual (Custom)":
            st.sidebar.info(f"Rentang Data: {min_val:,.0f} s/d {max_val:,.0f}")
            
            # Input user berupa text
            user_bins = st.sidebar.text_input(
                "Masukkan batas nilai (pisahkan koma):", 
                value=f"{min_val},{min_val + (max_val-min_val)/2},{max_val}"
            )
            
            try:
                # Ubah text "100, 200, 300" menjadi list [100, 200, 300]
                custom_bins = [float(x.strip()) for x in user_bins.split(',')]
                
                # Validasi: Bins harus urut
                custom_bins = sorted(custom_bins)
                
                # Pastikan mencakup min dan max data
                if custom_bins[0] > min_val:
                    custom_bins.insert(0, min_val)
                if custom_bins[-1] < max_val:
                    custom_bins.append(max_val)
                
                bins_list = custom_bins
                st.sidebar.success(f"Batas dipakai: {bins_list}")
                
            except ValueError:
                st.sidebar.error("Format salah! Masukkan hanya angka dipisah koma.")

        # -----------------------------------------------------------
        # VISUALISASI
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
            bins=bins_list, # <--- INI PARAMETER KUNCINYA
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

        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"Peta Sebaran: {pilihan_provinsi}")
            st_folium(m, use_container_width=True)

        with col2:
            st.subheader("Statistik")
            st.metric("Total Penjualan", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
            st.write("Top 10 Kecamatan:")
            st.dataframe(final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(10), hide_index=True)

    except Exception as e:
        st.error(f"Error: {e}")
else:
    st.info("Silakan upload data di sidebar.")
