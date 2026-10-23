"""Seguimiento sencillo de una lenteja de péndulo por color y proximidad.

Esta primera versión está pensada para videos con cámara fija y una lenteja
que contraste claramente con el fondo. No intenta detectar todavía la
longitud ni calcular la gravedad.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd


@dataclass
class ResultadoSeguimiento:
    """Resultados del procesamiento de un video."""

    datos: pd.DataFrame
    video_anotado: Path
    fps: float
    ancho: int
    alto: int
    fotogramas_totales: int


def _distancia_tono(hsv: np.ndarray, tono: int) -> np.ndarray:
    """Devuelve la distancia circular del tono HSV respecto a ``tono``."""

    return np.minimum(np.abs(hsv.astype(np.int16) - tono), 180 - np.abs(hsv.astype(np.int16) - tono))


def _perfil_color(frame_bgr: np.ndarray, x: int, y: int, radio: int) -> tuple[int, int, int]:
    """Obtiene el color HSV mediano de una pequeña región seleccionada."""

    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    alto, ancho = hsv.shape[:2]
    x1, x2 = max(0, x - radio), min(ancho, x + radio + 1)
    y1, y2 = max(0, y - radio), min(alto, y + radio + 1)
    muestra = hsv[y1:y2, x1:x2].reshape(-1, 3)
    mediana = np.median(muestra, axis=0).astype(int)
    return int(mediana[0]), int(mediana[1]), int(mediana[2])


def _centroide_mascara(
    mask: np.ndarray,
    posicion_anterior: tuple[float, float] | None,
    area_minima: int,
) -> tuple[float, float] | None:
    """Selecciona el contorno más plausible y devuelve su centroide."""

    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidatos = []

    for contorno in contornos:
        area = cv2.contourArea(contorno)
        if area < area_minima:
            continue

        momentos = cv2.moments(contorno)
        if momentos["m00"] == 0:
            continue

        cx = momentos["m10"] / momentos["m00"]
        cy = momentos["m01"] / momentos["m00"]
        candidatos.append((cx, cy, area))

    if not candidatos:
        return None

    if posicion_anterior is None:
        candidato = max(candidatos, key=lambda item: item[2])
    else:
        candidato = min(
            candidatos,
            key=lambda item: (item[0] - posicion_anterior[0]) ** 2
            + (item[1] - posicion_anterior[1]) ** 2,
        )

    return float(candidato[0]), float(candidato[1])


def _crear_escritor(
    ruta_preferida: str | Path,
    fps: float,
    ancho: int,
    alto: int,
) -> tuple[cv2.VideoWriter, Path]:
    """Intenta varios códecs porque su disponibilidad depende del sistema."""

    ruta_preferida = Path(ruta_preferida)
    candidatos = [
        (ruta_preferida.with_suffix(".mp4"), "mp4v"),
        (ruta_preferida.with_suffix(".mp4"), "avc1"),
        (ruta_preferida.with_suffix(".avi"), "MJPG"),
    ]
    rutas_probadas: set[Path] = set()

    for ruta, codec in candidatos:
        if ruta in rutas_probadas:
            continue
        rutas_probadas.add(ruta)
        ruta.unlink(missing_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*codec)
        escritor = cv2.VideoWriter(str(ruta), fourcc, fps, (ancho, alto))
        if escritor.isOpened():
            return escritor, ruta
        escritor.release()

    raise ValueError(
        "OpenCV no pudo crear un archivo de video con los códecs disponibles. "
        "Prueba instalar ffmpeg o usar un entorno con soporte para mp4v."
    )


def procesar_video(
    video_entrada: str | Path,
    video_salida: str | Path,
    x_inicial: int,
    y_inicial: int,
    radio_muestra: int = 12,
    tolerancia_tono: int = 18,
    saturacion_minima: int = 60,
    valor_minimo: int = 40,
    area_minima: int = 20,
) -> ResultadoSeguimiento:
    """Rastrea la lenteja y genera un video con la trayectoria dibujada."""

    captura = cv2.VideoCapture(str(video_entrada))
    if not captura.isOpened():
        raise ValueError("No se pudo abrir el video de entrada.")

    fps = float(captura.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        fps = 30.0

    ancho = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fotogramas_totales = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))

    ok, primer_frame = captura.read()
    if not ok:
        captura.release()
        raise ValueError("No se pudo leer el primer fotograma del video.")

    tono, saturacion, valor = _perfil_color(primer_frame, x_inicial, y_inicial, radio_muestra)
    # La detección usa el tono seleccionado y exige una saturación/iluminación
    # mínima para evitar que el fondo gris se convierta en candidato.
    saturacion_minima = max(saturacion_minima, int(saturacion * 0.45))
    valor_minimo = max(valor_minimo, int(valor * 0.35))

    try:
        escritor, ruta_video_final = _crear_escritor(video_salida, fps, ancho, alto)
    except ValueError:
        captura.release()
        raise

    filas: list[dict[str, float | int | bool]] = []
    posicion_anterior: tuple[float, float] | None = None
    trayectoria: list[tuple[int, int]] = []
    numero_fotograma = 0

    # Procesamos de nuevo desde el primer fotograma.
    captura.set(cv2.CAP_PROP_POS_FRAMES, 0)

    while True:
        ok, frame = captura.read()
        if not ok:
            break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        distancia = _distancia_tono(hsv[:, :, 0], tono)
        mascara = (
            (distancia <= tolerancia_tono)
            & (hsv[:, :, 1] >= saturacion_minima)
            & (hsv[:, :, 2] >= valor_minimo)
        ).astype(np.uint8) * 255

        kernel = np.ones((5, 5), np.uint8)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, kernel)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, kernel)

        posicion = _centroide_mascara(mascara, posicion_anterior, area_minima)
        tiempo = numero_fotograma / fps

        if posicion is None:
            filas.append({"fotograma": numero_fotograma, "tiempo_s": tiempo, "x_px": np.nan, "y_px": np.nan, "detectado": False})
        else:
            x, y = posicion
            posicion_anterior = posicion
            trayectoria.append((int(round(x)), int(round(y))))
            filas.append({"fotograma": numero_fotograma, "tiempo_s": tiempo, "x_px": x, "y_px": y, "detectado": True})

        for punto_a, punto_b in zip(trayectoria[:-1], trayectoria[1:]):
            cv2.line(frame, punto_a, punto_b, (255, 120, 0), 2)

        if posicion is not None:
            cv2.circle(frame, (int(posicion[0]), int(posicion[1])), 10, (0, 255, 0), 2)

        cv2.circle(frame, (x_inicial, y_inicial), radio_muestra, (0, 0, 255), 2)
        cv2.putText(
            frame,
            f"t = {tiempo:.2f} s",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        escritor.write(frame)
        numero_fotograma += 1

    captura.release()
    escritor.release()

    return ResultadoSeguimiento(
        datos=pd.DataFrame(filas),
        video_anotado=ruta_video_final,
        fps=fps,
        ancho=ancho,
        alto=alto,
        fotogramas_totales=numero_fotograma or fotogramas_totales,
    )
