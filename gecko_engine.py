"""Lanzador efímero en RAM del motor Firefox Gecko C++ endurecido al nivel Tor Browser."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from newtab import AppearanceSettings, render_new_tab_html
from tor_manager import SOCKS_HOST, SOCKS_PORT


def _resolve_firefox_bin() -> Path:
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            if base:
                cand = Path(base) / "Mozilla Firefox" / "firefox.exe"
                if cand.is_file():
                    return cand
        sys_ff = shutil.which("firefox.exe") or shutil.which("firefox")
        return Path(sys_ff) if sys_ff else Path("firefox.exe")
    local_ff = Path("/usr/lib/firefox/firefox")
    if local_ff.is_file():
        return local_ff
    sys_ff = shutil.which("firefox") or shutil.which("librewolf")
    return Path(sys_ff) if sys_ff else local_ff


FIREFOX_BIN = _resolve_firefox_bin()


def is_gecko_available() -> bool:
    return FIREFOX_BIN.is_file()


def build_gecko_profile(
    use_tor: bool = True,
    safest_no_js: bool = False,
    blocked_count: int = 0,
    https_upgrades: int = 0,
    appearance: AppearanceSettings | None = None,
) -> Path:
    """Crea un perfil efímero en /tmp (RAM tmpfs) con blindaje C++ nativo de Firefox y huella TLS real."""
    prof_dir = Path(tempfile.mkdtemp(prefix="netlis-gecko-"))
    chrome_dir = prof_dir / "chrome"
    chrome_dir.mkdir(parents=True, exist_ok=True)

    # Página de inicio de Netlis guardada en el perfil temporal
    home_file = prof_dir / "netlis_home.html"
    home_file.write_text(
        render_new_tab_html(
            blocked_count=blocked_count,
            https_upgrades=https_upgrades,
            incognito=True,
            appearance=appearance,
        ),
        encoding="utf-8",
    )
    home_uri = home_file.as_uri()

    proxy_type = 1 if use_tor else 0
    js_enabled = "false" if safest_no_js else "true"

    prefs = f"""// Perfil efímero Netlis Gecko C++ (nivel Tor Browser + huella TLS Firefox real)
user_pref("browser.startup.homepage", "{home_uri}");
user_pref("browser.startup.page", 1);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.tabs.warnOnClose", false);
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);

// Blindaje C++ nativo estilo Tor Browser (huella idéntica Firefox RFP + Letterboxing + First-Party Isolation)
user_pref("privacy.resistFingerprinting", true);
user_pref("privacy.resistFingerprinting.letterboxing", true);
user_pref("privacy.firstparty.isolate", true);
user_pref("privacy.trackingprotection.enabled", true);
user_pref("privacy.trackingprotection.socialtracking.enabled", true);
user_pref("privacy.FingerprintingProtection", true);
user_pref("privacy.globalprivacycontrol.enabled", true);
user_pref("dom.security.https_only_mode", true);
user_pref("media.peerconnection.enabled", false);
user_pref("media.navigator.enabled", false);
user_pref("geo.enabled", false);
user_pref("dom.battery.enabled", false);
user_pref("beacon.enabled", false);
user_pref("webgl.disabled", true);

// Blindaje Anti-Exploit C++ SpiderMonkey (sin JIT ni WebAssembly, o modo Sin-JS total)
user_pref("javascript.enabled", {js_enabled});
user_pref("javascript.options.ion", false);
user_pref("javascript.options.baselinejit", false);
user_pref("javascript.options.jit_trustedprincipals", false);
user_pref("javascript.options.wasm", false);

// Enrutamiento 100% por el túnel Tor aislado (IsolateDestAddr + obfs4) de Netlis
user_pref("network.proxy.type", {proxy_type});
user_pref("network.proxy.socks", "{SOCKS_HOST}");
user_pref("network.proxy.socks_port", {SOCKS_PORT});
user_pref("network.proxy.socks_version", 5);
user_pref("network.proxy.socks_remote_dns", true);
user_pref("network.dns.disablePrefetch", true);
user_pref("network.predictor.enabled", false);
user_pref("network.prefetch-next", false);

// Cero telemetría y borrado total
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("extensions.pocket.enabled", false);
user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
user_pref("places.history.enabled", false);
user_pref("network.cookie.cookieBehavior", 1);
user_pref("network.cookie.lifetimePolicy", 2);
"""
    (prof_dir / "user.js").write_text(prefs, encoding="utf-8")

    # Estética oscura redondeada estilo Netlis en Firefox
    user_chrome = """
    :root {
        --toolbar-bgcolor: #22212c !important;
        --lwt-accent-color: #16151e !important;
        --tab-border-radius: 10px !important;
    }
    #urlbar-background { border-radius: 12px !important; background-color: #16151e !important; }
    """
    (chrome_dir / "userChrome.css").write_text(user_chrome, encoding="utf-8")
    return prof_dir


def launch_gecko_session(
    use_tor: bool = True,
    safest_no_js: bool = False,
    blocked_count: int = 0,
    https_upgrades: int = 0,
    appearance: AppearanceSettings | None = None,
) -> bool:
    """Lanza Firefox Gecko C++ en un perfil efímero en RAM y lo destruye automáticamente al cerrarse."""
    if not is_gecko_available():
        return False

    prof_dir = build_gecko_profile(
        use_tor=use_tor,
        safest_no_js=safest_no_js,
        blocked_count=blocked_count,
        https_upgrades=https_upgrades,
        appearance=appearance,
    )

    def _runner() -> None:
        try:
            proc = subprocess.Popen(
                [str(FIREFOX_BIN), "--no-remote", "--profile", str(prof_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            proc.wait()
        finally:
            shutil.rmtree(prof_dir, ignore_errors=True)

    threading.Thread(target=_runner, daemon=True).start()
    return True
