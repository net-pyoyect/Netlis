#!/usr/bin/env python3
"""Netlis Doctor: buscador y reparador automático de errores de instalación y arranque."""

from __future__ import annotations

import argparse
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FONT_DIRS = (
    "/usr/share/fonts/liberation",
    "/usr/share/fonts/noto",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/liberation2",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/liberation-sans",
    "/usr/share/fonts/google-noto",
)

CORE_PY_FILES = (
    "browser.py",
    "privacy.py",
    "plugins.py",
    "dialogs.py",
    "updater.py",
    "tor_manager.py",
)

EXEC_SCRIPTS = (
    "launch.sh",
    "install.sh",
    "install_desktop.sh",
    "update.sh",
    "doctor.sh",
    "release.py",
)


def _ok(msg: str) -> None:
    print(f"  [OK]    {msg}")


def _warn(msg: str) -> None:
    print(f"  [AVISO] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


def _fix(msg: str) -> None:
    print(f"  [FIX]   {msg}")


def _has_ldconfig_lib(pattern: str) -> bool:
    ldconfig = shutil.which("ldconfig") or "/sbin/ldconfig"
    if not Path(ldconfig).exists():
        return True
    try:
        res = subprocess.run([ldconfig, "-p"], capture_output=True, text=True, timeout=5, check=False)
        return pattern in (res.stdout or "")
    except Exception:
        return True


def _ask_yes_no(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        ans = input(f"{prompt} [s/N]: ").strip().lower()
        return ans in ("s", "si", "sí", "y", "yes")
    except EOFError:
        return False


def _install_system_packages(auto_fix: bool) -> bool:
    if shutil.which("apt-get"):
        cmd = (
            "sudo apt-get update || true; "
            "sudo apt-get install -y python3 python3-venv python3-pip git tor "
            "libxcb-cursor0 libnss3 libegl1 libxkbcommon0 fonts-liberation fonts-dejavu-core"
        )
    elif shutil.which("pacman"):
        cmd = "sudo pacman -Sy --needed --noconfirm python git tor nss libxcb xcb-util-cursor libxkbcommon ttf-liberation noto-fonts"
    elif shutil.which("dnf"):
        cmd = "sudo dnf install -y python3 python3-pip git tor nss xcb-util-cursor libxkbcommon liberation-fonts"
    else:
        _err("No se detectó apt-get, pacman ni dnf; instala manualmente libxcb-cursor0, libnss3, libegl1, libxkbcommon0 y fuentes.")
        return False

    print(f"\n  Comando de reparación del sistema:\n    {cmd}\n")
    if auto_fix or _ask_yes_no("  ¿Quieres ejecutar ahora este comando para instalar lo que falta?"):
        res = subprocess.run(["bash", "-c", cmd], check=False)
        return res.returncode == 0
    return False


def run_doctor(auto_fix: bool = False) -> int:
    print("=== Netlis Doctor — Buscador y Reparador de Errores ===")
    print(f"Carpeta: {ROOT}\n")
    issues = 0
    fixed = 0

    # 1. Permisos de scripts
    print("[1/6] Verificando permisos de scripts...")
    for name in EXEC_SCRIPTS:
        p = ROOT / name
        if not p.exists():
            continue
        if not os.access(p, os.X_OK):
            try:
                p.chmod(p.stat().st_mode | 0o755)
                _fix(f"Permiso +x agregado a {name}")
                fixed += 1
            except OSError as exc:
                _err(f"No se pudo dar +x a {name}: {exc}")
                issues += 1
        else:
            _ok(f"{name} es ejecutable")

    # 2. Librerías del sistema y fuentes (Qt6 / WebEngine / Fontconfig)
    print("\n[2/6] Verificando librerías gráficas (Qt6/XCB) y fuentes...")
    if sys.platform == "win32":
        _ok("Sistema Windows detectado (Qt6 usa librerías nativas de Windows)")
    else:
        missing_sys: list[str] = []
        for lib_name, pkg_hint in (
            ("libxcb-cursor.so.0", "libxcb-cursor0"),
            ("libnss3.so", "libnss3"),
            ("libEGL.so.1", "libegl1"),
            ("libxkbcommon.so.0", "libxkbcommon0"),
        ):
            if _has_ldconfig_lib(lib_name):
                _ok(f"Librería presente: {lib_name}")
            else:
                _err(f"Falta librería del sistema: {lib_name} (paquete {pkg_hint})")
                missing_sys.append(pkg_hint)

        if any(Path(d).is_dir() for d in FONT_DIRS):
            _ok("Fuentes del sistema encontradas (sin riesgo de cuadritos □□□□)")
        else:
            _err("No se encontraron fuentes Liberation/Noto/DejaVu (las letras saldrían como □□□□)")
            missing_sys.append("fonts-liberation")

        if missing_sys:
            if _install_system_packages(auto_fix):
                _fix("Dependencias del sistema instaladas")
                fixed += 1
            else:
                issues += len(missing_sys)

    # 3. Entorno virtual .venv y PyQt6
    print("\n[3/6] Verificando entorno Python (.venv) y PyQt6-WebEngine...")
    if sys.platform == "win32":
        venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
        venv_pip = ROOT / ".venv" / "Scripts" / "pip.exe"
    else:
        venv_py = ROOT / ".venv" / "bin" / "python3"
        venv_pip = ROOT / ".venv" / "bin" / "pip"
    if not venv_py.is_file():
        _err("No existe .venv/bin/python3")
        _fix("Creando entorno virtual .venv e instalando requirements.txt...")
        shutil.rmtree(ROOT / ".venv", ignore_errors=True)
        r1 = subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=False)
        r2 = subprocess.run([str(venv_pip), "install", "-r", str(ROOT / "requirements.txt")], check=False)
        if r1.returncode == 0 and r2.returncode == 0:
            _fix(".venv y dependencias Python reparados")
            fixed += 1
        else:
            _err("No se pudo crear .venv (en Ubuntu/Debian instala: sudo apt install -y python3-venv)")
            issues += 1
    else:
        chk = subprocess.run(
            [str(venv_py), "-c", "import PyQt6, PyQt6.QtWebEngineWidgets; print('PYQT_OK')"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if chk.returncode == 0 and "PYQT_OK" in (chk.stdout or ""):
            _ok("PyQt6 y PyQt6-WebEngine importan correctamente")
        else:
            _err(f"Falla al importar PyQt6: {(chk.stderr or chk.stdout).strip()[:160]}")
            _fix("Reinstalando dependencias en .venv...")
            r_pip = subprocess.run([str(venv_pip), "install", "-r", str(ROOT / "requirements.txt")], check=False)
            if r_pip.returncode == 0:
                _fix("Dependencias Python reparadas")
                fixed += 1
            else:
                issues += 1

    # 4. Integridad de código Python
    print("\n[4/6] Verificando sintaxis de archivos principales...")
    for fname in CORE_PY_FILES:
        fpath = ROOT / fname
        if not fpath.exists():
            _err(f"Falta archivo esencial: {fname}")
            issues += 1
            continue
        try:
            py_compile.compile(str(fpath), doraise=True)
            _ok(f"{fname} sin errores de sintaxis")
        except py_compile.PyCompileError as exc:
            _err(f"Error de sintaxis en {fname}: {exc}")
            issues += 1

    # 5. Tor y AppArmor
    print("\n[5/6] Verificando motor Tor y sandbox del sistema...")
    if shutil.which("tor") or (ROOT / ".tor").exists():
        _ok("Binario de Tor disponible")
    else:
        _warn("Tor no encontrado en PATH (el modo 'Sin Tor ⚡' funcionará, pero Modo Tor requiere 'tor')")

    apparmor_userns = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
    if apparmor_userns.is_file() and apparmor_userns.read_text(encoding="utf-8", errors="ignore").strip() == "1":
        _ok("AppArmor userns activo: configurar permiso del sandbox si Chromium no inicia")

    # 6. Acceso directo .desktop
    print("\n[6/6] Verificando acceso directo del menú...")
    desk_file = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "applications" / "netlis.desktop"
    expected_exec = f"Exec={ROOT}/launch.sh"
    if desk_file.is_file() and expected_exec in desk_file.read_text(encoding="utf-8", errors="ignore"):
        _ok(f"Acceso directo correcto en {desk_file}")
    else:
        _warn("Acceso directo ausente o apunta a otra carpeta; regenerando...")
        res_d = subprocess.run(["bash", str(ROOT / "install_desktop.sh")], check=False)
        if res_d.returncode == 0:
            _fix(f"Acceso directo actualizado en {desk_file}")
            fixed += 1
        else:
            issues += 1

    print("\n=== Resumen de Netlis Doctor ===")
    print(f"  Reparaciones aplicadas: {fixed}")
    print(f"  Errores pendientes:     {issues}")
    if issues == 0:
        print("\nTodo listo. Puedes abrir Netlis con: ./launch.sh")
        return 0
    print("\nQuedaron errores pendientes; revisa los mensajes [ERROR] arriba.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Buscador y reparador de errores de Netlis")
    parser.add_argument("--fix", action="store_true", help="Instala automáticamente dependencias faltantes sin preguntar")
    args = parser.parse_args()
    return run_doctor(auto_fix=args.fix)


if __name__ == "__main__":
    raise SystemExit(main())
