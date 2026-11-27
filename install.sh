#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Instalador Universal de Netlis Browser para Linux ==="

install_sys_deps() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "[*] Detectado sistema basado en Debian/Ubuntu (Debian, Ubuntu, Kali, Linux Mint, Pop!_OS)..."
        sudo apt-get update || true
        sudo apt-get install -y python3 python3-venv python3-pip git tor obfs4proxy libxcb-cursor0 libnss3 libegl1 libxkbcommon0 fonts-liberation fonts-dejavu-core || \
        sudo apt-get install -y python3 python3-venv python3-pip git tor libxcb-cursor0 libnss3 libegl1 libxkbcommon0 fonts-liberation fonts-dejavu-core
    elif command -v pacman >/dev/null 2>&1; then
        echo "[*] Detectado sistema basado en Arch Linux (Arch, Manjaro, EndeavourOS, Quantum)..."
        sudo pacman -Sy --needed --noconfirm python git tor nss libxcb xcb-util-cursor libxkbcommon
        sudo pacman -S --needed --noconfirm obfs4proxy 2>/dev/null || true
    elif command -v dnf >/dev/null 2>&1; then
        echo "[*] Detectado sistema basado en Fedora/RHEL (Fedora, Nobara, Alma, Rocky)..."
        sudo dnf install -y python3 python3-pip git tor nss xcb-util-cursor libxkbcommon
        sudo dnf install -y obfs4proxy 2>/dev/null || true
    elif command -v zypper >/dev/null 2>&1; then
        echo "[*] Detectado openSUSE..."
        sudo zypper install -y python3 python3-pip git tor mozilla-nss libxcb-cursor0
    elif command -v xbps-install >/dev/null 2>&1; then
        echo "[*] Detectado Void Linux..."
        sudo xbps-install -Sy python3 git tor nss xcb-util-cursor
    elif command -v apk >/dev/null 2>&1; then
        echo "[*] Detectado Alpine Linux..."
        sudo apk add --no-cache python3 py3-pip git tor nss libxkbcommon
    else
        echo "[!] Gestor de paquetes no reconocido; asegúrate de tener Python 3.10+, pip, venv y Tor instalados."
    fi
}

if [ "${1:-}" != "--no-sys" ]; then
    install_sys_deps
fi

if [ ! -d ".venv" ]; then
    echo "[*] Creando entorno virtual .venv..."
    python3 -m venv .venv
fi

echo "[*] Instalando PyQt6 y PyQt6-WebEngine..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

chmod +x launch.sh install_desktop.sh release.py
./install_desktop.sh

echo ""
echo "=== ¡Netlis instalado correctamente! ==="
echo "Ejecútalo desde tu menú de aplicaciones o con: $DIR/launch.sh"
