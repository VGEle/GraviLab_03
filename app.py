"""Primer prototipo web de GraviLab."""

from __future__ import annotations

import csv
import io
import math
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

st.subheader("Registro de mediciones")
st.write(
    "Registra la longitud del péndulo y el tiempo de 10 oscilaciones para cada "
    "repetición. Para completar la serie se requieren al menos 6 longitudes y "
    "entre 3 y 5 repeticiones por longitud."
)

if "mediciones_registradas" not in st.session_state:
    st.session_state.mediciones_registradas = []

with st.form("form_registro_datos"):
    columna_longitud, columna_tiempo, columna_repeticion = st.columns(3)
    with columna_longitud:
        longitud_ingresada = st.text_input("Longitud")
        unidad_longitud = st.selectbox("Unidad de longitud", ["", "m", "cm", "mm"])
    with columna_tiempo:
        tiempo_ingresado = st.text_input("Tiempo de 10 oscilaciones")
        unidad_tiempo = st.selectbox("Unidad de tiempo", ["", "s"])
    with columna_repeticion:
        repeticion_ingresada = st.text_input("Número de repetición")
    guardar_medicion = st.form_submit_button("Agregar medición", type="primary")

if guardar_medicion:
    errores: list[str] = []
    longitud_m: float | None = None
    tiempo_s: float | None = None
    repeticion: int | None = None

    if not longitud_ingresada.strip():
        errores.append("Ingresa la longitud.")
    elif unidad_longitud not in {"m", "cm", "mm"}:
        errores.append("Selecciona una unidad válida para la longitud.")
    else:
        try:
            longitud_valor = float(longitud_ingresada.strip().replace(",", "."))
            if not math.isfinite(longitud_valor) or longitud_valor <= 0:
                errores.append("La longitud debe ser un número mayor que cero.")
            else:
                factor_longitud = {"m": 1.0, "cm": 0.01, "mm": 0.001}[unidad_longitud]
                longitud_convertida = round(longitud_valor * factor_longitud, 9)
                if longitud_convertida <= 0:
                    errores.append("La longitud convertida a metros debe ser mayor que cero.")
                else:
                    longitud_m = longitud_convertida
        except ValueError:
            errores.append("La longitud debe ser un valor numérico válido.")

    if not tiempo_ingresado.strip():
        errores.append("Ingresa el tiempo de 10 oscilaciones.")
    elif unidad_tiempo != "s":
        errores.append("Selecciona la unidad de tiempo en segundos (s).")
    else:
        try:
            tiempo_s = float(tiempo_ingresado.strip().replace(",", "."))
            if not math.isfinite(tiempo_s) or tiempo_s <= 0:
                errores.append("El tiempo debe ser un número mayor que cero.")
        except ValueError:
            errores.append("El tiempo debe ser un valor numérico válido.")

    if not repeticion_ingresada.strip():
        errores.append("Ingresa el número de repetición.")
    else:
        try:
            repeticion = int(repeticion_ingresada.strip())
            if not 1 <= repeticion <= 5:
                errores.append("El número de repetición debe estar entre 1 y 5.")
        except ValueError:
            errores.append("El número de repetición debe ser un entero entre 1 y 5.")

    if not errores and longitud_m is not None and tiempo_s is not None and repeticion is not None:
        mediciones = st.session_state.mediciones_registradas
        repeticiones_longitud = [
            medicion for medicion in mediciones if medicion["longitud_m"] == longitud_m
        ]
        if any(medicion["repeticion"] == repeticion for medicion in repeticiones_longitud):
            errores.append("Ese número de repetición ya existe para esta longitud.")
        elif len(repeticiones_longitud) >= 5:
            errores.append("Cada longitud admite un máximo de 5 repeticiones.")
        else:
            mediciones.append(
                {
                    "longitud_m": longitud_m,
                    "tiempo_10_oscilaciones_s": tiempo_s,
                    "repeticion": repeticion,
                }
            )
            st.success("Medición agregada.")

    for error in errores:
        st.error(error)

mediciones = st.session_state.mediciones_registradas
if mediciones:
    longitudes = sorted({medicion["longitud_m"] for medicion in mediciones})
    longitudes_completas = sum(
        sum(medicion["longitud_m"] == longitud for medicion in mediciones) >= 3
        for longitud in longitudes
    )
    st.caption(
        f"Longitudes registradas: {len(longitudes)} (mínimo 6) · "
        f"Longitudes con al menos 3 repeticiones: {longitudes_completas}"
    )
    if len(longitudes) >= 6 and longitudes_completas == len(longitudes):
        st.success("La serie cumple el mínimo de 6 longitudes y 3 repeticiones por longitud.")
    else:
        st.info("Continúa agregando mediciones hasta completar al menos 6 longitudes con 3 repeticiones cada una.")

    st.dataframe(
        sorted(mediciones, key=lambda medicion: (medicion["longitud_m"], medicion["repeticion"])),
        use_container_width=True,
        hide_index=True,
    )
    salida_csv = io.StringIO()
    escritor_csv = csv.DictWriter(
        salida_csv,
        fieldnames=["longitud_m", "tiempo_10_oscilaciones_s", "repeticion"],
    )
    escritor_csv.writeheader()
    escritor_csv.writerows(mediciones)
    st.download_button(
        "Descargar mediciones CSV",
        data=salida_csv.getvalue().encode("utf-8"),
        file_name="gravilab_mediciones.csv",
        mime="text/csv",
    )
    if st.button("Borrar todas las mediciones"):
        st.session_state.mediciones_registradas = []
        st.rerun()

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
