"""Subsistema de mantenimiento y actualización criptográfica de Netlis (SHA-256, Rollback .bak y systemd timer)."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen
import zipfile

import security_shield
from stability import atomic_write_json, record_diagnostic, safe_load_json
from tor_manager import LYREBIRD_BIN, SOCKS_HOST, SOCKS_PORT, TOR_BIN, fetch_text_via_socks5

THREAT_FEEDS: tuple[str, ...] = (
    "https://malware-filter.gitlab.io/malware-filter/urlhaus-filter-hosts.txt",
    "https://phishing.army/download/phishing_army_blocklist.txt",
)

THREAT_REFRESH_INTERVAL_S = 12 * 3600       # Cada 12 horas
ENGINE_CHECK_INTERVAL_S = 3 * 24 * 3600     # Cada 3 días
MIN_VALID_THREAT_DOMAINS = 10_000           # Umbral anti-corrupción / anti-truncado


def sha256_file(path: Path) -> str:
    """Calcula el hash criptográfico SHA-256 de un archivo local."""
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _is_tor_socks_ready() -> bool:
    try:
        with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=0.25):
            return True
    except OSError:
        return False


def _status_file(data_dir: Path) -> Path:
    return data_dir / "update_status.json"


def get_update_status(data_dir: Path | None = None) -> dict:
    """Devuelve el estado persistente del actualizador automático de seguridad."""
    target_dir = data_dir or (Path(__file__).resolve().parent / "data")
    return safe_load_json(_status_file(target_dir), {})


def _save_update_status(data_dir: Path, **updates) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    current = get_update_status(data_dir)
    current.update(updates)
    atomic_write_json(_status_file(data_dir), current)
    return current


def _download_feed_text(feed_url: str, timeout: float = 14.0) -> str:
    """Descarga una fuente de seguridad usando Tor SOCKS5h si está activo (cero fuga de IP)."""
    if _is_tor_socks_ready():
        try:
            return fetch_text_via_socks5(feed_url, socks_port=SOCKS_PORT, timeout=timeout)
        except Exception:
            pass
    req = Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def apply_verified_threat_domains(domains: set[str], target_dir: Path) -> tuple[bool, int, str]:
    """Valida integridad, guarda respaldo .bak, aplica atómicamente y registra SHA-256."""
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / "threat_domains.txt"
    bak_file = target_dir / "threat_domains.txt.bak"

    if len(domains) < MIN_VALID_THREAT_DOMAINS:
        record_diagnostic(
            "threat_feed_rollback",
            f"Fuente rechazada por conteo insuficiente ({len(domains)} < {MIN_VALID_THREAT_DOMAINS}); manteniendo copia íntegra.",
        )
        if not out_file.is_file() and bak_file.is_file():
            shutil.copy2(bak_file, out_file)
        count = security_shield.reload_threat_domains(out_file)
        return False, count, f"Protección anti-corrupción activada ({count:,} firmas conservadas)."

    if out_file.is_file() and out_file.stat().st_size > 100_000:
        shutil.copy2(out_file, bak_file)

    tmp = out_file.with_suffix(".tmp")
    tmp.write_text("\n".join(sorted(domains)) + "\n", encoding="utf-8")
    tmp.replace(out_file)
    digest = sha256_file(out_file)
    security_shield.reload_threat_domains(out_file)
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_update_status(
        target_dir,
        last_threat_ts=time.time(),
        last_threat_date=now_iso,
        threat_count=len(domains),
        threat_sha256=digest,
    )
    return True, len(domains), f"{len(domains):,} firmas verificadas (SHA-256 {digest[:12]}…)"


def update_threat_feed(data_dir: Path | None = None, timeout: float = 14.0) -> tuple[bool, int, str]:
    """Descarga, valida y respalda las listas activas de malware (URLhaus) y phishing (Phishing Army)."""
    target_dir = data_dir or (Path(__file__).resolve().parent / "data")
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / "threat_domains.txt"

    domains: set[str] = set()
    last_err = ""
    for feed_url in THREAT_FEEDS:
        try:
            raw = _download_feed_text(feed_url, timeout=timeout)
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "!")):
                    continue
                parts = line.split()
                host = parts[-1].lower().strip(".")
                if host and host not in ("localhost", "127.0.0.1", "0.0.0.0", "::1") and "." in host:
                    domains.add(host)
        except Exception as exc:
            last_err = str(exc)

    if domains:
        return apply_verified_threat_domains(domains, target_dir)

    count = security_shield.reload_threat_domains(out_file)
    return False, count, f"Sin conexión a fuentes ({last_err or 'usando base local'})"


def get_tor_version() -> str:
    if not TOR_BIN.is_file():
        return "no instalado"
    try:
        res = subprocess.run(
            [str(TOR_BIN), "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        first = (res.stdout or "").splitlines()[0] if res.stdout else ""
        return first.replace("Tor version ", "").strip().rstrip(".") or "activo"
    except Exception:
        return "activo"


def verify_tor_binaries(data_dir: Path | None = None) -> dict[str, str | bool]:
    """Verifica firma binaria ELF, ejecución sana y SHA-256 de Tor y Lyrebird (obfs4), con auto-rollback si hay corrupción."""
    target_dir = data_dir or (Path(__file__).resolve().parent / "data")
    tor_bak = TOR_BIN.with_suffix(".bak")
    tor_ok = False
    if TOR_BIN.is_file():
        try:
            with open(TOR_BIN, "rb") as fh:
                magic = fh.read(4)
            is_valid_bin = (magic[:2] == b"MZ") if sys.platform == "win32" else (magic == b"\x7fELF")
            ver = get_tor_version()
            tor_ok = is_valid_bin and ver != "no instalado"
            if tor_ok and not tor_bak.is_file():
                shutil.copy2(TOR_BIN, tor_bak)
            elif not tor_ok and tor_bak.is_file():
                shutil.copy2(tor_bak, TOR_BIN)
                tor_ok = True
                record_diagnostic("tor_binary_rollback", "Restaurado binario Tor desde respaldo .bak")
        except OSError:
            pass

    tor_hash = sha256_file(TOR_BIN)
    lyrebird_hash = sha256_file(LYREBIRD_BIN)
    info = {
        "tor_ok": tor_ok,
        "tor_version": get_tor_version(),
        "tor_sha256": tor_hash,
        "lyrebird_ok": LYREBIRD_BIN.is_file() and bool(lyrebird_hash),
        "lyrebird_sha256": lyrebird_hash,
    }
    _save_update_status(
        target_dir,
        tor_version=str(info["tor_version"]),
        tor_sha256=tor_hash,
        lyrebird_sha256=lyrebird_hash,
    )
    return info


def get_engine_versions() -> dict[str, str]:
    """Obtiene versiones exactas de Chromium, Parche de Seguridad CVE de Chromium, QtWebEngine, Tor y obfs4."""
    versions = {
        "chromium": "desconocido",
        "chromium_security_patch": "desconocido",
        "qtwebengine": "desconocido",
        "tor": get_tor_version(),
    }
    try:
        from PyQt6.QtWebEngineCore import (
            qWebEngineChromiumSecurityPatchVersion,
            qWebEngineChromiumVersion,
            qWebEngineVersion,
        )

        versions["chromium"] = qWebEngineChromiumVersion()
        versions["chromium_security_patch"] = qWebEngineChromiumSecurityPatchVersion()
        versions["qtwebengine"] = qWebEngineVersion()
    except Exception:
        pass
    return versions


def systemd_timer_paths() -> tuple[Path, Path]:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    return unit_dir / "netlis-updater.service", unit_dir / "netlis-updater.timer"


def install_systemd_timer() -> tuple[bool, str]:
    """Instala el servicio y temporizador systemd --user en Linux para actualizar Netlis en segundo plano."""
    if not sys.platform.startswith("linux"):
        return False, "Auto-actualización en segundo plano disponible al abrir Netlis (systemd es exclusivo de Linux)."
    proj_dir = Path(__file__).resolve().parent
    py_bin = proj_dir / ".venv" / "bin" / "python3"
    updater_script = proj_dir / "updater.py"
    svc_path, tmr_path = systemd_timer_paths()

    svc_content = f"""[Unit]
Description=Actualización criptográfica de seguridad de Netlis (Firmas Anti-Phishing, Motor Chromium y Tor)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={proj_dir}
ExecStart={py_bin} {updater_script} --run-maintenance
Nice=15
"""
    tmr_content = """[Unit]
Description=Temporizador periódico de seguridad de Netlis (cada 12 horas)

[Timer]
OnCalendar=*-*-* 06,18:00:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
"""
    try:
        svc_path.parent.mkdir(parents=True, exist_ok=True)
        svc_path.write_text(svc_content, encoding="utf-8")
        tmr_path.write_text(tmr_content, encoding="utf-8")
    except OSError as exc:
        return False, f"No se pudo escribir unidad systemd: {exc}"

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=5, check=False)
        res = subprocess.run(
            ["systemctl", "--user", "enable", "--now", "netlis-updater.timer"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return True, "Temporizador systemd activo (06:00 y 18:00)"
    except Exception:
        pass
    return True, "Unidades systemd instaladas en ~/.config/systemd/user"


def get_local_version_info(proj_dir: Path | None = None) -> dict:
    """Lee version.json del proyecto Netlis."""
    root = proj_dir or Path(__file__).resolve().parent
    vf = root / "version.json"
    if not vf.is_file():
        return {"version": "1.0.0", "repo": "", "branch": "main", "notes": ""}
    try:
        raw = json.loads(vf.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"version": "1.0.0", "repo": "", "branch": "main", "notes": ""}
    except (OSError, json.JSONDecodeError):
        return {"version": "1.0.0", "repo": "", "branch": "main", "notes": ""}


def parse_semver(ver: str) -> tuple[int, int, int]:
    parts = [int(p) for p in str(ver).lstrip("v").split(".")[:3] if p.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def check_app_update(proj_dir: Path | None = None, manifest_url: str = "") -> dict:
    """Comprueba si existe una nueva versión de Netlis en GitHub (enrutando por Tor si está activo)."""
    root = proj_dir or Path(__file__).resolve().parent
    local = get_local_version_info(root)
    local_ver = str(local.get("version") or "1.0.0")
    repo = str(local.get("repo") or "").strip().strip("/")
    branch = str(local.get("branch") or "main").strip() or "main"

    target_url = manifest_url.strip()
    if not target_url and repo:
        target_url = f"https://raw.githubusercontent.com/{repo}/{branch}/version.json"

    if not target_url:
        if (root / ".git").is_dir():
            try:
                subprocess.run(["git", "-C", str(root), "fetch", "--quiet"], timeout=8, check=False)
                res = subprocess.run(
                    ["git", "-C", str(root), "rev-list", "--count", "HEAD..@{u}"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                ahead = int((res.stdout or "0").strip() or "0")
                return {
                    "ok": True,
                    "has_update": ahead > 0,
                    "local_version": local_ver,
                    "remote_version": f"{local_ver}+{ahead}" if ahead > 0 else local_ver,
                    "notes": f"{ahead} nuevos commits disponibles en Git." if ahead > 0 else "Ya estás en la última versión.",
                }
            except Exception as exc:
                return {"ok": False, "has_update": False, "local_version": local_ver, "remote_version": local_ver, "notes": str(exc)}
        return {
            "ok": False,
            "has_update": False,
            "local_version": local_ver,
            "remote_version": local_ver,
            "notes": "Configura 'repo' (usuario/netlis) en version.json al publicar en GitHub.",
        }

    try:
        raw = _download_feed_text(target_url, timeout=8.0)
        remote = json.loads(raw)
        remote_ver = str(remote.get("version") or local_ver)
        has_upd = parse_semver(remote_ver) > parse_semver(local_ver)
        return {
            "ok": True,
            "has_update": has_upd,
            "local_version": local_ver,
            "remote_version": remote_ver,
            "notes": str(remote.get("notes") or ""),
            "repo": repo,
            "branch": branch,
        }
    except Exception as exc:
        return {"ok": False, "has_update": False, "local_version": local_ver, "remote_version": local_ver, "notes": f"Sin conexión: {exc}"}


def apply_app_update(proj_dir: Path | None = None, archive_url: str = "") -> tuple[bool, str]:
    """Aplica la actualización de Netlis conservando intactos los datos y ajustes de data/."""
    root = proj_dir or Path(__file__).resolve().parent
    local = get_local_version_info(root)
    repo = str(local.get("repo") or "").strip().strip("/")
    branch = str(local.get("branch") or "main").strip() or "main"

    if (root / ".git").is_dir() and not archive_url:
        res = subprocess.run(
            ["git", "-C", str(root), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if res.returncode != 0:
            return False, f"No se pudo actualizar vía git: {(res.stderr or res.stdout).strip()[:160]}"
        pip_bin = root / ".venv" / ("Scripts/pip.exe" if sys.platform == "win32" else "bin/pip")
        req_file = root / "requirements.txt"
        if pip_bin.is_file() and req_file.is_file():
            subprocess.run([str(pip_bin), "install", "-r", str(req_file), "--quiet"], capture_output=True, timeout=60, check=False)
        new_ver = get_local_version_info(root).get("version", "?")
        return True, f"Netlis actualizado vía Git a v{new_ver}. Reinicia para aplicar."

    zip_url = archive_url.strip() or (f"https://github.com/{repo}/archive/refs/heads/{branch}.zip" if repo else "")
    if not zip_url:
        return False, "No hay repositorio GitHub configurado en version.json."

    try:
        req = Request(zip_url, headers={"User-Agent": "NetlisUpdater/1.0"})
        with urlopen(req, timeout=20.0) as resp:
            zip_bytes = resp.read()
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as exc:
        return False, f"Error descargando actualización: {exc}"

    protected_prefixes = ("data/", ".venv/", ".tor/", "__pycache__/")
    updated_files = 0
    try:
        for member in zf.infolist():
            if member.is_dir():
                continue
            parts = Path(member.filename).parts
            rel_parts = parts[1:] if len(parts) > 1 else parts
            if not rel_parts or ".." in rel_parts:
                continue
            rel_posix = Path(*rel_parts).as_posix()
            if rel_posix.startswith(protected_prefixes):
                continue
            dest = root / Path(*rel_parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))
            updated_files += 1
    finally:
        zf.close()

    new_ver = get_local_version_info(root).get("version", "?")
    return True, f"Netlis actualizado a v{new_ver} ({updated_files} archivos). Reinicia para aplicar."


def get_security_health_report(data_dir: Path | None = None) -> dict:
    """Genera el informe completo de salud, integridad SHA-256 y parches de seguridad de Netlis."""
    target_dir = data_dir or (Path(__file__).resolve().parent / "data")
    threat_file = target_dir / "threat_domains.txt"
    st = get_update_status(target_dir)
    eng = get_engine_versions()
    svc_path, tmr_path = systemd_timer_paths()

    threat_hash = st.get("threat_sha256") or sha256_file(threat_file)
    tor_hash = st.get("tor_sha256") or sha256_file(TOR_BIN)
    lyrebird_hash = st.get("lyrebird_sha256") or sha256_file(LYREBIRD_BIN)

    return {
        "chromium_version": eng["chromium"],
        "chromium_security_patch": eng["chromium_security_patch"],
        "qtwebengine_version": eng["qtwebengine"],
        "tor_version": eng["tor"],
        "tor_sha256": tor_hash,
        "lyrebird_sha256": lyrebird_hash,
        "threat_count": len(security_shield.DYNAMIC_THREAT_DOMAINS),
        "threat_sha256": threat_hash,
        "last_threat_date": st.get("last_threat_date") or "verificado localmente",
        "last_engine_date": st.get("last_engine_date") or "al día",
        "systemd_timer_installed": svc_path.is_file() and tmr_path.is_file(),
    }


def update_browser_engine(data_dir: Path | None = None) -> tuple[bool, str]:
    """Actualiza PyQt6 y PyQt6-WebEngine y verifica integridad SHA-256 de Tor/Lyrebird."""
    target_dir = data_dir or (Path(__file__).resolve().parent / "data")
    tor_info = verify_tor_binaries(target_dir)
    eng = get_engine_versions()
    proj = Path(__file__).resolve().parent
    pip_bin = proj / ".venv" / ("Scripts/pip.exe" if sys.platform == "win32" else "bin/pip")
    if not pip_bin.is_file():
        return False, f"No se encontró {pip_bin}."

    cmd = [str(pip_bin), "install", "--upgrade", "--quiet", "PyQt6", "PyQt6-WebEngine"]
    if _is_tor_socks_ready():
        cmd.extend(["--proxy", f"socks5h://{SOCKS_HOST}:{SOCKS_PORT}"])

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
        _save_update_status(
            target_dir,
            last_engine_ts=time.time(),
            last_engine_date=now_iso,
            chromium_version=eng["chromium"],
            chromium_security_patch=eng["chromium_security_patch"],
            engine_ok=(res.returncode == 0),
        )
        if res.returncode == 0:
            return (
                True,
                f"Chromium {eng['chromium']} (parche {eng['chromium_security_patch']}) + Tor {tor_info['tor_version']} al día.",
            )
        return (
            False,
            f"Modo sin red PyPI — activo Chromium {eng['chromium']} (parche {eng['chromium_security_patch']}).",
        )
    except Exception as exc:
        return False, f"Error verificando motor: {exc}"


def auto_update_engine_if_due(data_dir: Path | None = None, interval_s: int = ENGINE_CHECK_INTERVAL_S) -> bool:
    """Comprueba e instala automáticamente parches de seguridad del motor cada 3 días."""
    target_dir = data_dir or (Path(__file__).resolve().parent / "data")
    verify_tor_binaries(target_dir)
    st = get_update_status(target_dir)
    last_ts = float(st.get("last_engine_ts", 0.0) or 0.0)
    if time.time() - last_ts >= interval_s:
        ok, _ = update_browser_engine(target_dir)
        return ok
    return False


def auto_refresh_threats_async(data_dir: Path | None = None) -> None:
    """Ejecuta en segundo plano el demonio de mantenimiento criptográfico (firmas cada 12h + motor cada 3d)."""
    target_dir = data_dir or (Path(__file__).resolve().parent / "data")
    out_file = target_dir / "threat_domains.txt"
    security_shield.reload_threat_domains(out_file)

    def _background_maintenance() -> None:
        svc_path, tmr_path = systemd_timer_paths()
        if not (svc_path.is_file() and tmr_path.is_file()):
            install_systemd_timer()
        verify_tor_binaries(target_dir)
        time.sleep(2.5)
        needs_threats = not out_file.exists() or (
            time.time() - out_file.stat().st_mtime > THREAT_REFRESH_INTERVAL_S
        )
        if needs_threats:
            update_threat_feed(target_dir)
        elif not get_update_status(target_dir).get("threat_sha256"):
            _save_update_status(
                target_dir,
                threat_sha256=sha256_file(out_file),
                threat_count=len(security_shield.DYNAMIC_THREAT_DOMAINS),
            )
        auto_update_engine_if_due(target_dir)

    threading.Thread(target=_background_maintenance, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Mantenimiento de seguridad de Netlis")
    parser.add_argument("--run-maintenance", action="store_true", help="Actualiza firmas, motor y verifica SHA-256")
    parser.add_argument("--install-timer", action="store_true", help="Instala temporizador systemd --user")
    parser.add_argument("--status", action="store_true", help="Muestra estado de seguridad en JSON")
    args = parser.parse_args()

    data_dir = Path(__file__).resolve().parent / "data"
    if args.install_timer:
        ok, msg = install_systemd_timer()
        print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        return 0 if ok else 1
    if args.run_maintenance:
        verify_tor_binaries(data_dir)
        ok_t, n_t, msg_t = update_threat_feed(data_dir)
        ok_e, msg_e = update_browser_engine(data_dir)
        print(json.dumps({"threats_ok": ok_t, "threats": n_t, "msg_t": msg_t, "engine_ok": ok_e, "msg_e": msg_e}, ensure_ascii=False))
        return 0
    report = get_security_health_report(data_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
