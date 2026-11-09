import unittest

import cv2
import numpy as np
import pandas as pd

from analisis import (
    calcular_analisis,
    calcular_periodo_trayectoria,
    calibrar_escala_m_por_pixel,
    detectar_datos_atipicos,
    generar_conclusiones,
)
from seguimiento import _perfil_color


class AnalisisTrayectoriaTests(unittest.TestCase):
    def test_periodo_se_estima_con_ruido_y_perdida_de_fotogramas(self):
        frecuencia = 60
        periodo_real = 1.6
        tiempos = np.arange(0, 7, 1 / frecuencia)
        generador = np.random.default_rng(42)
        datos = pd.DataFrame(
            {
                "tiempo_s": tiempos,
                "x_px": 180
                + 75 * np.sin(2 * np.pi * tiempos / periodo_real)
                + generador.normal(0, 0.6, len(tiempos)),
                "y_px": 250 + generador.normal(0, 0.2, len(tiempos)),
                "detectado": True,
            }
        )
        datos.loc[120:126, "detectado"] = False

        resultado = calcular_periodo_trayectoria(datos)

        self.assertAlmostEqual(resultado["periodo_s"], periodo_real, delta=0.04)
        self.assertEqual(resultado["eje"], "x")
        self.assertGreaterEqual(resultado["oscilaciones"], 3)

    def test_movimiento_insuficiente_no_produce_un_periodo_falso(self):
        datos = pd.DataFrame(
            {
                "tiempo_s": np.arange(10) / 30,
                "x_px": np.full(10, 100.0),
                "y_px": np.full(10, 100.0),
                "detectado": True,
            }
        )

        with self.assertRaisesRegex(ValueError, "demasiado pequeño"):
            calcular_periodo_trayectoria(datos)

    def test_calibracion_convierte_distancia_conocida_a_escala(self):
        escala = calibrar_escala_m_por_pixel((10, 10), (110, 10), 0.5)

        self.assertAlmostEqual(escala, 0.005)

    def test_calibracion_rechaza_puntos_iguales(self):
        with self.assertRaisesRegex(ValueError, "puntos distintos"):
            calibrar_escala_m_por_pixel((10, 10), (10, 10), 0.5)


class SeguimientoColorTests(unittest.TestCase):
    def test_perfil_de_color_no_se_deja_dominar_por_el_fondo(self):
        frame = np.zeros((80, 80, 3), dtype=np.uint8)
        cv2.circle(frame, (40, 40), 8, (0, 0, 255), -1)

        tono, saturacion, valor = _perfil_color(frame, 40, 40, 12)

        self.assertLess(min(tono, 180 - tono), 5)
        self.assertGreaterEqual(saturacion, 240)
        self.assertGreaterEqual(valor, 240)


class AnalisisFisicoTests(unittest.TestCase):
    def _mediciones(self):
        return [
            {"longitud_m": longitud, "tiempo_10_oscilaciones_s": tiempo, "repeticion": repeticion}
            for longitud, tiempos in {
                0.20: [8.98, 9.02, 9.00],
                0.30: [11.00, 11.04, 11.02],
                0.40: [12.70, 12.74, 12.72],
                0.50: [14.20, 14.24, 14.22],
                0.60: [15.55, 15.59, 15.57],
                0.80: [17.95, 17.99, 17.97],
            }.items()
            for repeticion, tiempo in enumerate(tiempos, start=1)
        ]

    def test_detecta_un_periodo_atipico_por_longitud(self):
        mediciones = self._mediciones()
        mediciones.extend(
            [
                {"longitud_m": 0.20, "tiempo_10_oscilaciones_s": 15.0, "repeticion": 4},
            ]
        )

        atipicos = detectar_datos_atipicos(mediciones)

        fila = atipicos[
            (atipicos["longitud_m"] == 0.20) & (atipicos["repeticion"] == 4)
        ].iloc[0]
        self.assertTrue(fila["atipico"])

    def test_genera_conclusiones_con_resultados_del_ajuste(self):
        resumen, parametros = calcular_analisis(self._mediciones())

        conclusiones = generar_conclusiones(resumen, parametros)

        self.assertGreaterEqual(len(conclusiones), 3)
        self.assertTrue(any("R²" in conclusion for conclusion in conclusiones))
        self.assertTrue(any("gravedad experimental" in conclusion for conclusion in conclusiones))


if __name__ == "__main__":
    unittest.main()
