#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
ulimit -c 0 2>/dev/null || true

# Si el Escudo Anti-Espionaje Total está activo (por defecto sí), forzar UTC y aislar fuentes C++ (Fontconfig)
if [ ! -f "data/plugins.json" ] || ! grep -q '"anti-espionaje-total":.*"enabled": false' "data/plugins.json"; then
    export TZ=UTC
    export FONTCONFIG_FILE="$PWD/assets/fonts_isolated.conf"
fi

# Las banderas unificadas (--site-per-process, StrictOriginIsolation, ThirdPartyStoragePartitioning, --jitless)
# se construyen e inyectan dinámicamente en browser.py mediante privacy.build_chromium_flags()
exec .venv/bin/python3 browser.py "$@"
