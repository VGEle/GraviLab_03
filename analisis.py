"""Cálculos físicos de las mediciones de un péndulo simple."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def calibrar_escala_m_por_pixel(
    punto_1: tuple[float, float],
    punto_2: tuple[float, float],
    longitud_m: float,
) -> float:
    """Calcula la escala espacial a partir de dos puntos y una distancia real."""

    distancia_px = math.hypot(punto_2[0] - punto_1[0], punto_2[1] - punto_1[1])
    if not math.isfinite(distancia_px) or distancia_px <= 0:
        raise ValueError("Los extremos de calibración deben ser puntos distintos.")
    if not math.isfinite(longitud_m) or longitud_m <= 0:
        raise ValueError("La longitud de referencia debe ser mayor que cero.")
    return longitud_m / distancia_px


def calcular_periodo_trayectoria(datos: pd.DataFrame) -> dict[str, float | int | str]:
    """Estima el periodo con cruces ascendentes interpolados por la posición central."""

    trayectoria = datos.loc[datos["detectado"], ["tiempo_s", "x_px", "y_px"]].copy()
    trayectoria = trayectoria.replace([np.inf, -np.inf], np.nan).dropna()
    if len(trayectoria) < 5:
        raise ValueError("Se necesitan al menos 5 posiciones detectadas para estimar el periodo.")

    tiempos = trayectoria["tiempo_s"].to_numpy(dtype=float)
    if np.any(np.diff(tiempos) <= 0):
        raise ValueError("Los tiempos de la trayectoria deben ser estrictamente crecientes.")

    x = trayectoria["x_px"].to_numpy(dtype=float)
    y = trayectoria["y_px"].to_numpy(dtype=float)
    eje = "x" if np.std(x) >= np.std(y) else "y"
    posicion = x if eje == "x" else y
    amplitud = float(np.percentile(posicion, 95) - np.percentile(posicion, 5))
    if amplitud < 4:
        raise ValueError(
            "El movimiento detectado es demasiado pequeño para estimar el periodo. "
            "Revisa la selección de la pelotilla y el encuadre."
        )
    equilibrio = float(np.median(posicion))

    paso_medio = float(np.median(np.diff(tiempos)))
    if paso_medio <= 0:
        raise ValueError("No se pudo determinar el intervalo temporal de la trayectoria.")

    # No conectamos cruces a través de tramos donde la pelotilla dejó de detectarse.
    limites_segmento = np.flatnonzero(np.diff(tiempos) > 2.5 * paso_medio) + 1
    segmentos = np.split(np.arange(len(tiempos)), limites_segmento)
    cruces: list[float] = []
    ventana = min(11, max(3, int(round(0.08 / paso_medio))))
    if ventana % 2 == 0:
        ventana += 1
    mitad_ventana = ventana // 2

    for indices in segmentos:
        if len(indices) < 5:
            continue
        valores = posicion[indices] - equilibrio
        valores_suavizados = np.convolve(
            np.pad(valores, (mitad_ventana, mitad_ventana), mode="edge"),
            np.ones(ventana) / ventana,
            mode="valid",
        )
        tiempo_segmento = tiempos[indices]
        for indice in np.flatnonzero(
            (valores_suavizados[:-1] <= 0) & (valores_suavizados[1:] > 0)
        ):
            fraccion = -valores_suavizados[indice] / (
                valores_suavizados[indice + 1] - valores_suavizados[indice]
            )
            cruces.append(
                float(
                    tiempo_segmento[indice]
                    + fraccion * (tiempo_segmento[indice + 1] - tiempo_segmento[indice])
                )
            )

    if len(cruces) < 2:
        raise ValueError(
            "No se detectaron suficientes cruces ascendentes. Revisa el seguimiento "
            "y asegúrate de incluir al menos una oscilación completa."
        )

    intervalos = np.diff(cruces)
    referencia_intervalo = float(np.percentile(intervalos, 25))
    intervalos_validos = intervalos[
        (intervalos >= 0.7 * referencia_intervalo)
        & (intervalos <= 1.3 * referencia_intervalo)
    ]
    if len(intervalos_validos) == 0:
        raise ValueError("No se pudieron identificar intervalos de oscilación consistentes.")

    periodo = float(np.median(intervalos_validos))
    incertidumbre = (
        float(np.std(intervalos_validos, ddof=1) / math.sqrt(len(intervalos_validos)))
        if len(intervalos_validos) > 1
        else float("nan")
    )
    return {
        "periodo_s": periodo,
        "incertidumbre_s": incertidumbre,
        "eje": eje,
        "cruces": len(cruces),
        "oscilaciones": len(intervalos_validos),
    }


def calcular_analisis(
    mediciones: list[dict[str, float | int]],
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Calcula estadísticas del periodo y el ajuste lineal de T² frente a L."""

    datos = pd.DataFrame(mediciones)
    datos["periodo_s"] = datos["tiempo_10_oscilaciones_s"] / 10
    resumen = (
        datos.groupby("longitud_m", as_index=False)
        .agg(
            repeticiones=("periodo_s", "count"),
            periodo_promedio_s=("periodo_s", "mean"),
            desviacion_estandar_s=("periodo_s", "std"),
        )
        .sort_values("longitud_m")
    )
    resumen["periodo_cuadrado_s2"] = resumen["periodo_promedio_s"] ** 2

    longitudes = resumen["longitud_m"].to_numpy(dtype=float)
    periodos_cuadrados = resumen["periodo_cuadrado_s2"].to_numpy(dtype=float)
    pendiente, intercepto = np.polyfit(longitudes, periodos_cuadrados, 1)
    predicciones = pendiente * longitudes + intercepto
    residuos = periodos_cuadrados - predicciones
    suma_residuos = float(np.sum(residuos**2))
    suma_total = float(np.sum((periodos_cuadrados - np.mean(periodos_cuadrados)) ** 2))
    r_cuadrado = 1 - suma_residuos / suma_total if suma_total > 0 else float("nan")

    suma_x = float(np.sum((longitudes - np.mean(longitudes)) ** 2))
    error_estandar_pendiente = (
        math.sqrt(suma_residuos / (len(longitudes) - 2) / suma_x)
        if len(longitudes) > 2 and suma_x > 0
        else float("nan")
    )
    parametros = {
        "pendiente": float(pendiente),
        "intercepto": float(intercepto),
        "r_cuadrado": float(r_cuadrado),
        "error_estandar_pendiente": float(error_estandar_pendiente),
    }

    if pendiente > 0 and math.isfinite(pendiente):
        gravedad = 4 * math.pi**2 / pendiente
        incertidumbre_gravedad = gravedad * error_estandar_pendiente / abs(pendiente)
        parametros["gravedad"] = gravedad
        parametros["incertidumbre_gravedad"] = incertidumbre_gravedad
        parametros["error_porcentual"] = abs(gravedad - 9.81) / 9.81 * 100

    return resumen, parametros
