"""Cálculos físicos de las mediciones de un péndulo simple."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

GRAVEDAD_REFERENCIA_M_S2 = 9.78


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
    gravedad_referencia_m_s2: float = GRAVEDAD_REFERENCIA_M_S2,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Calcula estadísticas del periodo y el ajuste lineal de T² frente a L."""

    if not math.isfinite(gravedad_referencia_m_s2) or gravedad_referencia_m_s2 <= 0:
        raise ValueError("La gravedad de referencia debe ser un número mayor que cero.")

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
        parametros["gravedad_referencia"] = gravedad_referencia_m_s2
        parametros["error_porcentual"] = (
            abs(gravedad - gravedad_referencia_m_s2) / gravedad_referencia_m_s2 * 100
        )

    return resumen, parametros


def detectar_datos_atipicos(
    mediciones: list[dict[str, float | int]],
) -> pd.DataFrame:
    """Marca periodos atípicos dentro de cada grupo de longitud usando el IQR.

    Se trabaja con el periodo de cada repetición, no con los tiempos brutos de
    diez oscilaciones. Para grupos pequeños con IQR cero se usa MAD; si todas
    las mediciones coinciden, solo se tolera una diferencia numérica mínima.
    """

    columnas = [
        "longitud_m",
        "repeticion",
        "periodo_s",
        "limite_inferior_s",
        "limite_superior_s",
        "atipico",
    ]
    datos = pd.DataFrame(mediciones).copy()
    if datos.empty:
        return pd.DataFrame(columns=columnas)

    datos["periodo_s"] = datos["tiempo_10_oscilaciones_s"] / 10
    filas: list[dict[str, float | int | bool]] = []

    for longitud, grupo in datos.groupby("longitud_m", sort=True):
        valores = grupo["periodo_s"].to_numpy(dtype=float)
        q1, q3 = np.percentile(valores, [25, 75])
        iqr = q3 - q1

        if iqr > 0:
            limite_inferior = q1 - 1.5 * iqr
            limite_superior = q3 + 1.5 * iqr
        else:
            mediana = float(np.median(valores))
            mad = float(np.median(np.abs(valores - mediana)))
            dispersion = 1.4826 * mad
            if dispersion > 0:
                limite_inferior = mediana - 3 * dispersion
                limite_superior = mediana + 3 * dispersion
            else:
                tolerancia = max(abs(mediana) * 1e-9, 1e-9)
                limite_inferior = mediana - tolerancia
                limite_superior = mediana + tolerancia

        for indice, fila in grupo.iterrows():
            periodo = float(fila["periodo_s"])
            filas.append(
                {
                    "longitud_m": float(longitud),
                    "repeticion": int(fila["repeticion"]),
                    "periodo_s": periodo,
                    "limite_inferior_s": float(limite_inferior),
                    "limite_superior_s": float(limite_superior),
                    "atipico": bool(
                        periodo < limite_inferior or periodo > limite_superior
                    ),
                }
            )

    return pd.DataFrame(filas, columns=columnas).sort_values(
        ["longitud_m", "repeticion"]
    )


def generar_conclusiones(
    resumen: pd.DataFrame,
    parametros: dict[str, float],
    datos_atipicos: pd.DataFrame | None = None,
) -> list[str]:
    """Genera conclusiones breves a partir del ajuste y la dispersión observada."""

    if resumen.empty:
        return ["No hay suficientes datos para generar conclusiones."]

    conclusiones: list[str] = []
    r_cuadrado = parametros.get("r_cuadrado", float("nan"))
    if math.isfinite(r_cuadrado):
        if r_cuadrado >= 0.95:
            conclusiones.append(
                f"La relación lineal entre T² y L es fuerte (R² = {r_cuadrado:.4f})."
            )
        elif r_cuadrado >= 0.80:
            conclusiones.append(
                f"La relación entre T² y L es moderada (R² = {r_cuadrado:.4f}); conviene revisar la dispersión."
            )
        else:
            conclusiones.append(
                f"La relación lineal entre T² y L es débil (R² = {r_cuadrado:.4f}); deben revisarse las mediciones."
            )

    gravedad = parametros.get("gravedad", float("nan"))
    error_porcentual = parametros.get("error_porcentual", float("nan"))
    referencia = parametros.get("gravedad_referencia", GRAVEDAD_REFERENCIA_M_S2)
    if math.isfinite(gravedad) and math.isfinite(error_porcentual):
        if error_porcentual <= 5:
            conclusiones.append(
                f"La gravedad experimental es {gravedad:.3f} m/s² y presenta un error de {error_porcentual:.2f}% frente a la referencia de {referencia:.2f} m/s²."
            )
        else:
            conclusiones.append(
                f"La gravedad experimental es {gravedad:.3f} m/s², con un error de {error_porcentual:.2f}%; conviene revisar el cronometraje, la longitud y el ángulo inicial."
            )

    intercepto = parametros.get("intercepto", float("nan"))
    escala_t2 = float(resumen["periodo_cuadrado_s2"].mean())
    if math.isfinite(intercepto) and escala_t2 > 0:
        if abs(intercepto) <= 0.1 * escala_t2:
            conclusiones.append("El intercepto es pequeño frente a T² promedio, consistente con el modelo ideal.")
        else:
            conclusiones.append("El intercepto no es despreciable; puede indicar errores sistemáticos o una longitud efectiva mal medida.")

    if datos_atipicos is not None and not datos_atipicos.empty:
        cantidad_atipicos = int(datos_atipicos["atipico"].sum())
        if cantidad_atipicos:
            conclusiones.append(
                f"Se detectaron {cantidad_atipicos} medición(es) atípica(s); deben revisarse antes de sacar la conclusión final."
            )
        else:
            conclusiones.append("No se detectaron mediciones atípicas mediante el criterio IQR por longitud.")

    return conclusiones
