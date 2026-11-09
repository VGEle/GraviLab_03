"""Primer prototipo web de GraviLab."""

from __future__ import annotations

import hashlib
import io
import math
import tempfile
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image

from analisis import (
    GRAVEDAD_REFERENCIA_M_S2,
    calcular_analisis,
    calcular_periodo_trayectoria,
    calibrar_escala_m_por_pixel,
    detectar_datos_atipicos,
    generar_conclusiones,
)
from seguimiento import procesar_video

try:
    from streamlit_image_coordinates import streamlit_image_coordinates

    COMPONENTE_CLIC = True
except ImportError:
    COMPONENTE_CLIC = False


st.set_page_config(page_title="GraviLab - Análisis del péndulo", layout="wide")

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1280px;
        padding-top: 2.5rem;
        padding-bottom: 3rem;
    }
    .gravi-hero {
        background: linear-gradient(135deg, #102a43 0%, #176b87 100%);
        border-radius: 22px;
        padding: 2.1rem 2.4rem;
        margin-bottom: 1.5rem;
        color: #f7fbff;
        box-shadow: 0 12px 32px rgba(7, 28, 45, 0.25);
    }
    .gravi-hero .eyebrow {
        color: #9ee7dc;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
    }
    .gravi-hero h1 {
        margin: 0.25rem 0 0.35rem 0;
        font-size: clamp(2rem, 5vw, 3.5rem);
        line-height: 1.05;
    }
    .gravi-hero p {
        color: #d7f4f1;
        font-size: 1.05rem;
        margin: 0;
        max-width: 800px;
    }
    .workflow-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 1rem;
        margin: 1rem 0 2rem 0;
    }
    .workflow-card {
        border: 1px solid rgba(120, 180, 195, 0.35);
        border-radius: 16px;
        padding: 1rem 1.15rem;
        background: rgba(23, 107, 135, 0.10);
    }
    .workflow-card strong { color: #8fe3d7; }
    .workflow-card span { color: #c6d5df; font-size: 0.92rem; }
    .section-label {
        color: #63d7c6;
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-top: 1.7rem;
        margin-bottom: -0.6rem;
    }
    div[data-testid="stForm"] {
        border: 1px solid rgba(120, 180, 195, 0.28);
        border-radius: 16px;
        padding: 1rem 1.1rem 0.5rem 1.1rem;
        background: rgba(255, 255, 255, 0.025);
    }
    div[data-testid="stMetric"] {
        border: 1px solid rgba(120, 180, 195, 0.25);
        border-radius: 14px;
        padding: 0.8rem 1rem;
        background: rgba(23, 107, 135, 0.08);
    }
    div.stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #159a9c, #176b87);
        border: 0;
        color: white;
        font-weight: 700;
    }
    @media (max-width: 700px) {
        .workflow-grid { grid-template-columns: 1fr; }
        .gravi-hero { padding: 1.5rem; }
    }
    </style>
    <div class="gravi-hero">
        <div class="eyebrow">Laboratorio integrado · péndulo simple</div>
        <h1>GraviLab</h1>
        <p>Registra tus mediciones, analiza la gravedad y revisa el movimiento de la pelotilla en video.</p>
    </div>
    <div class="workflow-grid">
        <div class="workflow-card"><strong>01 · Mediciones manuales</strong><br><span>Calcula T, T², g, incertidumbre, gráficas y conclusiones.</span></div>
        <div class="workflow-card"><strong>02 · Análisis de video</strong><br><span>Sigue la pelotilla, estima su periodo y descarga la trayectoria.</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="section-label">01 · Datos del experimento</div>', unsafe_allow_html=True)
st.subheader("Registro manual de mediciones")
st.write(
    "Esta sección se usa para el análisis físico de la práctica. En cada fila se "
    "registra una longitud y el tiempo total de 10 oscilaciones. La aplicación "
    "divide ese tiempo entre 10, calcula promedios y obtiene g a partir de T² frente a L."
)
with st.expander("¿Qué debo medir y qué datos debo ingresar?"):
    st.markdown(
        "1. Mide la longitud desde el punto de suspensión hasta el centro de la pelotilla.\n"
        "2. Para esa longitud, mide con cronómetro el tiempo de **10 oscilaciones completas**.\n"
        "3. Repite la medición 3, 4 o 5 veces y cambia el número de repetición.\n"
        "4. Repite todo con al menos 6 longitudes diferentes.\n\n"
        "El registro manual y el análisis de video son complementarios: el registro "
        "manual alimenta el cálculo de la gravedad, mientras el video permite revisar "
        "la trayectoria y estimar un periodo automáticamente."
    )

if "mediciones_registradas" not in st.session_state:
    st.session_state.mediciones_registradas = []

with st.form("form_registro_datos"):
    columna_longitud, columna_tiempo, columna_repeticion = st.columns(3)
    with columna_longitud:
        longitud_ingresada = st.text_input("Longitud")
        unidad_longitud = st.selectbox("Unidad de longitud", ["cm", "m", "mm"])
    with columna_tiempo:
        tiempo_ingresado = st.text_input("Tiempo de 10 oscilaciones")
        unidad_tiempo = st.selectbox("Unidad de tiempo", ["s"])
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
longitudes = sorted({medicion["longitud_m"] for medicion in mediciones})
longitudes_completas = sum(
    sum(medicion["longitud_m"] == longitud for medicion in mediciones) >= 3
    for longitud in longitudes
)
serie_lista = len(longitudes) >= 6 and longitudes_completas == len(longitudes)
metrica_longitudes, metrica_repeticiones, metrica_estado = st.columns(3)
metrica_longitudes.metric("Longitudes", f"{min(len(longitudes), 6)}/6")
metrica_repeticiones.metric("Series completas", str(longitudes_completas))
metrica_estado.metric("Estado", "Listo para analizar" if serie_lista else "Datos en progreso")
st.progress(min(len(longitudes) / 6, 1.0), text="Progreso del conjunto experimental")
if mediciones:
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
    salida_csv = pd.DataFrame(mediciones).to_csv(
        index=False,
        sep=";",
        decimal=",",
    )
    st.caption("El CSV usa punto y coma como separador y coma decimal para abrirlo correctamente en Excel.")
    st.download_button(
        "Descargar mediciones CSV",
        data=salida_csv.encode("utf-8-sig"),
        file_name="gravilab_mediciones.csv",
        mime="text/csv; charset=utf-8",
    )
    if st.button("Borrar todas las mediciones"):
        st.session_state.mediciones_registradas = []
        st.rerun()

    st.markdown('<div class="section-label">01.2 · Resultados</div>', unsafe_allow_html=True)
    st.subheader("Análisis físico")
    if len(longitudes) < 6 or longitudes_completas != len(longitudes):
        st.info(
            "Completa al menos 6 longitudes distintas y 3 repeticiones por longitud "
            "para habilitar el análisis."
        )
    else:
        gravedad_referencia = st.number_input(
            "Gravedad de referencia (m/s²)",
            min_value=9.0,
            max_value=10.0,
            value=GRAVEDAD_REFERENCIA_M_S2,
            step=0.01,
            format="%.2f",
            help="Se propone 9,78 m/s² como referencia local para Medellín.",
        )
        resumen, parametros = calcular_analisis(mediciones, gravedad_referencia)
        datos_atipicos = detectar_datos_atipicos(mediciones)
        st.caption(
            "El periodo de cada repetición es el tiempo de 10 oscilaciones dividido entre 10. "
            "Se ajusta T² promedio frente a la longitud; la incertidumbre reportada es "
            "el error estándar de g propagado desde el error estándar de la pendiente. "
            "El error porcentual usa la gravedad de referencia seleccionada."
        )
        st.dataframe(
            resumen.rename(
                columns={
                    "longitud_m": "Longitud (m)",
                    "repeticiones": "Repeticiones",
                    "periodo_promedio_s": "Periodo promedio T (s)",
                    "desviacion_estandar_s": "Desviación estándar de T (s)",
                    "periodo_cuadrado_s2": "T² promedio (s²)",
                }
            ).round(6),
            use_container_width=True,
            hide_index=True,
        )

        metrica_pendiente, metrica_intercepto, metrica_r2 = st.columns(3)
        metrica_pendiente.metric("Pendiente", f'{parametros["pendiente"]:.6g} s²/m')
        metrica_intercepto.metric("Intercepto", f'{parametros["intercepto"]:.6g} s²')
        metrica_r2.metric("R²", f'{parametros["r_cuadrado"]:.6f}')

        if "gravedad" in parametros:
            metrica_gravedad, metrica_incertidumbre, metrica_error = st.columns(3)
            metrica_gravedad.metric("g calculada", f'{parametros["gravedad"]:.4f} m/s²')
            metrica_incertidumbre.metric(
                "Incertidumbre estándar de g",
                f'± {parametros["incertidumbre_gravedad"]:.4f} m/s²',
            )
            metrica_error.metric("Error porcentual", f'{parametros["error_porcentual"]:.2f}%')
        else:
            st.warning("La pendiente del ajuste no es positiva; no se puede calcular una g física.")

        figura_analisis, eje_analisis = plt.subplots(figsize=(8, 4))
        eje_analisis.scatter(
            resumen["longitud_m"],
            resumen["periodo_cuadrado_s2"],
            color="#1769aa",
            label="Datos experimentales",
        )
        longitudes_ajuste = np.linspace(resumen["longitud_m"].min(), resumen["longitud_m"].max(), 100)
        eje_analisis.plot(
            longitudes_ajuste,
            parametros["pendiente"] * longitudes_ajuste + parametros["intercepto"],
            color="#d1495b",
            label="Regresión lineal",
        )
        eje_analisis.set_xlabel("Longitud L (m)")
        eje_analisis.set_ylabel("Periodo al cuadrado T² (s²)")
        eje_analisis.grid(alpha=0.25)
        eje_analisis.legend()
        st.pyplot(figura_analisis, clear_figure=True)

        st.subheader("Periodo frente a la longitud")
        figura_periodo, eje_periodo = plt.subplots(figsize=(8, 4))
        desviaciones = resumen["desviacion_estandar_s"].fillna(0)
        eje_periodo.errorbar(
            resumen["longitud_m"],
            resumen["periodo_promedio_s"],
            yerr=desviaciones,
            fmt="o",
            capsize=4,
            color="#1769aa",
            label="Mediciones experimentales",
        )
        longitudes_teoricas = np.linspace(
            resumen["longitud_m"].min(), resumen["longitud_m"].max(), 200
        )
        gravedad_modelo = parametros.get("gravedad", gravedad_referencia)
        if not math.isfinite(gravedad_modelo) or gravedad_modelo <= 0:
            gravedad_modelo = gravedad_referencia
        periodos_teoricos = 2 * math.pi * np.sqrt(longitudes_teoricas / gravedad_modelo)
        eje_periodo.plot(
            longitudes_teoricas,
            periodos_teoricos,
            color="#d1495b",
            label=f"Modelo T = 2π√(L/g), g = {gravedad_modelo:.2f} m/s²",
        )
        eje_periodo.set_xlabel("Longitud L (m)")
        eje_periodo.set_ylabel("Periodo T (s)")
        eje_periodo.grid(alpha=0.25)
        eje_periodo.legend()
        st.pyplot(figura_periodo, clear_figure=True)

        st.subheader("Control de datos atípicos")
        filas_atipicas = datos_atipicos[datos_atipicos["atipico"]]
        if filas_atipicas.empty:
            st.success("No se detectaron mediciones atípicas mediante el criterio IQR por longitud.")
        else:
            st.warning(
                f"Se detectaron {len(filas_atipicas)} medición(es) atípica(s). Revisa estos valores antes de excluirlos."
            )
            st.dataframe(
                filas_atipicas.rename(
                    columns={
                        "longitud_m": "Longitud (m)",
                        "repeticion": "Repetición",
                        "periodo_s": "Periodo (s)",
                        "limite_inferior_s": "Límite inferior (s)",
                        "limite_superior_s": "Límite superior (s)",
                    }
                ).round(6),
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("Conclusiones automáticas")
        for conclusion in generar_conclusiones(resumen, parametros, datos_atipicos):
            st.markdown(f"- {conclusion}")

st.divider()
st.markdown('<div class="section-label">02 · Movimiento y video</div>', unsafe_allow_html=True)
st.subheader("Análisis de video")
st.write(
    "Carga un video con cámara fija para seguir la pelotilla, estimar su periodo "
    "y revisar la trayectoria. La calibración espacial es opcional."
)
video_cargado = st.file_uploader(
    "Carga un video del péndulo",
    type=["mp4", "mov", "avi", "m4v"],
    help="Usa una cámara fija y una pelotilla que contraste con el fondo.",
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

huella_video = hashlib.sha256(video_cargado.getbuffer()).hexdigest()
identificador_video = f"{video_cargado.name}:{huella_video}"
if st.session_state.get("identificador_video") != identificador_video:
    st.session_state.identificador_video = identificador_video
    st.session_state.pop("punto_calibracion_1", None)
    st.session_state.pop("punto_calibracion_2", None)
    st.session_state.pop("clic_calibracion", None)
    st.session_state.lenteja_x = ancho // 2
    st.session_state.lenteja_y = alto // 2

st.caption(f"Resolución: {ancho} × {alto} px · FPS detectados: {fps:.2f}")

# La imagen se reduce para que no ocupe toda la página. Las coordenadas del
# clic se convierten de nuevo a la resolución original del video.
ancho_maximo = 800
escala = min(1.0, ancho_maximo / ancho)
ancho_vista = max(1, int(ancho * escala))
alto_vista = max(1, int(alto * escala))

st.markdown('<div class="section-label">02.1 · Preparación</div>', unsafe_allow_html=True)
st.subheader("Calibración espacial")
with st.expander("Calibrar píxeles a metros con una regla o longitud conocida"):
    st.caption(
        "La calibración es opcional. Solo necesitas hacerla si quieres convertir posiciones "
        "de píxeles a metros. Usa una regla visible en el mismo plano del péndulo: haz clic "
        "en sus dos extremos, confirma cada punto e ingresa la distancia real."
    )
    st.info(
        "Los píxeles son coordenadas de la imagen, no una medición física. Por ejemplo, "
        "si una regla de 30 cm ocupa 150 píxeles, la aplicación calcula 0,002 m/px. "
        "La calibración no es necesaria para seguir la pelotilla ni para calcular el "
        "periodo; solo permite mostrar la posición en metros."
    )
    if COMPONENTE_CLIC:
        vista_calibracion = cv2.resize(
            primer_frame, (ancho_vista, alto_vista), interpolation=cv2.INTER_AREA
        )
        for numero, color in ((1, (0, 255, 0)), (2, (255, 0, 0))):
            punto = st.session_state.get(f"punto_calibracion_{numero}")
            if punto is not None:
                cv2.drawMarker(
                    vista_calibracion,
                    (int(punto[0] * escala), int(punto[1] * escala)),
                    color,
                    cv2.MARKER_CROSS,
                    24,
                    2,
                )
        vista_calibracion_rgb = cv2.cvtColor(vista_calibracion, cv2.COLOR_BGR2RGB)
        clic_calibracion = streamlit_image_coordinates(
            Image.fromarray(vista_calibracion_rgb),
            key=f"selector_calibracion_{identificador_video}",
        )
        if clic_calibracion is not None:
            st.session_state.clic_calibracion = (
                min(ancho - 1, max(0, round(clic_calibracion["x"] / escala))),
                min(alto - 1, max(0, round(clic_calibracion["y"] / escala))),
            )
        punto_seleccionado = st.session_state.get("clic_calibracion")
        st.caption(
            "Punto seleccionado: "
            + (
                f"X = {punto_seleccionado[0]} px, Y = {punto_seleccionado[1]} px"
                if punto_seleccionado
                else "haz clic sobre un extremo"
            )
        )
    else:
        st.image(
            cv2.cvtColor(primer_frame, cv2.COLOR_BGR2RGB),
            caption="Fotograma para seleccionar los puntos de referencia",
            width=ancho_vista,
        )
        columnas_punto_1 = st.columns(2)
        coordenada_x_1 = columnas_punto_1[0].number_input(
            "X del extremo 1 (px)", min_value=0, max_value=ancho - 1, value=0
        )
        coordenada_y_1 = columnas_punto_1[1].number_input(
            "Y del extremo 1 (px)", min_value=0, max_value=alto - 1, value=0
        )
        columnas_punto_2 = st.columns(2)
        coordenada_x_2 = columnas_punto_2[0].number_input(
            "X del extremo 2 (px)", min_value=0, max_value=ancho - 1, value=min(100, ancho - 1)
        )
        coordenada_y_2 = columnas_punto_2[1].number_input(
            "Y del extremo 2 (px)", min_value=0, max_value=alto - 1, value=0
        )
        st.session_state.punto_calibracion_1 = (coordenada_x_1, coordenada_y_1)
        st.session_state.punto_calibracion_2 = (coordenada_x_2, coordenada_y_2)

    if COMPONENTE_CLIC:
        columna_extremo_1, columna_extremo_2, columna_reiniciar = st.columns(3)
        if columna_extremo_1.button("Confirmar extremo 1", key="guardar_extremo_1"):
            if "clic_calibracion" in st.session_state:
                st.session_state.punto_calibracion_1 = st.session_state.clic_calibracion
            else:
                st.error("Haz clic en el primer extremo de la referencia.")
        if columna_extremo_2.button("Confirmar extremo 2", key="guardar_extremo_2"):
            if "clic_calibracion" in st.session_state:
                st.session_state.punto_calibracion_2 = st.session_state.clic_calibracion
            else:
                st.error("Haz clic en el segundo extremo de la referencia.")
        if columna_reiniciar.button("Reiniciar puntos", key="reiniciar_calibracion"):
            st.session_state.pop("punto_calibracion_1", None)
            st.session_state.pop("punto_calibracion_2", None)

    columna_longitud_real, columna_unidad_real = st.columns(2)
    with columna_longitud_real:
        longitud_referencia_ingresada = st.text_input(
            "Distancia real entre los extremos",
            value="",
            placeholder="Ejemplo: 30",
            key="longitud_referencia",
        )
    with columna_unidad_real:
        unidad_referencia = st.selectbox(
            "Unidad de referencia", ["cm", "m", "mm"], index=0, key="unidad_referencia"
        )

    escala_m_por_px: float | None = None
    if longitud_referencia_ingresada.strip():
        try:
            longitud_referencia = float(longitud_referencia_ingresada.strip().replace(",", "."))
            factor_unidad = {"m": 1.0, "cm": 0.01, "mm": 0.001}[unidad_referencia]
            longitud_referencia_m = longitud_referencia * factor_unidad
            if not math.isfinite(longitud_referencia_m) or longitud_referencia_m <= 0:
                raise ValueError("La distancia de referencia debe ser mayor que cero.")
            if "punto_calibracion_1" in st.session_state and "punto_calibracion_2" in st.session_state:
                escala_m_por_px = calibrar_escala_m_por_pixel(
                    st.session_state.punto_calibracion_1,
                    st.session_state.punto_calibracion_2,
                    longitud_referencia_m,
                )
                st.success(f"Escala calculada: {escala_m_por_px:.6g} m/px")
            else:
                st.caption("Confirma los dos extremos para calcular la escala.")
        except ValueError as error:
            st.error(str(error))

st.markdown('<div class="section-label">02.2 · Selección</div>', unsafe_allow_html=True)
st.subheader("Selecciona la pelotilla")
st.caption(
    "Haz clic una vez sobre el centro de la pelotilla, no sobre el hilo. "
    "La cruz amarilla indica la selección actual. Si el clic no queda exacto, "
    "puedes corregir las coordenadas en el ajuste fino."
)

radio_muestra = st.slider(
    "Tamaño de la zona de color alrededor de la pelotilla (px)",
    4,
    50,
    12,
    help="Incluye el centro y una pequeña zona de la pelotilla, pero evita incluir el fondo.",
)
tolerancia_tono = st.slider(
    "Tolerancia de color",
    5,
    45,
    18,
    help="Auméntala si la pelotilla cambia de tono por iluminación; redúcela si detecta el fondo.",
)

vista_seleccion = cv2.resize(primer_frame, (ancho_vista, alto_vista), interpolation=cv2.INTER_AREA)
x_vista = int(st.session_state.lenteja_x * escala)
y_vista = int(st.session_state.lenteja_y * escala)
cv2.circle(vista_seleccion, (x_vista, y_vista), max(4, int(radio_muestra * escala)), (0, 0, 255), 2)
cv2.drawMarker(vista_seleccion, (x_vista, y_vista), (0, 255, 255), cv2.MARKER_CROSS, 20, 2)
vista_rgb = cv2.cvtColor(vista_seleccion, cv2.COLOR_BGR2RGB)

if COMPONENTE_CLIC:
    clic = streamlit_image_coordinates(
        Image.fromarray(vista_rgb),
        key=f"selector_lenteja_{identificador_video}",
    )
    if clic is not None:
        nueva_x = min(ancho - 1, max(0, round(clic["x"] / escala)))
        nueva_y = min(alto - 1, max(0, round(clic["y"] / escala)))
        st.session_state.lenteja_x = nueva_x
        st.session_state.lenteja_y = nueva_y
        st.session_state[f"ajuste_x_{identificador_video}"] = nueva_x
        st.session_state[f"ajuste_y_{identificador_video}"] = nueva_y
else:
    st.warning("Falta el componente de selección por clic. Usa temporalmente estos controles o instala las dependencias del proyecto.")
    st.image(vista_rgb, caption="Fotograma de selección", width=ancho_vista)
    st.session_state.lenteja_x = st.slider("Coordenada X", 0, max(0, ancho - 1), st.session_state.lenteja_x)
    st.session_state.lenteja_y = st.slider("Coordenada Y", 0, max(0, alto - 1), st.session_state.lenteja_y)

with st.expander("Ajuste fino de la selección (opcional)"):
    st.write("Corrige la posición si la pelotilla es pequeña o el clic quedó sobre el hilo.")
    columna_x, columna_y = st.columns(2)
    with columna_x:
        x_ajustado = st.number_input(
            "Coordenada X (px)",
            min_value=0,
            max_value=max(0, ancho - 1),
            value=int(st.session_state.lenteja_x),
            key=f"ajuste_x_{identificador_video}",
        )
    with columna_y:
        y_ajustado = st.number_input(
            "Coordenada Y (px)",
            min_value=0,
            max_value=max(0, alto - 1),
            value=int(st.session_state.lenteja_y),
            key=f"ajuste_y_{identificador_video}",
        )
    st.session_state.lenteja_x = int(x_ajustado)
    st.session_state.lenteja_y = int(y_ajustado)

x_inicial = st.session_state.lenteja_x
y_inicial = st.session_state.lenteja_y
st.info(f"Selección actual: X = {x_inicial} px, Y = {y_inicial} px")

st.subheader("Procesamiento")
if st.button("Seguir pelotilla", type="primary"):
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

    try:
        periodo_trayectoria = calcular_periodo_trayectoria(datos)
    except ValueError as error:
        periodo_trayectoria = None
        st.warning(f"No se pudo estimar el periodo automáticamente: {error}")

    metrica_1, metrica_2, metrica_3 = st.columns(3)
    metrica_1.metric("Fotogramas", f"{len(datos):,}")
    metrica_2.metric("FPS", f"{resultado.fps:.2f}")
    metrica_3.metric("Detección válida", f"{porcentaje_detectado:.1f}%")

    if periodo_trayectoria is not None:
        metricas_periodo = st.columns(3)
        metricas_periodo[0].metric(
            "Periodo automático",
            f'{periodo_trayectoria["periodo_s"]:.4f} s',
        )
        metricas_periodo[1].metric(
            "Incertidumbre estándar del periodo",
            (
                f'± {periodo_trayectoria["incertidumbre_s"]:.4f} s'
                if math.isfinite(float(periodo_trayectoria["incertidumbre_s"]))
                else "No disponible"
            ),
        )
        metricas_periodo[2].metric(
            "Oscilaciones detectadas",
            f'{periodo_trayectoria["oscilaciones"]} '
            f'({periodo_trayectoria["cruces"]} cruces)',
        )
        st.caption(
            f"Periodo estimado entre cruces ascendentes de la posición de equilibrio "
            f"en el eje {periodo_trayectoria['eje'].upper()}."
        )

    if escala_m_por_px is not None and len(datos_validos) > 0:
        for eje_posicion in ("x", "y"):
            origen = float(datos_validos[f"{eje_posicion}_px"].iloc[0])
            datos[f"{eje_posicion}_m"] = (
                datos[f"{eje_posicion}_px"] - origen
            ) * escala_m_por_px
        datos_validos = datos[datos["detectado"]].copy()

    if porcentaje_detectado < 80:
        st.warning("La detección es baja. Prueba con mejor iluminación, más contraste o ajusta las coordenadas y la tolerancia de color.")
    else:
        st.success("La pelotilla fue seguida durante la mayor parte del video.")

    st.subheader("Video con trayectoria")
    if resultado.video_anotado.suffix.lower() == ".mp4":
        columna_video, _, _ = st.columns([2, 1, 1])
        with columna_video:
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
        eje_trayectoria = (
            str(periodo_trayectoria["eje"])
            if periodo_trayectoria is not None
            else ("x" if datos_validos["x_px"].std() >= datos_validos["y_px"].std() else "y")
        )
        columna_posicion = f"{eje_trayectoria}_m" if escala_m_por_px is not None else f"{eje_trayectoria}_px"
        unidad_posicion = "m" if escala_m_por_px is not None else "px"
        st.subheader("Posición de la pelotilla frente al tiempo")
        figura, eje = plt.subplots(figsize=(10, 4))
        eje.plot(
            datos_validos["tiempo_s"],
            datos_validos[columna_posicion],
            color="#1769aa",
            linewidth=1.5,
        )
        eje.set_xlabel("Tiempo (s)")
        eje.set_ylabel(f"Posición {eje_trayectoria.upper()} ({unidad_posicion})")
        eje.grid(alpha=0.25)
        st.pyplot(figura, clear_figure=True)

        st.subheader("Datos extraídos")
        st.dataframe(datos, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar datos CSV",
            data=datos.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
            file_name="gravilab_trayectoria.csv",
            mime="text/csv; charset=utf-8",
        )
    else:
        st.error("No hubo suficientes detecciones para construir la gráfica.")

st.divider()
st.caption("GraviLab · Laboratorio Integrado · Análisis experimental del péndulo simple")
