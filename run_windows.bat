@echo off
setlocal

cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo ERROR: uv no esta instalado o no esta disponible en PATH.
    echo Instalalo desde: https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

set "APP_PORT=%~1"
if not defined APP_PORT set "APP_PORT=8000"
set "APP_URL=http://127.0.0.1:%APP_PORT%"

echo Sincronizando dependencias con uv...
uv sync
if errorlevel 1 (
    echo.
    echo No fue posible instalar las dependencias.
    pause
    exit /b 1
)

echo Iniciando Conteo Vial en %APP_URL%
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%APP_URL%'"

uv run uvicorn app.main:app --host 127.0.0.1 --port %APP_PORT%

if errorlevel 1 (
    echo.
    echo La aplicacion se detuvo con un error.
    pause
    exit /b 1
)

endlocal
