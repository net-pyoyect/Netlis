"""Gestor del motor Tor integrado en Netlis (ocultación real de IP, rotación en vivo y SOCKS5 sin fugas)."""
from __future__ import annotations

import atexit
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time

NETLIS_DIR = Path(__file__).resolve().parent


def _resolve_tor_bin() -> Path:
    candidates = [
        NETLIS_DIR / ".tor" / "usr" / "bin" / "tor",
        NETLIS_DIR / ".tor" / "tor" / "tor.exe",
        NETLIS_DIR / ".tor" / "Tor" / "tor.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    sys_tor = shutil.which("tor.exe") or shutil.which("tor")
    return Path(sys_tor) if sys_tor else candidates[0]


def _resolve_lyrebird_bin() -> Path:
    candidates = [
        NETLIS_DIR / ".tor" / "pt" / "lyrebird",
        NETLIS_DIR / ".tor" / "pt" / "lyrebird.exe",
        NETLIS_DIR / ".tor" / "Tor" / "PluggableTransports" / "lyrebird.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    sys_pt = shutil.which("lyrebird.exe") or shutil.which("lyrebird") or shutil.which("obfs4proxy.exe") or shutil.which("obfs4proxy")
    return Path(sys_pt) if sys_pt else candidates[0]


TOR_BIN = _resolve_tor_bin()
LYREBIRD_BIN = _resolve_lyrebird_bin()

PT_CONFIG_JSON = NETLIS_DIR / ".tor" / "pt" / "pt_config.json"
_LOCAL_GEOIP4 = NETLIS_DIR / ".tor" / "usr" / "share" / "tor" / "geoip"
_LOCAL_GEOIP6 = NETLIS_DIR / ".tor" / "usr" / "share" / "tor" / "geoip6"
_WIN_GEOIP4 = NETLIS_DIR / ".tor" / "Data" / "Tor" / "geoip"
_WIN_GEOIP6 = NETLIS_DIR / ".tor" / "Data" / "Tor" / "geoip6"
GEOIP_V4 = _LOCAL_GEOIP4 if _LOCAL_GEOIP4.is_file() else (_WIN_GEOIP4 if _WIN_GEOIP4.is_file() else Path("/usr/share/tor/geoip"))
GEOIP_V6 = _LOCAL_GEOIP6 if _LOCAL_GEOIP6.is_file() else (_WIN_GEOIP6 if _WIN_GEOIP6.is_file() else Path("/usr/share/tor/geoip6"))


def load_official_obfs4_bridges() -> list[str]:
    if not PT_CONFIG_JSON.is_file():
        return []
    try:
        data = json.loads(PT_CONFIG_JSON.read_text(encoding="utf-8"))
        return [str(b).strip() for b in data.get("bridges", {}).get("obfs4", []) if str(b).strip()]
    except (OSError, json.JSONDecodeError):
        return []

SOCKS_HOST = "127.0.0.1"
SOCKS_PORT = 19050
CONTROL_PORT = 19051
DEFAULT_TOR_PROXY = f"socks5://{SOCKS_HOST}:{SOCKS_PORT}"


class EmbeddedTorManager:
    """Administra el proceso Tor local de Netlis sin requerir permisos root."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = (data_dir or (NETLIS_DIR / "data")) / "tor_consensus"
        self.proc: subprocess.Popen | None = None
        atexit.register(self.stop)

    def is_available(self) -> bool:
        return TOR_BIN.is_file()

    def is_running(self) -> bool:
        try:
            with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=0.2):
                return True
        except OSError:
            return False

    def start(self, ip_region: str = "auto", use_bridges: bool = False, wait_seconds: float = 12.0) -> bool:
        if self.is_running():
            self.set_bridges_enabled(use_bridges)
            self.set_exit_region(ip_region)
            return True
        if not self.is_available():
            return False

        self.data_dir.mkdir(parents=True, exist_ok=True)
        torrc = self.data_dir / "torrc"
        lines = [
            f"DataDirectory {self.data_dir}",
            f"SocksPort {SOCKS_HOST}:{SOCKS_PORT} IsolateDestAddr IsolateDestPort",
            f"ControlPort {SOCKS_HOST}:{CONTROL_PORT}",
            "CookieAuthentication 0",
            "AvoidDiskWrites 1",
            "ClientOnly 1",
            "MaxMemInQueues 48 MB",
            "MaxCircuitDirtiness 300",
            "NumEntryGuards 2",
            "CircuitBuildTimeout 10",
            "KeepalivePeriod 60",
        ]
        if LYREBIRD_BIN.is_file():
            lines.append(f"ClientTransportPlugin obfs4,webtunnel exec {LYREBIRD_BIN}")
            bridges = load_official_obfs4_bridges()
            if use_bridges and bridges:
                lines.append("UseBridges 1")
                for br in bridges:
                    lines.append(f"Bridge {br}")
        if GEOIP_V4.is_file():
            lines.append(f"GeoIPFile {GEOIP_V4}")
        if GEOIP_V6.is_file():
            lines.append(f"GeoIPv6File {GEOIP_V6}")
        if ip_region and ip_region != "auto":
            lines.append(f"ExitNodes {{{ip_region}}}")
            lines.append("StrictNodes 1")

        torrc.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log_path = self.data_dir / "tor.log"
        log_file = open(log_path, "w", encoding="utf-8")
        popen_kwargs: dict = {
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
        }
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self.proc = subprocess.Popen([str(TOR_BIN), "-f", str(torrc)], **popen_kwargs)

        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return False
            try:
                txt = log_path.read_text(encoding="utf-8", errors="ignore")
                if "Bootstrapped 100%" in txt:
                    return True
            except OSError:
                pass
            time.sleep(0.25)
        return self.is_running()

    def start_async(self, ip_region: str = "auto", use_bridges: bool = False) -> None:
        """Arranca el circuito Tor en segundo plano para que la ventana de Netlis abra al instante."""
        threading.Thread(
            target=self.start,
            args=(ip_region, use_bridges, 25.0),
            daemon=True,
        ).start()

    def set_bridges_enabled(self, enabled: bool) -> tuple[bool, str]:
        """Activa o desactiva en vivo los puentes anticensura obfs4 (lyrebird) sin reiniciar Tor."""
        if not enabled:
            return self.control_cmd("RESETCONF UseBridges Bridge", "SIGNAL NEWNYM")
        bridges = load_official_obfs4_bridges()
        if not bridges or not LYREBIRD_BIN.is_file():
            return False, "No se encontraron puentes obfs4."
        bridge_args = " ".join(f'Bridge="{b}"' for b in bridges[:4])
        return self.control_cmd(f"SETCONF UseBridges=1 {bridge_args}", "SIGNAL NEWNYM")

    def control_cmd(self, *commands: str) -> tuple[bool, str]:
        try:
            with socket.create_connection((SOCKS_HOST, CONTROL_PORT), timeout=1.5) as sock:
                payload = 'AUTHENTICATE ""\r\n' + "\r\n".join(commands) + "\r\nQUIT\r\n"
                sock.sendall(payload.encode("utf-8"))
                resp = sock.recv(1024).decode("utf-8", errors="ignore")
                ok = "250 OK" in resp
                return ok, resp.strip()
        except OSError as exc:
            return False, str(exc)

    def set_exit_region(self, ip_region: str) -> tuple[bool, str]:
        if not ip_region or ip_region == "auto":
            return self.control_cmd("RESETCONF ExitNodes StrictNodes", "SIGNAL NEWNYM")
        return self.control_cmd(
            f'SETCONF ExitNodes="{{{ip_region}}}" StrictNodes=1',
            "SIGNAL NEWNYM",
        )

    def stop(self, wipe_files: bool = False) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2.5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if wipe_files and self.data_dir.exists():
            shutil.rmtree(self.data_dir, ignore_errors=True)


def _decode_chunked(raw_body: bytes) -> bytes:
    out = bytearray()
    idx = 0
    n = len(raw_body)
    while idx < n:
        rn = raw_body.find(b"\r\n", idx)
        if rn == -1:
            break
        line = raw_body[idx:rn].split(b";", 1)[0].strip()
        if not line:
            idx = rn + 2
            continue
        try:
            size = int(line, 16)
        except ValueError:
            return raw_body
        if size == 0:
            break
        start = rn + 2
        out.extend(raw_body[start : start + size])
        idx = start + size + 2
    return bytes(out)


def fetch_text_via_socks5(
    url_str: str,
    socks_port: int = SOCKS_PORT,
    timeout: float = 14.0,
    max_redirects: int = 3,
) -> str:
    """Descarga texto HTTPS/HTTP pasando DNS y tráfico 100% por SOCKS5h (cero fuga de IP o DNS)."""
    from urllib.parse import urljoin, urlparse

    current = url_str
    for _ in range(max_redirects + 1):
        parsed = urlparse(current)
        scheme = parsed.scheme.lower()
        if scheme not in ("https", "http"):
            raise ValueError(f"Esquema no soportado: {scheme}")
        host = parsed.hostname or ""
        if not host:
            raise ValueError("URL inválida")
        port = parsed.port or (443 if scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        with socket.create_connection((SOCKS_HOST, socks_port), timeout=timeout) as raw_sock:
            raw_sock.settimeout(timeout)
            raw_sock.sendall(b"\x05\x01\x00")
            if raw_sock.recv(2) != b"\x05\x00":
                raise RuntimeError("Fallo de saludo SOCKS5")

            host_bytes = host.encode("idna")
            req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + port.to_bytes(2, "big")
            raw_sock.sendall(req)
            rep = raw_sock.recv(4)
            if len(rep) < 4 or rep[1] != 0x00:
                raise RuntimeError("No se pudo abrir circuito SOCKS5")
            atyp = rep[3]
            if atyp == 1:
                raw_sock.recv(6)
            elif atyp == 3:
                ln = raw_sock.recv(1)[0]
                raw_sock.recv(ln + 2)
            elif atyp == 4:
                raw_sock.recv(18)

            http_req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "User-Agent: Mozilla/5.0\r\n"
                "Accept: */*\r\n"
                "Accept-Encoding: identity\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")

            if scheme == "https":
                ctx = ssl.create_default_context()
                with ctx.wrap_socket(raw_sock, server_hostname=host) as tls:
                    tls.sendall(http_req)
                    chunks = []
                    while True:
                        buf = tls.recv(16384)
                        if not buf:
                            break
                        chunks.append(buf)
            else:
                raw_sock.sendall(http_req)
                chunks = []
                while True:
                    buf = raw_sock.recv(16384)
                    if not buf:
                        break
                    chunks.append(buf)

        raw_bytes = b"".join(chunks)
        head_bytes, _, body_bytes = raw_bytes.partition(b"\r\n\r\n")
        head_text = head_bytes.decode("iso-8859-1", errors="ignore")
        lines = head_text.splitlines()
        status_code = 200
        if lines:
            parts = lines[0].split()
            if len(parts) >= 2 and parts[1].isdigit():
                status_code = int(parts[1])
        headers: dict[str, str] = {}
        for hline in lines[1:]:
            if ":" in hline:
                k, v = hline.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        if status_code in (301, 302, 303, 307, 308) and "location" in headers:
            current = urljoin(current, headers["location"])
            continue
        if status_code >= 400:
            raise RuntimeError(f"HTTP {status_code}")
        if "chunked" in headers.get("transfer-encoding", "").lower():
            body_bytes = _decode_chunked(body_bytes)
        return body_bytes.decode("utf-8", errors="ignore")

    raise RuntimeError("Demasiadas redirecciones")


def fetch_json_via_socks5(host: str, path: str, socks_port: int = SOCKS_PORT, timeout: float = 10.0) -> dict:
    """Realiza una petición HTTPS pasando nombre DNS y tráfico 100% por SOCKS5h (cero fuga DNS)."""
    body = fetch_text_via_socks5(f"https://{host}{path}", socks_port=socks_port, timeout=timeout)
    start = body.find("{")
    end = body.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Respuesta JSON inválida")
    return json.loads(body[start : end + 1])


def check_exit_ip(use_tor: bool = True, socks_port: int = SOCKS_PORT) -> dict[str, str | bool]:
    """Devuelve la IP pública de salida real que ven los sitios web."""
    if use_tor:
        tor_info = fetch_json_via_socks5("check.torproject.org", "/api/ip", socks_port=socks_port)
        ip = str(tor_info.get("IP", "?"))
        is_tor = bool(tor_info.get("IsTor", False))
        country = "Tor Exit"
        try:
            geo = fetch_json_via_socks5("ipinfo.io", f"/{ip}/json", socks_port=socks_port, timeout=6.0)
            country = f"{geo.get('city', '')}, {geo.get('country', '')}".strip(", ")
        except Exception:
            pass
        return {"ip": ip, "is_tor": is_tor, "location": country}

    from urllib.request import urlopen

    with urlopen("https://ipinfo.io/json", timeout=5.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "ip": str(data.get("ip", "?")),
        "is_tor": False,
        "location": f"{data.get('city', '')}, {data.get('country', '')}".strip(", "),
    }
