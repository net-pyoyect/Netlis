""" Subsistema de estabilidad de producción: escritura atómica con auto-recuperación (.bak) y escudo anti-excepciones en RAM."""
from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import threading
import traceback
from typing import Any

# Anillo de diagnóstico en memoria RAM (cero escritura de URLs o datos privados a disco)
CRASH_LOG_RING: deque[dict[str, str]] = deque(maxlen=50)
_SHIELD_INSTALLED = False


def record_diagnostic(kind: str, detail: str) -> None:
    """Registra un evento de estabilidad en el anillo en memoria RAM."""
    CRASH_LOG_RING.append(
        {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "detail": detail[:400],
        }
    )


def get_diagnostics() -> list[dict[str, str]]:
    return list(CRASH_LOG_RING)


def clear_diagnostics() -> None:
    CRASH_LOG_RING.clear()


def install_crash_shield() -> None:
    """Instala manejadores globales para evitar que un fallo aislado en un callback cierre todo el navegador."""
    global _SHIELD_INSTALLED
    if _SHIELD_INSTALLED:
        return
    _SHIELD_INSTALLED = True

    orig_excepthook = sys.excepthook

    def _safe_excepthook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            orig_excepthook(exc_type, exc_value, exc_tb)
            return
        tb_short = "".join(traceback.format_exception_only(exc_type, exc_value)).strip()
        record_diagnostic("unhandled_exception", tb_short)

    def _safe_thread_excepthook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
            return
        tb_short = "".join(traceback.format_exception_only(args.exc_type, args.exc_value)).strip()
        record_diagnostic("background_thread_exception", tb_short)

    sys.excepthook = _safe_excepthook
    threading.excepthook = _safe_thread_excepthook


def atomic_write_json(path: Path, data: Any) -> None:
    """Escribe JSON de forma atómica con fsync y conserva respaldo .bak verificado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    bak_path = path.with_suffix(path.suffix + ".bak")
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
            json.loads(existing)
            bak_path.write_text(existing, encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass

    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(serialized)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)


def safe_load_json(path: Path, default: Any) -> Any:
    """Carga JSON y se auto-recupera desde .bak si el archivo principal sufrió corrupción."""
    bak_path = path.with_suffix(path.suffix + ".bak")
    for candidate in (path, bak_path):
        if not candidate.is_file():
            continue
        try:
            parsed = json.loads(candidate.read_text(encoding="utf-8"))
            if type(parsed) is type(default):
                if candidate == bak_path:
                    record_diagnostic("config_recovered", f"Restaurado automáticamente desde {bak_path.name}")
                    try:
                        atomic_write_json(path, parsed)
                    except OSError:
                        pass
                return parsed
        except (OSError, json.JSONDecodeError):
            continue
    return default() if callable(default) else json.loads(json.dumps(default))
