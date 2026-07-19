#!/bin/zsh

set -e

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv no está instalado."
  echo "Instálalo desde: https://docs.astral.sh/uv/getting-started/installation/"
  echo
  read "?Presiona Enter para cerrar..."
  exit 1
fi

APP_PORT="${1:-8000}"
APP_URL="http://127.0.0.1:${APP_PORT}"

echo "Sincronizando dependencias con uv..."
uv sync

echo "Iniciando Conteo Vial en ${APP_URL}"
(sleep 2 && open "$APP_URL") &

exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT"

