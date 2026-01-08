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
        # LOGIKA BINS (DIPERBARUI: LANGSUNG DI INPUT BOX)
        # -----------------------------------------------------------
        min_val = final_map_data['Total_Penjualan'].min()
        max_val = final_map_data['Total_Penjualan'].max()
        
        # 1. Hitung Default Otomatis (Quantile)
        # Kita hitung dulu nilai idealnya supaya user tidak mulai dari nol
        try:
            default_quantiles = list(final_map_data['Total_Penjualan'].quantile([0, 0.2, 0.4, 0.6, 0.8, 1.0]))
            default_quantiles = sorted(list(set(default_quantiles))) # Hapus duplikat
            
            # Format menjadi string "0, 100, 200" untuk ditampilkan di input box
            # Kita bulatkan jadi integer (int) agar rapi di input box
            default_str = ", ".join([str(int(x)) for x in default_quantiles])
        except:
            default_str = f"{int(min_val)}, {int(max_val)}"

        # 2. Tampilkan Input Box (Langsung terisi nilai otomatis)
        st.sidebar.markdown("### Batas Nilai (Legend)")
        st.sidebar.caption(f"Rentang Data: {min_val:,.0f} - {max_val:,.0f}")
        
        user_bins = st.sidebar.text_area(
            "Edit batas nilai di bawah ini (pisahkan koma):", 
            value=default_str,
            height=100
        )
        
        # 3. Proses Nilai dari Input Box
        bins_list = None
        try:
            custom_bins = [float(x.strip()) for x in user_bins.split(',')]
            custom_bins = sorted(list(set(custom_bins)))
            
            # Validasi keamanan range
            if custom_bins[0] > min_val: custom_bins.insert(0, min_val)
            if custom_bins[-1] < max_val: custom_bins.append(max_val)
            
            if len(custom_bins) < 4:
                st.sidebar.warning("⚠️ Masukkan minimal 4 angka batas.")
                bins_list = None # Fallback ke default folium
            else:
                bins_list = custom_bins
        except:
            st.sidebar.error("⚠️ Format angka salah. Gunakan koma sebagai pemisah.")
            bins_list = None

        # -----------------------------------------------------------
        # VISUALISASI UTAMA (FOLIUM)
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
            # Tangkap interaksi user
            map_output = st_folium(m, use_container_width=True)

        with col2:
            st.subheader("Statistik")
            st.metric("Total Penjualan", f"{final_map_data['Total_Penjualan'].sum():,.0f}")
            st.dataframe(final_map_data.sort_values(by='Total_Penjualan', ascending=False)[[region_col, 'Total_Penjualan']].head(10), hide_index=True)

            # -----------------------------------------------------------
            # FITUR EXPORT: "DRAW BY CANVAS" + RAPI LEGEND
            # -----------------------------------------------------------
            st.markdown("---")
            st.subheader("⬇️ Export View")
            format_file = st.selectbox("Format:", ["PNG", "SVG"])
            
            if st.button("Generate from Current View"):
                with st.spinner("Merender ulang tampilan canvas..."):
                    
                    # 1. Ambil Koordinat View Saat Ini
                    bounds = map_output.get("bounds")
                    if bounds:
                        south, north = bounds['_southWest']['lat'], bounds['_northEast']['lat']
                        west, east = bounds['_southWest']['lng'], bounds['_northEast']['lng']
                    else:
                        minx, miny, maxx, maxy = final_map_data.total_bounds
                        west, south, east, north = minx, miny, maxx, maxy

                    # 2. Setup Matplotlib
                    fig, ax = plt.subplots(figsize=(12, 7)) # Sedikit lebih lebar
                    
                    # Gunakan BoundaryNorm agar warna tegas (discrete) sesuai bins
                    cmap_base = plt.get_cmap(color_palette)
                    if bins_list:
                        # Membuat colormap discrete (kotak-kotak)
                        norm = mcolors.BoundaryNorm(bins_list, cmap_base.N)
                    else:
                        norm = mcolors.Normalize(vmin=min_val, vmax=max_val)

                    # 3. Plot Peta
                    final_map_data.plot(
                        column='Total_Penjualan',
                        cmap=cmap_base,
                        norm=norm,
                        ax=ax,
                        edgecolor='black',
                        linewidth=0.3
                    )
                    
                    # 4. Potong Sesuai Canvas
                    ax.set_xlim(west, east)
                    ax.set_ylim(south, north)
                    ax.set_axis_off()
                    
                    # 5. CUSTOM LEGEND (YANG LEBIH RAPI)
                    # Posisi: Upper Right, lebar 35% dari peta, tinggi 2.5%
                    cax = inset_axes(ax,
                                    width="35%", 
                                    height="2.5%", 
                                    loc='upper right',
                                    bbox_to_anchor=(0, -0.05, 1, 1), 
                                    bbox_transform=ax.transAxes,
                                    borderpad=0)
                    
                    # spacing='uniform' membuat kotak warna sama besar (Rapi)
                    cb = fig.colorbar(
                        cm.ScalarMappable(norm=norm, cmap=cmap_base),
                        cax=cax,
                        orientation='horizontal',
                        spacing='uniform' 
                    )
                    
                    # Styling Text Legenda
                    # Format angka biar gak kepanjangan (opsional, tapi pakai raw dulu)
                    cb.ax.tick_params(labelsize=6, color='black', labelcolor='black') 
                    
                    # Judul Legenda (Padding diperbesar agar tidak numpuk)
                    cb.set_label('Total Penjualan (Z)', size=8, weight='bold', labelpad=7) 
                    
                    # Background Transparan
                    fig.patch.set_alpha(0.0)
                    ax.patch.set_alpha(0.0)

                    # 6. Simpan
                    img_buffer = io.BytesIO()
                    plt.savefig(
                        img_buffer, 
                        format=format_file.lower(), 
                        transparent=True, 
                        dpi=200 if format_file == "PNG" else None, 
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
