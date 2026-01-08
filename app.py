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

# Konfigurasi Halaman
st.set_page_config(page_title="Peta Penjualan Rokok", layout="wide")

st.title("🗺️ Peta Interaktif & Export Canvas Style")

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_excel = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])
    uploaded_map = st.file_uploader("Upload Peta (.geojson/.shp)", type=["geojson", "json", "shp"])

    st.header("2. Pengaturan Tampilan")
    color_palette = st.selectbox(
        "Pilih Tema Warna:",
        ["YlOrRd", "PuBu", "YlGn", "OrRd", "RdPu", "Spectral", "coolwarm"],
        index=0
    )
    
    classification_mode = st.radio(
        "Metode Pembagian Kelas:",
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
        # LOGIKA BINS
        # -----------------------------------------------------------
        min_val = final_map_data['Total_Penjualan'].min()
        max_val = final_map_data['Total_Penjualan'].max()
        bins_list = None 

        if classification_mode == "Otomatis (Quantile)":
            try:
                quantiles = list(final_map_data['Total_Penjualan'].quantile([0, 0.2, 0.4, 0.6, 0.8, 1.0]))
                bins_list = sorted(list(set(quantiles)))
                if len(bins_list) < 4: bins_list = None 
            except:
                bins_list = None 

        elif classification_mode == "Manual (Custom)":
            st.sidebar.info(f"Rentang: {min_val:,.0f} - {max_val:,.0f}")
            default_bins = f"{min_val}, {min_val + (max_val-min_val)/3:.0f}, {min_val + 2*(max_val-min_val)/3:.0f}, {max_val}"
            user_bins = st.sidebar.text_input("Batas nilai (pisahkan koma):", value=default_bins)
            
            try:
                custom_bins = [float(x.strip()) for x in user_bins.split(',')]
                custom_bins = sorted(list(set(custom_bins)))
                if custom_bins[0] > min_val: custom_bins.insert(0, min_val)
                if custom_bins[-1] < max_val: custom_bins.append(max_val)
                
                if len(custom_bins) < 4:
                    st.sidebar.warning("⚠️ Minimal 4 batas. Menggunakan mode otomatis.")
                    bins_list = None
                else:
                    bins_list = custom_bins
            except:
                st.sidebar.error("Format angka salah.")

        # -----------------------------------------------------------
        # VISUALISASI UTAMA
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
            # PENTING: Kita tampung output st_folium ke variabel 'map_output'
            # untuk menangkap posisi zoom/geser user terakhir
            map_output = st_folium(m, use_container_width=True)

        with col2:
            st.subheader("Statistik")
            st.metric("Total Penjualan", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
            st.dataframe(final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(10), hide_index=True)

            # -----------------------------------------------------------
            # FITUR EXPORT: "DRAW BY CANVAS" + COMPACT LEGEND
            # -----------------------------------------------------------
            st.markdown("---")
            st.subheader("⬇️ Export View")
            st.write("Download tampilan peta sesuai zoom saat ini (Canvas Style).")
            
            format_file = st.selectbox("Format:", ["PNG", "SVG"])
            
            if st.button("Generate from Current View"):
                with st.spinner("Sedang merender ulang tampilan (Canvas)..."):
                    
                    # 1. Ambil Koordinat Batas (Bounds) dari Interaksi User Terakhir
                    bounds = map_output.get("bounds")
                    if bounds:
                        south = bounds['_southWest']['lat']
                        north = bounds['_northEast']['lat']
                        west = bounds['_southWest']['lng']
                        east = bounds['_northEast']['lng']
                    else:
                        # Jika user belum menyentuh peta, pakai batas default data
                        minx, miny, maxx, maxy = final_map_data.total_bounds
                        west, south, east, north = minx, miny, maxx, maxy

                    # 2. Siapkan Plotting Matplotlib (Backend Vector)
                    # Rasio aspek disesuaikan dengan map view
                    fig, ax = plt.subplots(figsize=(10, 6))
                    
                    # Logika Warna (Normalize) agar sesuai dengan interaktif
                    cmap = plt.get_cmap(color_palette)
                    if bins_list:
                        norm = mcolors.BoundaryNorm(bins_list, cmap.N)
                    else:
                        norm = mcolors.Normalize(vmin=min_val, vmax=max_val)

                    # 3. Plot Peta
                    final_map_data.plot(
                        column='Total_Penjualan',
                        cmap=cmap,
                        norm=norm,
                        ax=ax,
                        edgecolor='black',
                        linewidth=0.3
                    )
                    
                    # 4. POTONG SESUAI CANVAS (Draw by Canvas)
                    ax.set_xlim(west, east)
                    ax.set_ylim(south, north)
                    ax.set_axis_off() # Hilangkan kotak koordinat
                    
                    # 5. CUSTOM LEGEND (POJOK KANAN ATAS - COMPACT)
                    # Membuat axis kecil melayang di dalam axis utama (Inset Axes)
                    # [x, y, width, height] relatif terhadap axis utama (0-1)
                    # Posisi (0.65, 0.95) = Pojok Kanan Atas
                    cax = inset_axes(ax,
                                    width="30%",  # Lebar colorbar 30% dari lebar peta
                                    height="3%",  # Tinggi colorbar tipis (3%)
                                    loc='upper right',
                                    bbox_to_anchor=(0, -0.05, 1, 1), # Sedikit geser ke bawah dari batas atas
                                    bbox_transform=ax.transAxes,
                                    borderpad=0)
                    
                    # Gambar Colorbar Horizontal
                    cb = fig.colorbar(
                        cm.ScalarMappable(norm=norm, cmap=cmap),
                        cax=cax,
                        orientation='horizontal',
                        spacing='proportional'
                    )
                    
                    # Styling Legenda agar kecil dan rapi
                    cb.ax.tick_params(labelsize=6, color='black') # Ukuran font kecil
                    cb.set_label('Total Penjualan (Z)', size=7, labelpad=-25, y=1.5) # Label di atas bar
                    
                    # Transparansi Background
                    fig.patch.set_alpha(0.0)
                    ax.patch.set_alpha(0.0)

                    # 6. Simpan ke Buffer
                    img_buffer = io.BytesIO()
                    plt.savefig(
                        img_buffer, 
                        format=format_file.lower(), 
                        transparent=True, 
                        dpi=150 if format_file == "PNG" else None, 
                        bbox_inches='tight',
                        pad_inches=0.1
                    )
                    img_buffer.seek(0)
                    
                    st.download_button(
                        label=f"Download {format_file}",
                        data=img_buffer,
                        file_name=f"peta_canvas_{pilihan_provinsi}.{format_file.lower()}",
                        mime=f"image/{format_file.lower()}" if format_file != "SVG" else "image/svg+xml"
                    )

    except Exception as e:
        st.error(f"Terjadi kesalahan: {e}")
else:
    st.info("Silakan upload data Excel dan Shapefile di sidebar.")
