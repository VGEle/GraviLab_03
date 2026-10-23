# GraviLab

GraviLab es una aplicación web para analizar videos de un péndulo simple. Esta primera versión valida el seguimiento automático de la lenteja antes de incorporar el cálculo del periodo y de la aceleración de la gravedad.

Actualmente la aplicación:

- Carga videos del experimento.
- Muestra el primer fotograma en tamaño reducido.
- Permite seleccionar la lenteja haciendo clic sobre ella.
- Sigue la lenteja usando su color y su posición anterior.
- Dibuja la trayectoria sobre el video.
- Genera una gráfica de posición horizontal contra tiempo.
- Permite descargar el video anotado y los datos en formato CSV.

## Requisitos

- Python 3.10 o superior.
- Un video del péndulo en formato `.mp4`, `.mov`, `.avi` o `.m4v`.
- Cámara fija, buena iluminación y una lenteja que contraste con el fondo.

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

1. Carga el video en el botón **Carga un video del péndulo**.
2. Haz clic sobre el centro de la lenteja en la imagen reducida.
3. Ajusta el radio de muestra y la tolerancia de color si es necesario.
4. Pulsa **Seguir lenteja**.
5. Revisa el porcentaje de fotogramas detectados.
6. Descarga el video anotado o el archivo CSV.

## Recomendaciones para grabar el video

- Usa una cámara fija y perpendicular al plano de oscilación.
- Mantén la lenteja visible durante todo el video.
- Utiliza un fondo uniforme y una lenteja de color contrastante.
- Evita sombras, reflejos y objetos con colores similares.
- Graba al menos 10 oscilaciones, preferiblemente a 30 FPS o más.
- Incluye una regla o marcador de escala para una futura calibración de píxeles a metros.

## Archivos principales

```text
app.py             Interfaz web de Streamlit.
seguimiento.py     Detección de color y seguimiento de la lenteja.
requirements.txt   Dependencias del proyecto.
```

## Limitaciones actuales

- La lenteja debe tener suficiente contraste con el fondo.
- La selección inicial se realiza manualmente.
- La posición se expresa en píxeles, no en metros.
- Todavía no se detectan automáticamente los máximos de oscilación.
- Todavía no se calcula el periodo, la incertidumbre ni la gravedad.
- Si el sistema no dispone de un códec MP4 compatible, el resultado puede generarse en formato AVI.

