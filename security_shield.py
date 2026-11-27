"""Escudo de Seguridad 100% local de Netlis: Anti-Phishing, Anti-Homógrafos y Guardia Profunda de Descargas (Magic Bytes + SHA-256)."""
from __future__ import annotations

import hashlib
import html
from pathlib import Path
import re
from urllib.parse import urlparse

DANGEROUS_EXTENSIONS: frozenset[str] = frozenset({
    ".exe", ".msi", ".msp", ".bat", ".cmd", ".scr", ".pif", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".wsh", ".ps1", ".psm1", ".apk", ".jar", ".sh", ".run", ".bin", ".elf", ".appimage",
    ".deb", ".rpm", ".pkg", ".dll", ".hta", ".iso", ".img", ".cpl", ".reg", ".lnk", ".desktop",
})

DANGEROUS_MIME_TYPES: frozenset[str] = frozenset({
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/x-dosexec",
    "application/x-executable",
    "application/x-elf",
    "application/x-sh",
    "application/x-shellscript",
    "application/vnd.microsoft.portable-executable",
    "application/vnd.android.package-archive",
    "application/hta",
})

SAFE_DOCUMENT_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".txt", ".csv", ".md", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg",
    ".mp3", ".mp4", ".webm", ".wav", ".ogg", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
})

UNICODE_SPOOF_CHARS: frozenset[str] = frozenset({
    "\u202e",  # Right-To-Left Override (invierte visualmente "gpj.exe" -> "exe.jpg")
    "\u202d",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u200e",
    "\u200f",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
})

KNOWN_MALICIOUS_DOMAINS: frozenset[str] = frozenset({
    "malware.testing.google.test",
    "testsafebrowsing.appspot.com",
    "amtso.org",
    "eicar.org",
})

DYNAMIC_THREAT_DOMAINS: set[str] = set()


def reload_threat_domains(path: Path | None = None) -> int:
    """Carga en memoria O(1) la lista local actualizada de dominios de malware/phishing."""
    target = path or (Path(__file__).resolve().parent / "data" / "threat_domains.txt")
    if not target.is_file():
        return len(DYNAMIC_THREAT_DOMAINS)
    try:
        loaded = {
            ln.strip().lower()
            for ln in target.read_text(encoding="utf-8", errors="ignore").splitlines()
            if ln.strip() and not ln.startswith("#")
        }
        DYNAMIC_THREAT_DOMAINS.clear()
        DYNAMIC_THREAT_DOMAINS.update(loaded)
    except OSError:
        pass
    return len(DYNAMIC_THREAT_DOMAINS)


reload_threat_domains()

PROTECTED_BRANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("google", ("google.com", "google.es", "googleapis.com", "gstatic.com", "youtube.com")),
    ("paypal", ("paypal.com", "paypalobjects.com")),
    ("whatsapp", ("whatsapp.com", "whatsapp.net")),
    ("microsoft", ("microsoft.com", "live.com", "office.com", "outlook.com")),
    ("apple", ("apple.com", "icloud.com")),
    ("github", ("github.com", "githubusercontent.com")),
    ("binance", ("binance.com",)),
    ("steam", ("steampowered.com", "steamcommunity.com")),
)

SUSPICIOUS_TLDS: frozenset[str] = frozenset({
    ".zip", ".mov", ".top", ".xyz", ".click", ".gq", ".tk", ".ml", ".cf", ".ga", ".work",
})

IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def analyze_url_threat(url_str: str) -> tuple[bool, str]:
    """Analiza localmente si una URL presenta técnicas de phishing, homógrafos o trampa de credenciales."""
    if not url_str or url_str.startswith(("netlis://", "about:", "data:")):
        return False, ""

    parsed = urlparse(url_str)
    host = (parsed.hostname or "").lower().strip(".")
    if not host or host in ("127.0.0.1", "localhost", "::1"):
        return False, ""

    if parsed.username or "@" in parsed.netloc:
        return True, "URL engañosa con '@' para ocultar el dominio real de destino."

    if host in DYNAMIC_THREAT_DOMAINS or any(
        host == d or host.endswith("." + d) for d in KNOWN_MALICIOUS_DOMAINS
    ):
        return True, f"Dominio reportado por distribución de malware/phishing ({host})."

    if "xn--" in host:
        return True, f"Posible ataque homógrafo IDN/Punycode detectado en '{host}'."

    if any(ord(ch) > 127 for ch in host):
        scripts = {
            "latin" if "a" <= ch <= "z" else ("other" if ord(ch) > 127 else "num")
            for ch in host
            if ch.isalpha() or ord(ch) > 127
        }
        if "latin" in scripts and "other" in scripts:
            return True, f"Mezcla sospechosa de alfabetos para suplantar identidad en '{host}'."

    path_l = (parsed.path or "").lower()
    if IPV4_RE.match(host) and any(k in path_l for k in ("login", "signin", "verify", "bank", "secure", "account")):
        return True, f"Intento de inicio de sesión sobre dirección IP directa ({host})."

    normalized_host = host.replace("0", "o").replace("1", "l")
    for brand, legit_domains in PROTECTED_BRANDS:
        if brand in normalized_host and not any(
            host == ld or host.endswith("." + ld) for ld in legit_domains
        ):
            if any(host.endswith(tld) for tld in SUSPICIOUS_TLDS) or any(
                w in host for w in ("login", "verify", "secure", "update", "account", "auth", "-")
            ):
                return True, f"Posible suplantación de identidad (phishing) imitando a {brand.capitalize()} ({host})."

    return False, ""


def is_dangerous_download(filename: str) -> bool:
    """Detecta extensiones ejecutables, caracteres Unicode RLO o doble extensión engañosa."""
    blocked, _ = inspect_download_request(filename, "", "")
    return blocked


def inspect_download_request(filename: str, source_url: str = "", mime_type: str = "") -> tuple[bool, str]:
    """Inspección profunda previa a la descarga: Unicode RLO, doble extensión, MIME ejecutable y reputación de origen."""
    raw_name = filename.strip()
    if not raw_name:
        return False, ""

    # 1. Ataque de inversión direccional Unicode (RLO spoofing)
    if any(ch in raw_name for ch in UNICODE_SPOOF_CHARS):
        return True, "Nombre de archivo con camuflaje Unicode bidireccional (RLO)"

    # 2. Reputación del servidor de origen de la descarga
    if source_url:
        url_bad, url_reason = analyze_url_threat(source_url)
        if url_bad:
            return True, f"Origen malicioso ({url_reason})"

    # 3. Extensión final o doble extensión (ej. factura.pdf.exe o documento.docx.scr)
    clean_name = raw_name.rstrip(". ")
    suffixes = [s.lower() for s in Path(clean_name).suffixes]
    if suffixes and suffixes[-1] in DANGEROUS_EXTENSIONS:
        if len(suffixes) >= 2 and suffixes[-2] in SAFE_DOCUMENT_EXTENSIONS:
            return True, f"Doble extensión engañosa ({suffixes[-2]}{suffixes[-1]})"
        return True, f"Ejecutable bloqueado ({suffixes[-1]})"

    # 4. Tipo MIME ejecutable aunque la extensión parezca inocente
    mime_clean = mime_type.split(";", 1)[0].strip().lower()
    if mime_clean in DANGEROUS_MIME_TYPES:
        return True, f"MIME ejecutable camuflado ({mime_clean})"

    return False, ""


def verify_downloaded_file_safety(file_path: Path) -> tuple[bool, str, str]:
    """Verifica post-descarga los magic bytes reales del archivo y calcula su huella criptográfica SHA-256.
    Devuelve (es_seguro, sha256_hex, motivo_si_bloqueado).
    """
    if not file_path.is_file():
        return False, "", "Archivo no encontrado"

    h = hashlib.sha256()
    head = b""
    try:
        with open(file_path, "rb") as fh:
            first = True
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                if first:
                    head = chunk[:64]
                    first = False
                h.update(chunk)
    except OSError as exc:
        return False, "", f"Error leyendo archivo: {exc}"

    digest = h.hexdigest()
    ext = file_path.suffix.lower()

    # Firma EICAR estándar de prueba antivirus
    if head.startswith(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"):
        file_path.unlink(missing_ok=True)
        return False, digest, "Firma de prueba malware EICAR detectada y eliminada"

    # Si el archivo dice ser un documento/imagen/multimedia seguro pero su binario real es ejecutable -> CUARENTENA
    if ext in SAFE_DOCUMENT_EXTENSIONS or ext == "":
        disguised_kind = ""
        if head.startswith(b"\x7fELF"):
            disguised_kind = "binario ejecutable Linux ELF"
        elif head.startswith(b"MZ"):
            disguised_kind = "ejecutable Windows PE/MZ"
        elif head.startswith((b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe")):
            disguised_kind = "binario ejecutable Mach-O"
        elif head.startswith(b"#!") and ext != ".svg":
            disguised_kind = "script ejecutable (#!)"

        if disguised_kind:
            file_path.unlink(missing_ok=True)
            return False, digest, f"Malware camuflado eliminado ({disguised_kind} disfrazado de {ext or 'archivo'})"

    return True, digest, ""


def render_threat_warning_html(blocked_url: str, reason: str) -> str:
    """Genera una pantalla de bloqueo estilo cristal cuando se intercepta phishing o malware."""
    safe_url = html.escape(blocked_url[:140])
    safe_reason = html.escape(reason)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Sitio bloqueado — Netlis Shield</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, sans-serif; }}
  body {{
    min-height: 100vh;
    background: radial-gradient(circle at 50% 25%, #3d1822 0%, #1a1520 60%, #121118 100%);
    color: #f6f6fb;
    display: flex; align-items: center; justify-content: center; padding: 28px;
  }}
  .glass-box {{
    max-width: 620px; width: 100%;
    background: rgba(255, 255, 255, 0.07);
    backdrop-filter: blur(22px);
    border: 1px solid rgba(255, 110, 125, 0.45);
    border-radius: 22px;
    padding: 34px 32px;
    box-shadow: 0 18px 48px rgba(0, 0, 0, 0.5);
  }}
  .tag {{
    display: inline-block; background: rgba(255, 69, 58, 0.25);
    border: 1px solid rgba(255, 115, 110, 0.6);
    color: #ff9490; font-size: 12px; font-weight: 700;
    padding: 5px 13px; border-radius: 12px; margin-bottom: 16px;
  }}
  h1 {{ font-size: 25px; font-weight: 800; margin-bottom: 10px; }}
  p {{ font-size: 14px; line-height: 1.55; color: #d6d5e2; margin-bottom: 14px; }}
  .url-pill {{
    background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px; padding: 10px 14px; font-family: monospace;
    font-size: 12px; color: #ffb3b0; word-break: break-all; margin-bottom: 22px;
  }}
  .btn {{
    display: inline-block; text-decoration: none;
    background: linear-gradient(180deg, #0a84ff, #0066cc);
    color: #ffffff; font-weight: 600; font-size: 14px;
    padding: 10px 22px; border-radius: 12px;
    border: 1px solid rgba(165, 220, 255, 0.55);
  }}
</style>
</head>
<body>
  <div class="glass-box">
    <div class="tag">AMENAZA BLOQUEADA POR NETLIS</div>
    <h1>Conexión detenida por tu seguridad</h1>
    <p><b>Motivo detectado:</b> {safe_reason}</p>
    <p>Netlis bloqueó esta dirección localmente antes de enviar ningún dato ni conectar con el servidor.</p>
    <div class="url-pill">{safe_url}</div>
    <a class="btn" href="netlis://newtab">Volver a lugar seguro</a>
  </div>
</body>
</html>"""
