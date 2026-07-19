# Conteo vial aéreo

Aplicación local para cargar videos aéreos, dibujar múltiples líneas de conteo y obtener entradas/salidas por trazo para autos, personas, bicicletas, trucks y buses.

## Requisitos

- macOS o Windows.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) instalado y disponible en `PATH`.
- `best.pt` en la raíz del proyecto. El modelo está incluido en este repositorio.

## Levantar y apagar en macOS

Con doble clic, abre `run_mac.command`. Desde Terminal:

```bash
./run_mac.command
```

Para levantar manualmente:

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Para apagar la aplicación, vuelve a la Terminal y presiona:

```text
Control + C
```

## Levantar y apagar en Windows

Con doble clic, abre `run_windows.bat`. Desde PowerShell o CMD:

```bat
run_windows.bat
```

Para levantar manualmente:

```bat
uv sync
uv run uvicorn app.main:app --reload
```

Para apagar la aplicación, vuelve a la consola y presiona:

```text
Ctrl + C
```

La aplicación queda disponible en <http://127.0.0.1:8000>.

## Usar otro puerto

Los lanzadores comprueban que `uv` esté instalado, ejecutan `uv sync`, abren el navegador e inician el servidor. Puedes pasar otro puerto como primer argumento:

```bash
./run_mac.command 8080
```

```bat
run_windows.bat 8080
```

Los videos originales y resultados se guardan en `data/` y están excluidos de Git. Los modelos COCO opcionales se descargan automáticamente y tampoco se versionan.

## Flujo

1. Sube un video.
2. Pausa en un cuadro donde se vean las carreteras.
3. Dibuja uno o más trazos sobre el video y asigna un nombre a cada uno.
4. Cada trazo muestra dos flechas: verde para entrada y naranja para salida. Siempre se contabilizan ambos sentidos y se pueden invertir.
5. Selecciona las clases y ejecuta el conteo.
6. Descarga el CSV o JSON de eventos. El video de seguimiento es opcional y muestra cajas, IDs persistentes y la trayectoria reciente de cada objeto.

El video de seguimiento se exporta como MP4 H.264. Sus niveles disponibles son alta (`CRF 20`), equilibrada (`CRF 26`) y liviana (`CRF 31`). El codificador FFmpeg se instala dentro del entorno mediante `uv`; no requiere una instalación separada.

Cada fila CSV representa un cruce e incluye: trazo, dirección, clase, ID del objeto, cuadro y segundo del video.

En equipos Apple Silicon la app selecciona automáticamente la GPU Metal mediante MPS. El panel de progreso muestra el dispositivo y los cuadros procesados por segundo.

## Consideraciones para vuelos aéreos

El perfil predeterminado usa `best.pt`, resolución 1280, confianza 0.10 y un ByteTrack ajustado para mantener detecciones aéreas de baja confianza. Sus clases `pedestrian`, `people`, `bicycle`, `car`, `truck` y `bus` se traducen a las categorías de la aplicación sin reutilizar los índices de COCO.
