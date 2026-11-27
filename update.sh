#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Actualizando Netlis Browser ==="

if [ -d ".git" ]; then
    echo "[*] Descargando últimos cambios desde GitHub..."
    git pull --ff-only origin main || git pull --rebase --autostash origin main
else
    echo "[!] No se detectó repositorio git en $DIR; omitiendo git pull."
fi

if [ ! -d ".venv" ]; then
    echo "[*] Creando entorno virtual .venv..."
    python3 -m venv .venv
fi

echo "[*] Actualizando dependencias Python..."
.venv/bin/pip install -q -r requirements.txt

chmod +x launch.sh install.sh install_desktop.sh update.sh doctor.sh release.py 2>/dev/null || true
./install_desktop.sh

echo ""
echo "=== ¡Netlis actualizado correctamente! ==="
if [ "${1:-}" = "--launch" ]; then
    exec ./launch.sh
else
    echo "Ábrelo desde el menú de aplicaciones o con: $DIR/launch.sh"
fi
