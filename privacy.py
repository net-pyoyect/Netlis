"""Motor de privacidad y seguridad Netlis: bloqueo de rastreadores, anuncios YouTube, limpieza de URLs, DoH y Proxy/Tor."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import random
import socket
import time
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor

from stability import atomic_write_json, safe_load_json

DOH_PROVIDERS: dict[str, tuple[str, str]] = {
    "cloudflare": ("Cloudflare (1.1.1.1)", "https://cloudflare-dns.com/dns-query"),
    "quad9": ("Quad9 (Seguridad)", "https://dns.quad9.net/dns-query"),
    "adguard": ("AdGuard (Sin anuncios)", "https://dns.adguard-dns.com/dns-query"),
}

IP_REGIONS: dict[str, str] = {
    "auto": "Aleatorio mundial (Rotación automática)",
    "us": "Estados Unidos",
    "de": "Alemania",
    "nl": "Países Bajos",
    "ch": "Suiza",
    "jp": "Japón",
    "ca": "Canadá",
    "gb": "Reino Unido",
    "sg": "Singapur",
}

TRACKER_DOMAINS: tuple[str, ...] = (
    "doubleclick.net",
    "googlesyndication.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googleadservices.com",
    "adservice.google.com",
    "pagead2.googlesyndication.com",
    "tpc.googlesyndication.com",
    "s0.2mdn.net",
    "connect.facebook.net",
    "pixel.facebook.com",
    "facebook.net",
    "an.facebook.com",
    "scorecardresearch.com",
    "quantserve.com",
    "hotjar.com",
    "mixpanel.com",
    "segment.io",
    "segment.com",
    "taboola.com",
    "outbrain.com",
    "criteo.com",
    "adnxs.com",
    "pubmatic.com",
    "rubiconproject.com",
    "openx.net",
    "casalemedia.com",
    "advertising.com",
    "amazon-adsystem.com",
    "chartbeat.com",
    "clarity.ms",
    "amplitude.com",
    "sentry.io",
    "newrelic.com",
    "tiktokv.com",
    "analytics.tiktok.com",
    "ads-twitter.com",
    "analytics.twitter.com",
    "bat.bing.com",
    "mc.yandex.ru",
    "moatads.com",
    "demdex.net",
    "omtrdc.net",
    "krxd.net",
    "bluekai.com",
    "adsrvr.org",
    "innovid.com",
    "doubleverify.com",
)

TRACKER_PREFIXES: tuple[str, ...] = (
    "ads.",
    "ad.",
    "adserver.",
    "analytics.",
    "telemetry.",
    "pixel.",
    "tracking.",
    "metrics.",
    "beacon.",
    "stats.",
)

GEOIP_SPY_DOMAINS: tuple[str, ...] = (
    "ipapi.co",
    "ip-api.com",
    "geoip-db.com",
    "freegeoip.app",
    "ipwhois.app",
    "extreme-ip-lookup.com",
    "ipgeolocation.io",
    "maxmind.com",
    "ipdata.co",
    "ipregistry.co",
    "geolocation-db.com",
    "db-ip.com",
    "ipstack.com",
    "whatismyipaddress.com",
)

YOUTUBE_AD_PATHS: tuple[str, ...] = (
    "/api/stats/ads",
    "/api/stats/atr",
    "/pagead/",
    "/ptracking",
    "/get_midroll_info",
    "/youtubei/v1/player/ad_break",
)

TRACKING_QUERY_PARAMS: frozenset[str] = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "dclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "si",
    "yclid",
    "_hsenc",
    "_hsmi",
})


@dataclass
class PrivacySettings:
    block_trackers: bool = True
    block_youtube_ads: bool = True
    strip_tracking_params: bool = True
    https_only: bool = True
    doh_enabled: bool = True
    doh_provider: str = "adguard"
    block_third_party_cookies: bool = True
    anti_fingerprinting: bool = True
    exploit_shield_jitless: bool = False
    strict_site_isolation: bool = True
    isolated_tab_containers: bool = False
    safest_no_js: bool = False
    phishing_and_malware_guard: bool = True
    clear_on_exit: bool = True
    proxy_enabled: bool = True
    tor_bridges_obfs4: bool = False
    proxy_url: str = "socks5://127.0.0.1:19050"
    ip_region: str = "auto"

    @classmethod
    def load(cls, path: Path) -> "PrivacySettings":
        raw = safe_load_json(path, {})
        if not isinstance(raw, dict) or not raw:
            return cls()
        try:
            valid = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            return cls(**valid)
        except TypeError:
            return cls()

    def save(self, path: Path) -> None:
        atomic_write_json(path, asdict(self))


def is_proxy_reachable(proxy_url: str, timeout: float = 0.25) -> bool:
    """Comprueba si un proxy local (ej. Tor en 127.0.0.1:9050) está escuchando."""
    try:
        parsed = urlparse(proxy_url if "://" in proxy_url else f"socks5://{proxy_url}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9050
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pick_random_region() -> tuple[str, str]:
    """Elige aleatoriamente una región mundial distinta de 'auto'."""
    choices = [(k, v) for k, v in IP_REGIONS.items() if k != "auto"]
    return random.choice(choices)


def rotate_tor_identity(control_port: int = 19051, region_code: str = "") -> tuple[bool, str]:
    """Cambia de región (opcional) y solicita nueva IP aleatoria al ControlPort de Tor integrado."""
    try:
        cmds = ['AUTHENTICATE ""']
        if region_code == "auto":
            cmds.append("RESETCONF ExitNodes StrictNodes")
        elif region_code:
            cmds.append(f'SETCONF ExitNodes="{{{region_code}}}" StrictNodes=1')
        cmds.append("SIGNAL NEWNYM")
        cmds.append("QUIT")
        payload = ("\r\n".join(cmds) + "\r\n").encode("utf-8")
        with socket.create_connection(("127.0.0.1", control_port), timeout=1.5) as sock:
            sock.sendall(payload)
            resp = sock.recv(512).decode("utf-8", errors="ignore")
            if "250 OK" in resp:
                return True, "Circuito Tor renovado con nueva IP de salida."
            return False, f"Tor respondió: {resp.strip()}"
    except OSError:
        return False, "Túnel Tor iniciándose o apagado."


TRACKER_DOMAINS_SET: frozenset[str] = frozenset(TRACKER_DOMAINS)
GEOIP_SPY_DOMAINS_SET: frozenset[str] = frozenset(GEOIP_SPY_DOMAINS)


def _host_in_domain_set(host: str, domain_set: frozenset[str]) -> bool:
    if host in domain_set:
        return True
    idx = host.find(".")
    while idx != -1:
        sub = host[idx + 1 :]
        if sub in domain_set:
            return True
        idx = host.find(".", idx + 1)
    return False


def is_tracker_host(host: str) -> bool:
    h = host.lower().strip(".")
    if not h:
        return False
    if _host_in_domain_set(h, TRACKER_DOMAINS_SET):
        return True
    return any(h.startswith(prefix) for prefix in TRACKER_PREFIXES)


def is_youtube_ad_request(host: str, path: str, query: str) -> bool:
    h = host.lower()
    if "youtube.com" in h or "youtu.be" in h:
        if any(p in path for p in YOUTUBE_AD_PATHS):
            return True
    # No bloquear ctier=L (YouTube lo usa en streams normales); solo parámetros exclusivos de anuncios
    if "googlevideo.com" in h and ("&oad=" in query or "adformat=" in query):
        return True
    return False


def strip_tracking_from_url(url_str: str) -> str:
    """Elimina parámetros de rastreo (utm_*, fbclid, gclid, etc.) de una URL."""
    parsed = urlparse(url_str)
    if not parsed.query:
        return url_str
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    cleaned = [(k, v) for k, v in pairs if k.lower() not in TRACKING_QUERY_PARAMS]
    if len(cleaned) == len(pairs):
        return url_str
    return urlunparse(parsed._replace(query=urlencode(cleaned, doseq=True)))


def build_chromium_flags(settings: PrivacySettings) -> list[str]:
    """Construye banderas de alto rendimiento, compatibilidad GPU/Wasm y aislamiento estricto de sitios."""
    js_opts = ["--max-old-space-size=512"]
    if settings.exploit_shield_jitless:
        js_opts.insert(0, "--jitless")

    enabled_features: list[str] = [
        "ThirdPartyStoragePartitioning",
        "SplitCacheByNetworkIsolationKey",
        "BlockInsecurePrivateNetworkRequests",
    ]
    flags: list[str] = [
        f"--js-flags={','.join(js_opts)}",
    ]

    if settings.strict_site_isolation:
        # Sin --renderer-process-limit para garantizar un proceso OS aislado por cada dominio/origen
        flags.append("--site-per-process")
        enabled_features.insert(0, "StrictOriginIsolation")

    if settings.anti_fingerprinting:
        flags.append("--force-webrtc-ip-handling-policy=disable_non_proxied_udp")

    if settings.doh_enabled:
        _, doh_url = DOH_PROVIDERS.get(settings.doh_provider, DOH_PROVIDERS["adguard"])
        enabled_features.append("DnsOverHttps")
        flags.append(f"--dns-over-https-templates={doh_url}")

    flags.append(f"--enable-features={','.join(enabled_features)}")

    if settings.proxy_enabled and settings.proxy_url.strip():
        flags.append(f"--proxy-server={settings.proxy_url.strip()}")
    else:
        flags.append("--enable-quic")
    return flags


class TrackerInterceptor(QWebEngineUrlRequestInterceptor):
    """Intercepta peticiones para bloquear anuncios/rastreadores, limpiar URLs y forzar HTTPS."""

    def __init__(
        self,
        settings: PrivacySettings,
        on_blocked: Callable[[], None] | None = None,
        anti_spy_enabled: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.on_blocked = on_blocked
        self.anti_spy_enabled = anti_spy_enabled
        self.blocked_count = 0
        self.https_upgrades = 0
        self.per_site_blocked: dict[str, dict[str, int]] = {}
        self.per_site_totals: dict[str, int] = {}
        self._proxy_ok_cached = False
        self._proxy_check_ts = 0.0

    def _is_tor_ready_cached(self) -> bool:
        now = time.monotonic()
        # TTL de 1.5s para evitar cientos de sockets TCP síncronos por página al cargar recursos
        if now - self._proxy_check_ts > 1.5:
            self._proxy_ok_cached = is_proxy_reachable(self.settings.proxy_url, timeout=0.05)
            self._proxy_check_ts = now
        return self._proxy_ok_cached

    @staticmethod
    def _norm_site(host: str) -> str:
        h = (host or "").lower().strip(".")
        return h[4:] if h.startswith("www.") else h

    def _mark_blocked(self, site_host: str = "", target_label: str = "") -> None:
        self.blocked_count += 1
        s_key = self._norm_site(site_host)
        if s_key:
            self.per_site_totals[s_key] = self.per_site_totals.get(s_key, 0) + 1
            if target_label:
                bucket = self.per_site_blocked.setdefault(s_key, {})
                bucket[target_label] = bucket.get(target_label, 0) + 1
        if self.on_blocked is not None:
            self.on_blocked()

    def site_report(self, site_host: str) -> tuple[int, list[tuple[str, int]]]:
        """Devuelve (total_bloqueados_en_sitio, lista_ordenada_de_anuncios_y_rastreadores)."""
        s_key = self._norm_site(site_host)
        if not s_key:
            return 0, []
        total = self.per_site_totals.get(s_key, 0)
        items = sorted(
            self.per_site_blocked.get(s_key, {}).items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
        return total, items

    def reset_stats(self) -> None:
        self.per_site_blocked.clear()
        self.per_site_totals.clear()

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url = info.requestUrl()
        scheme = url.scheme().lower()
        host = url.host().lower()
        path = url.path().lower()
        query = url.query().lower()
        first_party = info.firstPartyUrl().host().lower()
        site_ctx = first_party or host

        spy_guard_on = self.anti_spy_enabled() if self.anti_spy_enabled is not None else False

        # Kill-Switch estricto Anti-Espionaje: si Modo Tor está activo pero el túnel aún no levanta,
        # no permitir que salga NI UN SOLO PAQUETE con tu IP real hacia internet.
        if (
            spy_guard_on
            and self.settings.proxy_enabled
            and scheme in ("http", "https", "ws", "wss")
            and host not in ("127.0.0.1", "localhost", "::1")
            and not self._is_tor_ready_cached()
        ):
            info.block(True)
            self._mark_blocked(site_ctx, f"Kill-Switch Tor ({host})")
            return

        # Bloquear servicios web espía de geolocalización por IP incrustados en páginas (lookup O(1))
        if spy_guard_on and _host_in_domain_set(host, GEOIP_SPY_DOMAINS_SET):
            info.block(True)
            self._mark_blocked(site_ctx, f"{host} (GeoIP)")
            return

        if self.settings.block_trackers and is_tracker_host(host):
            info.block(True)
            self._mark_blocked(site_ctx, host)
            return

        if self.settings.block_youtube_ads and is_youtube_ad_request(host, path, query):
            info.block(True)
            self._mark_blocked(site_ctx, f"{host} (Anuncio YouTube)")
            return

        if self.settings.strip_tracking_params and url.hasQuery():
            cleaned = strip_tracking_from_url(url.toString())
            if cleaned != url.toString():
                info.redirect(QUrl(cleaned))
                return

        if (
            self.settings.https_only
            and url.scheme() == "http"
            and host not in ("localhost", "127.0.0.1", "::1")
        ):
            upgraded = QUrl(url)
            upgraded.setScheme("https")
            info.redirect(upgraded)
            self.https_upgrades += 1

        if self.settings.anti_fingerprinting:
            info.setHttpHeader(b"DNT", b"1")
            info.setHttpHeader(b"Sec-GPC", b"1")
            if first_party and host and first_party != host:
                # Política strict-origin-when-cross-origin: envía solo el origen sin ruta (evita 403 en APIs como YouTube)
                fp_scheme = info.firstPartyUrl().scheme() or "https"
                info.setHttpHeader(b"Referer", f"{fp_scheme}://{first_party}/".encode("ascii", errors="ignore"))
