#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
ulimit -c 0 2>/dev/null || true

# Si el Escudo Anti-Espionaje Total está activo (por defecto sí), forzar UTC y aislar fuentes C++ (Fontconfig)
if [ ! -f "data/plugins.json" ] || ! grep -q '"anti-espionaje-total":.*"enabled": false' "data/plugins.json"; then
    export TZ=UTC
    for _fdir in \
        /usr/share/fonts/liberation /usr/share/fonts/noto \
        /usr/share/fonts/truetype/liberation /usr/share/fonts/truetype/liberation2 \
        /usr/share/fonts/truetype/noto /usr/share/fonts/truetype/dejavu \
        /usr/share/fonts/liberation-sans /usr/share/fonts/google-noto; do
        if [ -d "$_fdir" ]; then
            export FONTCONFIG_FILE="$PWD/assets/fonts_isolated.conf"
            break
        fi
    done
fi

# Mantener activo el sandbox de Chromium también con restricciones AppArmor.

# Las banderas unificadas (--site-per-process, StrictOriginIsolation, ThirdPartyStoragePartitioning, --jitless)
# se construyen e inyectan dinámicamente en browser.py mediante privacy.build_chromium_flags()
exec .venv/bin/python3 browser.py "$@"
