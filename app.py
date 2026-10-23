"""Primer prototipo web de GraviLab."""

from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import streamlit as st
from PIL import Image

from seguimiento import procesar_video

try:
    from streamlit_image_coordinates import streamlit_image_coordinates

    COMPONENTE_CLIC = True
except ImportError:
    COMPONENTE_CLIC = False


st.set_page_config(page_title="GraviLab - Seguimiento de video", layout="wide")

st.title("GraviLab: seguimiento del péndulo")
st.write("Carga un video y haz clic directamente sobre la lenteja para iniciar el seguimiento.")

video_cargado = st.file_uploader(
    "Carga un video del péndulo",
    type=["mp4", "mov", "avi", "m4v"],
    help="Usa una cámara fija y una lenteja que contraste con el fondo.",
)

if video_cargado is None:
    st.info("Carga un video para comenzar.")
    st.stop()

with tempfile.NamedTemporaryFile(delete=False, suffix=Path(video_cargado.name).suffix or ".mp4") as archivo_temporal:
    archivo_temporal.write(video_cargado.getbuffer())
    ruta_video = Path(archivo_temporal.name)

captura = cv2.VideoCapture(str(ruta_video))
ok, primer_frame = captura.read()
fps = captura.get(cv2.CAP_PROP_FPS)
ancho = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH))
alto = int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT))
captura.release()

if not ok:
    st.error("No se pudo leer el video. Prueba con un archivo MP4 o MOV válido.")
    st.stop()

st.caption(f"Resolución: {ancho} × {alto} px · FPS detectados: {fps:.2f}")
st.subheader("Selecciona la lenteja")

# La imagen se reduce para que no ocupe toda la página. Las coordenadas del
# clic se convierten de nuevo a la resolución original del video.
ancho_maximo = 800
escala = min(1.0, ancho_maximo / ancho)
ancho_vista = max(1, int(ancho * escala))
alto_vista = max(1, int(alto * escala))

if "lenteja_x" not in st.session_state:
    st.session_state.lenteja_x = ancho // 2
if "lenteja_y" not in st.session_state:
    st.session_state.lenteja_y = alto // 2

radio_muestra = st.slider("Radio de muestra (px)", 4, 50, 12)
tolerancia_tono = st.slider("Tolerancia de color", 5, 45, 18)

vista_seleccion = cv2.resize(primer_frame, (ancho_vista, alto_vista), interpolation=cv2.INTER_AREA)
x_vista = int(st.session_state.lenteja_x * escala)
y_vista = int(st.session_state.lenteja_y * escala)
cv2.circle(vista_seleccion, (x_vista, y_vista), max(4, int(radio_muestra * escala)), (0, 0, 255), 2)
cv2.drawMarker(vista_seleccion, (x_vista, y_vista), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
vista_rgb = cv2.cvtColor(vista_seleccion, cv2.COLOR_BGR2RGB)

if COMPONENTE_CLIC:
    st.caption("Haz clic sobre el centro de la lenteja. La cruz amarilla muestra la selección actual.")
    clic = streamlit_image_coordinates(Image.fromarray(vista_rgb), key="selector_lenteja")
    if clic is not None:
        st.session_state.lenteja_x = min(ancho - 1, max(0, round(clic["x"] / escala)))
        st.session_state.lenteja_y = min(alto - 1, max(0, round(clic["y"] / escala)))
else:
    st.warning("Falta el componente de selección por clic. Usa temporalmente estos controles o instala las dependencias del proyecto.")
    st.image(vista_rgb, caption="Fotograma de selección", width=ancho_vista)
    st.session_state.lenteja_x = st.slider("Coordenada X", 0, max(0, ancho - 1), st.session_state.lenteja_x)
    st.session_state.lenteja_y = st.slider("Coordenada Y", 0, max(0, alto - 1), st.session_state.lenteja_y)

x_inicial = st.session_state.lenteja_x
y_inicial = st.session_state.lenteja_y
st.info(f"Selección actual: X = {x_inicial} px, Y = {y_inicial} px")

st.subheader("Procesamiento")
if st.button("Seguir lenteja", type="primary"):
    with tempfile.NamedTemporaryFile(delete=False, suffix="_gravilab_anotado.mp4") as archivo_salida:
        ruta_salida = Path(archivo_salida.name)

    with st.spinner("Procesando el video fotograma a fotograma..."):
        try:
            resultado = procesar_video(
                ruta_video,
                ruta_salida,
                x_inicial=x_inicial,
                y_inicial=y_inicial,
                radio_muestra=radio_muestra,
                tolerancia_tono=tolerancia_tono,
            )
        except Exception as error:
            st.error(f"No se pudo procesar el video: {error}")
            st.stop()

    datos = resultado.datos
    porcentaje_detectado = 100 * datos["detectado"].mean()
    datos_validos = datos[datos["detectado"]].copy()

    metrica_1, metrica_2, metrica_3 = st.columns(3)
    metrica_1.metric("Fotogramas", f"{len(datos):,}")
    metrica_2.metric("FPS", f"{resultado.fps:.2f}")
    metrica_3.metric("Detección válida", f"{porcentaje_detectado:.1f}%")

    if porcentaje_detectado < 80:
        st.warning("La detección es baja. Prueba con mejor iluminación, más contraste o ajusta las coordenadas y la tolerancia de color.")
    else:
        st.success("La lenteja fue seguida durante la mayor parte del video.")

    st.subheader("Video con trayectoria")
    if resultado.video_anotado.suffix.lower() == ".mp4":
        st.video(resultado.video_anotado.read_bytes())
    else:
        st.info("El sistema generó el video en formato AVI porque no encontró un códec MP4 compatible.")
    st.download_button(
        "Descargar video anotado",
        data=resultado.video_anotado.read_bytes(),
        file_name=resultado.video_anotado.name,
        mime="video/mp4" if resultado.video_anotado.suffix.lower() == ".mp4" else "video/x-msvideo",
    )

    if len(datos_validos) >= 2:
        st.subheader("Posición horizontal frente al tiempo")
        figura, eje = plt.subplots(figsize=(10, 4))
        eje.plot(datos_validos["tiempo_s"], datos_validos["x_px"], color="#1769aa", linewidth=1.5)
        eje.set_xlabel("Tiempo (s)")
        eje.set_ylabel("Posición horizontal (px)")
        eje.grid(alpha=0.25)
        st.pyplot(figura, clear_figure=True)

        st.subheader("Datos extraídos")
        st.dataframe(datos, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar datos CSV",
            data=datos.to_csv(index=False).encode("utf-8"),
            file_name="gravilab_trayectoria.csv",
            mime="text/csv",
        )
    else:
        st.error("No hubo suficientes detecciones para construir la gráfica.")
