# GraviLab

GraviLab es una aplicación web para registrar mediciones y analizar videos de un péndulo simple.

Actualmente la aplicación:

- Registra longitudes y tiempos de 10 oscilaciones con sus repeticiones, valida las entradas y exporta las mediciones a CSV.
- Calcula el periodo por repetición, su promedio y desviación estándar por longitud, y ajusta una regresión lineal de T² frente a L.
- Calcula la gravedad, su incertidumbre propagada desde el error estándar de la pendiente y el error porcentual respecto a una gravedad de referencia configurable.
- Genera las gráficas T² frente a L y T frente a L, incluyendo la recta de ajuste, el modelo teórico y barras de error.
- Detecta mediciones atípicas por longitud mediante el criterio del rango intercuartílico (IQR).
- Redacta conclusiones automáticas sobre R², la gravedad experimental, el error porcentual, el intercepto y los datos atípicos.
- Carga videos del experimento.
- Muestra el primer fotograma en tamaño reducido.
- Permite seleccionar la pelotilla haciendo clic sobre ella y corregir la coordenada con un ajuste fino opcional.
- Sigue la pelotilla usando su color y una predicción de posición entre fotogramas, rechazando saltos improbables.
- Dibuja la trayectoria sobre el video.
- Estima automáticamente el periodo mediante cruces ascendentes de la posición de equilibrio.
- Calibra píxeles a metros con dos puntos de una regla o una longitud conocida.
- Genera una gráfica de posición contra tiempo en píxeles o metros calibrados.
- Permite descargar el video anotado y los datos en formato CSV.

## Requisitos

- Python 3.10 o superior.
- Un video del péndulo en formato `.mp4`, `.mov`, `.avi` o `.m4v`.
- Cámara fija, buena iluminación y una pelotilla que contraste con el fondo.

## Ejecución local

```bash
cd GraviLab_03
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Después, abre `http://localhost:8501` en el navegador.

En Windows, la activación del entorno virtual se realiza con:

```powershell
.venv\Scripts\activate
```

## Uso

### Registro de mediciones

1. En **Registro de mediciones**, ingresa la longitud y selecciona su unidad: metros (`m`), centímetros (`cm`) o milímetros (`mm`).
2. Ingresa el tiempo que tardan 10 oscilaciones, en segundos (`s`), y un número de repetición entero entre 1 y 5.
3. Pulsa **Agregar medición**. Se aceptan comas o puntos como separador decimal. La longitud y el tiempo deben ser valores finitos mayores que cero; los campos y las unidades son obligatorios.
4. Para una misma longitud no se puede repetir el mismo número de repetición y se permiten como máximo 5 mediciones.
5. Completa al menos 6 longitudes distintas con un mínimo de 3 y un máximo de 5 repeticiones por longitud. La aplicación muestra el progreso e indica cuándo la serie cumple el mínimo.
6. Consulta las mediciones registradas en la tabla o pulsa **Borrar todas las mediciones** para empezar de nuevo. Los datos se mantienen durante la sesión actual de la aplicación.
7. Pulsa **Descargar mediciones CSV** para exportar las columnas `longitud_m`, `tiempo_10_oscilaciones_s` y `repeticion`. Longitudes y tiempos se normalizan a metros y segundos.
8. Cuando haya al menos 6 longitudes distintas y 3 repeticiones por longitud, consulta **Análisis físico** para ver el periodo promedio, la desviación estándar, T², la regresión, g y el error porcentual. El ajuste usa el periodo promedio de cada longitud y reporta la incertidumbre estándar de g propagada desde la incertidumbre estándar de la pendiente.
9. Revisa las gráficas T² frente a L y T frente a L, las alertas de mediciones atípicas y las conclusiones automáticas. La gravedad de referencia inicia en 9,78 m/s², pero puede cambiarse desde la interfaz si el laboratorio define otro valor.

### Análisis de video

1. Carga el video en **Carga un video del péndulo**.
2. Opcionalmente, abre **Calibración espacial**. Haz clic en cada extremo de una regla o referencia visible, confirma cada punto e ingresa la distancia real. Esto convierte píxeles a metros; no es necesario para seguir la pelotilla ni para calcular el periodo.
3. Haz clic sobre el centro de la pelotilla en la imagen reducida. Si hace falta, usa **Ajuste fino de la selección** para corregir X e Y.
4. Ajusta el tamaño de la zona de color y la tolerancia si es necesario.
5. Pulsa **Seguir pelotilla**.
6. Revisa el porcentaje de fotogramas detectados y el periodo estimado automáticamente a partir de cruces ascendentes. Se muestra también la dispersión del periodo cuando hay suficientes ciclos.
7. Descarga el video anotado o los datos de trayectoria. Si calibraste, el CSV incluye las posiciones relativas `x_m` y `y_m`.

## Recomendaciones para grabar el video

- Usa una cámara fija y perpendicular al plano de oscilación.
- Mantén la pelotilla visible durante todo el video.
- Utiliza un fondo uniforme y una pelotilla de color contrastante.
- Evita sombras, reflejos y objetos con colores similares.
- Graba al menos 10 oscilaciones, preferiblemente a 30 FPS o más.
- Incluye una regla o marcador de longitud conocida en el mismo plano de movimiento para calibrar píxeles a metros.
- Asegúrate de que la cámara esté perpendicular al plano de movimiento; la calibración es una escala 2D simple y no corrige perspectiva.

## Archivos principales

```text
app.py             Interfaz web de Streamlit.
    analisis.py        Estadística de periodos, regresión lineal, cálculo de g y conclusiones.
seguimiento.py     Detección de color y seguimiento de la lenteja.
    test_analisis.py   Pruebas de análisis físico, datos atípicos, calibración y periodo automático.
requirements.txt   Dependencias del proyecto.
```

## Limitaciones actuales

- La pelotilla debe tener suficiente contraste con el fondo.
- La selección inicial se realiza manualmente.
- La calibración espacial es opcional, requiere dos puntos visibles de una distancia conocida y no corrige distorsión ni perspectiva.
- El criterio IQR marca valores para revisión, pero no los elimina automáticamente del análisis.
- La detección automática del periodo usa cruces ascendentes del eje de mayor movimiento; requiere que el video incluya al menos una oscilación completa y que la pelotilla se detecte con continuidad.
- El cálculo de g se basa en los tiempos registrados manualmente; no se extrae el periodo del video.
- Si el sistema no dispone de un códec MP4 compatible, el resultado puede generarse en formato AVI.
