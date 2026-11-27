"""Motor y Tienda de Plugins de Netlis (con iconos dedicados y Escudo Anti-Espionaje Total)."""
from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import shutil
import socket
import struct
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile

from stability import atomic_write_json, safe_load_json
from tor_manager import SOCKS_HOST, SOCKS_PORT, fetch_text_via_socks5


@dataclass(frozen=True)
class PluginDefinition:
    plugin_id: str
    name: str
    category: str
    icon_kind: str
    accent_hex: str
    description: str
    js_code: str
    run_at_start: bool = False
    match_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    version: str = "1.0"


def _glob_to_regex_str(pattern: str) -> str:
    """Convierte un patrón @match/@include de extensión Web/Userscript en expresión regular compatible con Python y JS."""
    pat = pattern.strip()
    if not pat or pat in ("<all_urls>", "*", "*://*/*"):
        return "^https?://.*"
    if pat.startswith("/") and pat.endswith("/") and len(pat) > 2:
        return pat[1:-1]

    m = re.match(r"^(\*|https?|http)://([^/]+)(/.*)?$", pat, re.IGNORECASE)
    if m:
        scheme_p, host_p, path_p = m.group(1).lower(), m.group(2).lower(), m.group(3) or "/*"
        scheme_rx = "https?" if scheme_p == "*" else re.escape(scheme_p)
        if host_p == "*":
            host_rx = r"[^/]+"
        elif host_p.startswith("*."):
            base = re.escape(host_p[2:])
            host_rx = rf"(?:[^/]+\.)?{base}"
        else:
            host_rx = re.escape(host_p).replace(r"\*", r"[^/]*")
        path_rx = re.escape(path_p).replace(r"\*", ".*").replace(r"\?", ".")
        return rf"^{scheme_rx}://{host_rx}{path_rx}$"

    escaped = re.escape(pat).replace(r"\*", ".*").replace(r"\?", ".")
    return rf"^{escaped}$"


def parse_userscript_metadata(js_code: str, fallback_name: str = "Script propio") -> dict:
    """Extrae metadatos estándar ==UserScript== (@name, @description, @version, @match, @include, @exclude, @run-at)."""
    meta = {
        "name": fallback_name,
        "name_es": "",
        "description": "",
        "description_es": "",
        "version": "1.0",
        "matches": [],
        "excludes": [],
        "run_at_start": False,
    }
    block_match = re.search(
        r"//\s*==UserScript==(.*?)//\s*==/UserScript==",
        js_code,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not block_match:
        return {
            "name": fallback_name,
            "description": "",
            "version": "1.0",
            "match_patterns": (),
            "exclude_patterns": (),
            "run_at_start": False,
        }

    for raw_line in block_match.group(1).splitlines():
        line = raw_line.strip()
        m = re.match(r"^//\s*@([\w:-]+)\s+(.+)$", line)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "name":
            meta["name"] = val
        elif key.startswith("name:es"):
            meta["name_es"] = val
        elif key == "description":
            meta["description"] = val
        elif key.startswith("description:es"):
            meta["description_es"] = val
        elif key == "version":
            meta["version"] = val[:16]
        elif key in ("match", "include"):
            meta["matches"].append(val)
        elif key in ("exclude", "exclude-match"):
            meta["excludes"].append(val)
        elif key == "run-at" and val.lower() in ("document-start", "document_start"):
            meta["run_at_start"] = True

    return {
        "name": meta["name_es"] or meta["name"] or fallback_name,
        "description": meta["description_es"] or meta["description"],
        "version": meta["version"],
        "match_patterns": tuple(meta["matches"]),
        "exclude_patterns": tuple(meta["excludes"]),
        "run_at_start": bool(meta["run_at_start"]),
    }


def url_matches_plugin(url_str: str, plug: PluginDefinition) -> bool:
    """Verifica si una URL cumple las reglas @match / @include y @exclude del plugin."""
    for ex in plug.exclude_patterns:
        try:
            if re.search(_glob_to_regex_str(ex), url_str, flags=re.IGNORECASE):
                return False
        except re.error:
            continue
    if not plug.match_patterns:
        return True
    for mp in plug.match_patterns:
        try:
            if re.search(_glob_to_regex_str(mp), url_str, flags=re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


def compile_plugin_source(plug: PluginDefinition) -> str:
    """Envuelve el plugin con control de dominios (@match/@exclude) y APIs GM_* compatibles con Tampermonkey/GreasyFork."""
    if not plug.plugin_id.startswith("custom:") and not plug.match_patterns and not plug.exclude_patterns:
        return plug.js_code

    match_regexes = [_glob_to_regex_str(p) for p in plug.match_patterns]
    exclude_regexes = [_glob_to_regex_str(p) for p in plug.exclude_patterns]
    ns = json.dumps(f"__netlis_gm_{plug.plugin_id}:")
    m_json = json.dumps(match_regexes)
    e_json = json.dumps(exclude_regexes)

    return f"""
    (() => {{
        const __href = String(location.href || '');
        if (!__href.startsWith('http')) return;
        const __excludes = {e_json}.map(r => new RegExp(r, 'i'));
        if (__excludes.some(rx => rx.test(__href))) return;
        const __matches = {m_json}.map(r => new RegExp(r, 'i'));
        if (__matches.length > 0 && !__matches.some(rx => rx.test(__href))) return;

        const __ns = {ns};
        const GM_addStyle = (css) => {{
            const s = document.createElement('style');
            s.textContent = String(css || '');
            (document.head || document.documentElement).appendChild(s);
            return s;
        }};
        const GM_getValue = (k, defVal) => {{
            try {{
                const raw = localStorage.getItem(__ns + k);
                return raw === null ? defVal : JSON.parse(raw);
            }} catch (e) {{ return defVal; }}
        }};
        const GM_setValue = (k, val) => {{
            try {{ localStorage.setItem(__ns + k, JSON.stringify(val)); }} catch (e) {{}}
        }};
        const GM_deleteValue = (k) => {{
            try {{ localStorage.removeItem(__ns + k); }} catch (e) {{}}
        }};
        const GM_registerMenuCommand = () => {{}};
        const GM_info = {{ script: {{ name: {json.dumps(plug.name)}, version: {json.dumps(plug.version)} }} }};

        try {{
            {plug.js_code}
        }} catch (err) {{
            console.warn('[Netlis Extension]', {json.dumps(plug.name)}, err);
        }}
    }})();
    """


BUILTIN_PLUGINS: tuple[PluginDefinition, ...] = (
    PluginDefinition(
        plugin_id="anti-espionaje-total",
        name="Escudo Anti-Espionaje Total",
        category="Anti-Espionaje",
        icon_kind="radar_shield",
        accent_hex="#00ddff",
        description=(
            "Oculta tu zona horaria real (fuerza UTC), destruye WebRTC, camufla pantalla/PC/arquitectura, "
            "bloquea sensores/USB/Bluetooth/voz, corta APIs de geolocalización por IP y activa Kill-Switch Tor."
        ),
        run_at_start=True,
        js_code="""
        (() => {
            if (window.__netlisAntiSpyActive) return;
            window.__netlisAntiSpyActive = true;
            try {
                // 1. Ocultar país/ciudad por Zona Horaria (forzar UTC exacto, offset 0)
                Date.prototype.getTimezoneOffset = function() { return 0; };
                const origDTF = Intl.DateTimeFormat;
                const origResolved = origDTF.prototype.resolvedOptions;
                origDTF.prototype.resolvedOptions = function() {
                    const res = origResolved.call(this);
                    res.timeZone = 'UTC';
                    res.locale = 'en-US';
                    return res;
                };

                // 2. Eliminar WebRTC y enumeración de cámaras/micrófonos (permitido solo en apps de videollamada bajo permiso)
                const _isCallHost = /(^|\\.)(zoom\\.us|meet\\.google\\.com|teams\\.microsoft\\.com|discord\\.com|jit\\.si)$/i.test(location.hostname);
                if (!_isCallHost) {
                    for (const k of ['RTCPeerConnection', 'webkitRTCPeerConnection', 'mozRTCPeerConnection', 'RTCDataChannel']) {
                        try { delete window[k]; Object.defineProperty(window, k, { get: () => undefined }); } catch (e) {}
                    }
                    if (navigator.mediaDevices) {
                        Object.defineProperty(navigator, 'mediaDevices', { get: () => undefined });
                    }
                }

                // 3. Bloquear Geolocalización GPS/Wi-Fi en JS
                if (navigator.geolocation) {
                    const denyGeo = (_ok, err) => { if (typeof err === 'function') err({ code: 1, message: 'Blocked by Netlis' }); };
                    navigator.geolocation.getCurrentPosition = denyGeo;
                    navigator.geolocation.watchPosition = (ok, err) => { denyGeo(ok, err); return 0; };
                }

                // 4. Ocultar resolución real de monitor, escala y detalles del PC (User-Agent Client Hints)
                for (const [prop, val] of [['width', 1920], ['height', 1080], ['availWidth', 1920], ['availHeight', 1080], ['colorDepth', 24], ['pixelDepth', 24]]) {
                    try { Object.defineProperty(Screen.prototype, prop, { get: () => val }); } catch (e) {}
                }
                try { Object.defineProperty(window, 'devicePixelRatio', { get: () => 1 }); } catch (e) {}
                try { Object.defineProperty(navigator, 'platform', { get: () => 'Linux x86_64' }); } catch (e) {}
                if (navigator.userAgentData) {
                    const _isFf = navigator.userAgent.includes('Firefox/');
                    Object.defineProperty(navigator, 'userAgentData', {
                        get: () => _isFf ? undefined : ({
                            brands: [{ brand: 'Chromium', version: '140' }],
                            mobile: false,
                            platform: 'Linux',
                            getHighEntropyValues: async () => ({
                                architecture: 'x86', bitness: '64', model: '', platform: 'Linux', platformVersion: '6.0.0'
                            })
                        })
                    });
                }

                // 5. Cortar acceso a hardware/voz (USB, Bluetooth, HID, Serial) manteniendo compatibilidad con SPAs (YouTube)
                for (const api of ['usb', 'bluetooth', 'hid', 'serial']) {
                    try { Object.defineProperty(navigator, api, { get: () => undefined }); } catch (e) {}
                }
                try {
                    Object.defineProperty(navigator, 'connection', {
                        get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10, saveData: false })
                    });
                } catch (e) {}
                try { navigator.getGamepads = () => []; } catch (e) {}
                if (window.speechSynthesis) {
                    try { window.speechSynthesis.getVoices = () => []; } catch (e) {}
                }

                // 6. Redondeo suave a 1ms (defiende contra timing attacks sin romper carga de comentarios en YouTube)
                if (window.performance && performance.now) {
                    const origNow = performance.now.bind(performance);
                    performance.now = () => Math.round(origNow());
                }

                // 7. Bloquear sondeo de fuentes instaladas por JS y unificar idioma con UTC
                try {
                    Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    if (typeof FontFaceSet !== 'undefined' && FontFaceSet.prototype) {
                        FontFaceSet.prototype.check = () => false;
                    }
                } catch (e) {}
            } catch (e) {}
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="dark-web",
        name="Modo Oscuro Universal",
        category="Apariencia",
        icon_kind="moon",
        accent_hex="#8c7ae6",
        description="Convierte páginas blancas brillantes a modo oscuro suave respetando fotos y videos.",
        js_code="""
        (() => {
            if (location.protocol === 'netlis:' || document.getElementById('__netlis_dark')) return;
            const bg = getComputedStyle(document.body || document.documentElement).backgroundColor;
            if (bg && (bg.includes('255, 255, 255') || bg === 'rgba(0, 0, 0, 0)')) {
                const st = document.createElement('style');
                st.id = '__netlis_dark';
                st.textContent = `
                    html { filter: invert(0.90) hue-rotate(180deg) !important; background: #121216 !important; }
                    img, video, picture, canvas, iframe, svg { filter: invert(1) hue-rotate(180deg) !important; }
                `;
                document.documentElement.appendChild(st);
            }
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="cookie-killer",
        name="Anti-Carteles de Cookies",
        category="Privacidad",
        icon_kind="cookie_block",
        accent_hex="#ff9f43",
        description="Oculta y cierra automáticamente banners molestos de consentimiento de cookies (GDPR).",
        js_code="""
        (() => {
            const st = document.createElement('style');
            st.textContent = `
                #onetrust-consent-sdk, #onetrust-banner-sdk, .cc-window, .cc-banner,
                #CybotCookiebotDialog, .qc-cmp2-container, [id*="cookie-banner"],
                [class*="cookie-banner"], [class*="cookieConsent"] { display: none !important; }
                body, html { overflow: auto !important; }
            `;
            document.documentElement.appendChild(st);
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="unlock-copy",
        name="Desbloquear Copiar y Clic Derecho",
        category="Utilidades",
        icon_kind="unlock",
        accent_hex="#2ecc71",
        description="Reactiva seleccionar texto, copiar y el clic derecho en páginas que lo bloquean.",
        js_code="""
        (() => {
            const st = document.createElement('style');
            st.textContent = `* { user-select: text !important; -webkit-user-select: text !important; }`;
            document.documentElement.appendChild(st);
            for (const ev of ['contextmenu', 'copy', 'cut', 'selectstart']) {
                window.addEventListener(ev, (e) => e.stopPropagation(), true);
            }
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="pip-video",
        name="Video Flotante (Alt+V)",
        category="Multimedia",
        icon_kind="pip",
        accent_hex="#0abde3",
        description="Pulsa Alt+V en cualquier página con video para sacarlo en ventana flotante (PiP).",
        js_code="""
        (() => {
            if (window.__netlisPipBound) return;
            window.__netlisPipBound = true;
            window.addEventListener('keydown', async (e) => {
                if (e.altKey && e.key.toLowerCase() === 'v') {
                    const v = document.querySelector('video');
                    if (!v) return;
                    if (document.pictureInPictureElement) await document.exitPictureInPicture();
                    else await v.requestPictureInPicture();
                }
            });
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="video-speed",
        name="Control Turbo de Video (Alt + / -)",
        category="Multimedia",
        icon_kind="speed",
        accent_hex="#ff6b6b",
        description="Acelera o frena cualquier video web con Alt + '.' (más rápido) y Alt + ',' (normal).",
        js_code="""
        (() => {
            if (window.__netlisSpeedBound) return;
            window.__netlisSpeedBound = true;
            window.addEventListener('keydown', (e) => {
                if (!e.altKey) return;
                const v = document.querySelector('video');
                if (!v) return;
                if (e.key === '.') v.playbackRate = Math.min(4.0, +(v.playbackRate + 0.25).toFixed(2));
                if (e.key === ',') v.playbackRate = 1.0;
            });
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="translate-es",
        name="Traductor Rápido al Español (Alt+T)",
        category="Productividad",
        icon_kind="translate",
        accent_hex="#54a0ff",
        description="Pulsa Alt+T en cualquier página extranjera para abrir su traducción al español.",
        js_code="""
        (() => {
            if (window.__netlisTransBound) return;
            window.__netlisTransBound = true;
            window.addEventListener('keydown', (e) => {
                if (e.altKey && e.key.toLowerCase() === 't' && location.href.startsWith('http')) {
                    location.href = 'https://translate.google.com/translate?sl=auto&tl=es&u=' + encodeURIComponent(location.href);
                }
            });
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="reader-mode",
        name="Modo Lectura Limpia (Alt+R)",
        category="Productividad",
        icon_kind="reader",
        accent_hex="#feca57",
        description="Pulsa Alt+R en artículos o blogs para ocultar barras laterales y leer cómodo.",
        js_code="""
        (() => {
            if (window.__netlisReaderBound) return;
            window.__netlisReaderBound = true;
            window.addEventListener('keydown', (e) => {
                if (e.altKey && e.key.toLowerCase() === 'r') {
                    const art = document.querySelector('article, main') || document.body;
                    document.body.innerHTML = '';
                    document.body.style.cssText = 'max-width:740px;margin:48px auto;padding:24px;background:#191922;color:#ededf5;font:18px/1.75 system-ui,sans-serif;';
                    document.body.appendChild(art);
                }
            });
        })();
        """,
    ),
    PluginDefinition(
        plugin_id="pass-gen",
        name="Generador de Claves Seguras (Alt+P)",
        category="Seguridad",
        icon_kind="key",
        accent_hex="#1dd1a1",
        description="Pulsa Alt+P sobre un campo de contraseña para generar una clave fuerte aleatoria.",
        js_code="""
        (() => {
            if (window.__netlisPassBound) return;
            window.__netlisPassBound = true;
            window.addEventListener('keydown', (e) => {
                if (e.altKey && e.key.toLowerCase() === 'p') {
                    const el = document.activeElement;
                    if (el && el.tagName === 'INPUT') {
                        const chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*';
                        const arr = new Uint32Array(20);
                        crypto.getRandomValues(arr);
                        el.value = Array.from(arr, x => chars[x % chars.length]).join('');
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            });
        })();
        """,
    ),
)


def read_manifest_summary(ext_dir: Path) -> dict[str, str]:
    """Lee manifest.json de una WebExtension y resume versión y permisos declarados."""
    mf = ext_dir / "manifest.json"
    if not mf.is_file():
        return {"name": ext_dir.name, "version": "1.0", "mv": "3", "permissions": "ninguno"}
    try:
        data = json.loads(mf.read_text(encoding="utf-8", errors="ignore"))
        perms = list(data.get("permissions", []) or []) + list(data.get("host_permissions", []) or [])
        perms_str = ", ".join(str(p) for p in perms[:4]) if perms else "sin permisos especiales"
        if len(perms) > 4:
            perms_str += f" (+{len(perms) - 4})"
        return {
            "name": str(data.get("name") or ext_dir.name),
            "version": str(data.get("version") or "1.0"),
            "mv": str(data.get("manifest_version") or "3"),
            "description": str(data.get("description") or ""),
            "permissions": perms_str,
        }
    except (OSError, json.JSONDecodeError):
        return {"name": ext_dir.name, "version": "1.0", "mv": "3", "permissions": "desconocido"}


def _extract_crx_or_zip_bytes(raw: bytes) -> bytes:
    """Si el paquete es Chrome .crx (v2 o v3), salta la cabecera binaria firmada hasta el payload ZIP."""
    if raw.startswith(b"Cr24") and len(raw) >= 16:
        version = struct.unpack("<I", raw[4:8])[0]
        if version == 2:
            pub_len, sig_len = struct.unpack("<II", raw[8:16])
            offset = 16 + pub_len + sig_len
            return raw[offset:]
        if version == 3:
            header_len = struct.unpack("<I", raw[8:12])[0]
            offset = 12 + header_len
            return raw[offset:]
    return raw


def extract_web_extension_package(src_path: Path, target_root: Path) -> tuple[bool, Path | None, str]:
    """Valida e instala una WebExtension desde carpeta manifest.json o paquete .zip / .xpi / .crx."""
    target_root.mkdir(parents=True, exist_ok=True)
    if src_path.is_dir():
        mf = src_path / "manifest.json"
        if not mf.is_file():
            return False, None, "La carpeta seleccionada no contiene manifest.json."
        summary = read_manifest_summary(src_path)
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", summary["name"].lower()).strip("_")[:40] or src_path.name
        dest = target_root / slug
        if dest.resolve() != src_path.resolve():
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(src_path, dest)
        return True, dest, f"WebExtension «{summary['name']}» v{summary['version']} lista."

    if not src_path.is_file():
        return False, None, "Archivo de extensión no encontrado."

    try:
        raw_bytes = src_path.read_bytes()
        zip_bytes = _extract_crx_or_zip_bytes(raw_bytes)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as exc:
        return False, None, f"Paquete de extensión inválido ({exc})."

    tmp_extract = target_root / f".tmp_{src_path.stem}"
    if tmp_extract.exists():
        shutil.rmtree(tmp_extract, ignore_errors=True)
    tmp_extract.mkdir(parents=True, exist_ok=True)

    try:
        for member in zf.infolist():
            rel = Path(member.filename)
            if rel.is_absolute() or ".." in rel.parts:
                shutil.rmtree(tmp_extract, ignore_errors=True)
                return False, None, "Paquete rechazado por ruta insegura (path traversal)."
        zf.extractall(tmp_extract)
    except Exception as exc:
        shutil.rmtree(tmp_extract, ignore_errors=True)
        return False, None, f"Error extrayendo paquete: {exc}"
    finally:
        zf.close()

    ext_root = tmp_extract
    if not (ext_root / "manifest.json").is_file():
        subdirs = [d for d in tmp_extract.iterdir() if d.is_dir() and (d / "manifest.json").is_file()]
        if len(subdirs) == 1:
            ext_root = subdirs[0]
        else:
            shutil.rmtree(tmp_extract, ignore_errors=True)
            return False, None, "El paquete no contiene un manifest.json válido."

    summary = read_manifest_summary(ext_root)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", summary["name"].lower()).strip("_")[:40] or "webext"
    dest = target_root / slug
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    shutil.move(str(ext_root), str(dest))
    shutil.rmtree(tmp_extract, ignore_errors=True)
    return True, dest, f"WebExtension «{summary['name']}» v{summary['version']} instalada."


class PluginManager:
    """Gestiona plugins integrados, Userscripts GM_* y extensiones WebExtension C++."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or (Path(__file__).resolve().parent / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "plugins.json"
        self.custom_dir = self.data_dir / "custom_plugins"
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self.web_ext_dir = self.data_dir / "web_extensions"
        self.web_ext_dir.mkdir(parents=True, exist_ok=True)
        self.state: dict[str, dict[str, bool]] = self._load_state()
        self._purge_removed_web_extensions()

    def _purge_removed_web_extensions(self) -> None:
        changed = False
        for key in list(self.state.keys()):
            if key.startswith("webext:") and self.state[key].get("removed"):
                slug = key.split(":", 1)[1]
                target = (self.web_ext_dir / slug).resolve()
                if target.is_dir() and self.web_ext_dir.resolve() in target.parents:
                    shutil.rmtree(target, ignore_errors=True)
                self.state.pop(key, None)
                changed = True
        if changed:
            self.save()

    def _load_state(self) -> dict[str, dict[str, bool]]:
        defaults = {
            "anti-espionaje-total": {"installed": True, "enabled": True},
            "cookie-killer": {"installed": True, "enabled": True},
            "unlock-copy": {"installed": True, "enabled": True},
        }
        raw = safe_load_json(self.state_path, {})
        if isinstance(raw, dict) and raw:
            if "anti-espionaje-total" not in raw:
                raw["anti-espionaje-total"] = {"installed": True, "enabled": True}
            return raw
        return defaults

    def save(self) -> None:
        atomic_write_json(self.state_path, self.state)

    def list_saved_web_extension_dirs(self) -> list[Path]:
        if not self.web_ext_dir.is_dir():
            return []
        return sorted(
            d for d in self.web_ext_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and (d / "manifest.json").is_file()
            and not self.state.get(f"webext:{d.name}", {}).get("removed", False)
        )

    def import_web_extension(self, src_path: Path) -> tuple[bool, Path | None, str]:
        return extract_web_extension_package(src_path, self.web_ext_dir)

    def all_catalog(self) -> list[PluginDefinition]:
        items = list(BUILTIN_PLUGINS)
        for js_file in sorted(self.custom_dir.glob("*.js")):
            pid = f"custom:{js_file.stem}"
            try:
                code = js_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            fallback = js_file.stem.replace("_", " ").replace("-", " ").title()
            meta = parse_userscript_metadata(code, fallback_name=fallback)
            scope_hint = ""
            if meta["match_patterns"]:
                shown = ", ".join(meta["match_patterns"][:2])
                if len(meta["match_patterns"]) > 2:
                    shown += f" (+{len(meta['match_patterns']) - 2})"
                scope_hint = f" • Sitios: {shown}"
            desc = meta["description"] or f"Userscript instalado ({js_file.name})"
            items.append(
                PluginDefinition(
                    plugin_id=pid,
                    name=meta["name"],
                    category=f"Extensión v{meta['version']}",
                    icon_kind="code",
                    accent_hex="#a29bfe",
                    description=f"{desc}{scope_hint}",
                    js_code=code,
                    run_at_start=meta["run_at_start"],
                    match_patterns=meta["match_patterns"],
                    exclude_patterns=meta["exclude_patterns"],
                    version=meta["version"],
                )
            )
        return items

    def is_installed(self, plugin_id: str) -> bool:
        return bool(self.state.get(plugin_id, {}).get("installed", False))

    def is_enabled(self, plugin_id: str) -> bool:
        st = self.state.get(plugin_id, {})
        return bool(st.get("installed", False) and st.get("enabled", False))

    def install(self, plugin_id: str) -> None:
        self.state[plugin_id] = {"installed": True, "enabled": True}
        self.save()

    def uninstall(self, plugin_id: str) -> None:
        self.state[plugin_id] = {"installed": False, "enabled": False}
        if plugin_id.startswith("custom:"):
            self.state.pop(plugin_id, None)
            stem = plugin_id.split(":", 1)[1]
            (self.custom_dir / f"{stem}.js").unlink(missing_ok=True)
        self.save()

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        if plugin_id in self.state:
            self.state[plugin_id]["enabled"] = enabled
            self.save()

    def import_custom_script(self, src_path: Path) -> str:
        code = src_path.read_text(encoding="utf-8", errors="ignore")
        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", src_path.stem).strip("_") or "userscript"
        if safe_stem.endswith("_user"):
            safe_stem = safe_stem[:-5] or "userscript"
        dest = self.custom_dir / f"{safe_stem}.js"
        dest.write_text(code, encoding="utf-8")
        pid = f"custom:{dest.stem}"
        self.install(pid)
        return pid

    def install_from_url(self, url_str: str, timeout: float = 14.0) -> tuple[bool, str]:
        """Descarga e instala un Userscript (.user.js / .js) desde una URL HTTPS (usando Tor si está activo)."""
        clean_url = url_str.strip()
        parsed = urlparse(clean_url)
        if parsed.scheme.lower() not in ("https", "http") or not parsed.hostname:
            return False, "Introduce una dirección https:// válida hacia un archivo .js o .user.js."

        tor_up = False
        try:
            with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=0.25):
                tor_up = True
        except OSError:
            pass

        try:
            if tor_up:
                code = fetch_text_via_socks5(clean_url, socks_port=SOCKS_PORT, timeout=timeout)
            else:
                req = Request(clean_url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=timeout) as resp:
                    code = resp.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            return False, f"No se pudo descargar el script: {exc}"

        stripped = code.lstrip()
        if not stripped or stripped.lower().startswith("<!doctype html") or stripped.lower().startswith("<html"):
            return False, "El enlace devuelve una página HTML en lugar de un código JavaScript (.js)."

        raw_name = Path(parsed.path).name or "extension"
        raw_stem = re.sub(r"\.user\.js$|\.js$", "", raw_name, flags=re.IGNORECASE)
        meta = parse_userscript_metadata(code, fallback_name=raw_stem or "extension")
        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", meta["name"].lower()).strip("_")[:42] or "extension"
        dest = self.custom_dir / f"{safe_stem}.js"
        dest.write_text(code, encoding="utf-8")
        pid = f"custom:{dest.stem}"
        self.install(pid)
        return True, f"Extensión «{meta['name']}» instalada y activa."

    def active_plugins(self) -> list[PluginDefinition]:
        return [p for p in self.all_catalog() if self.is_enabled(p.plugin_id)]
