#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APP_DIR"

cat > "$APP_DIR/netlis.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Netlis
GenericName=Navegador Web Privado
Comment=Navegador privado ultraligero con Tor integrado, anti-rastreo y motor híbrido
Exec=$DIR/launch.sh %U
Icon=$DIR/assets/netlis_logo_transparent.png
Terminal=false
Categories=Network;WebBrowser;Security;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
StartupWMClass=browser.py
Actions=new-private-window;no-tor;

[Desktop Action new-private-window]
Name=Nueva ventana privada
Exec=$DIR/launch.sh --incognito

[Desktop Action no-tor]
Name=Abrir rápido (Sin Tor)
Exec=$DIR/launch.sh --no-tor
EOF

echo "Acceso directo instalado en $APP_DIR/netlis.desktop"
