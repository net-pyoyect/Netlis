#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/256x256/apps"
mkdir -p "$APP_DIR" "$ICON_DIR"
cp -f "$DIR/assets/netlis_logo_transparent.png" "$ICON_DIR/netlis.png" 2>/dev/null || true

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
StartupWMClass=netlis
Actions=new-private-window;no-tor;

[Desktop Action new-private-window]
Name=Nueva ventana privada
Exec=$DIR/launch.sh --incognito

[Desktop Action no-tor]
Name=Modo Día a día (Rápido, sin Tor)
Exec=$DIR/launch.sh --no-tor
EOF

update-desktop-database "$APP_DIR" 2>/dev/null || true
echo "Acceso directo instalado en $APP_DIR/netlis.desktop"
