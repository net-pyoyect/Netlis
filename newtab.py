"""Página de Nueva Pestaña personalizable para Netlis (incluyendo modo visual Antigravity y wallpaper)."""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import html
import json
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_WALLPAPER = PROJECT_ROOT / "assets" / "netlis_wallpaper.png"

BACKGROUND_PRESETS: dict[str, tuple[str, str]] = {
    "netlis": ("Oscuro Minimal (LibreWolf)", "#131215"),
    "antigravity": (
        "Nébula Glass",
        "radial-gradient(circle at 20% 20%, rgba(124, 92, 255, 0.34) 0%, transparent 46%), "
        "radial-gradient(circle at 82% 78%, rgba(56, 189, 248, 0.28) 0%, transparent 50%), "
        "linear-gradient(135deg, #090b16 0%, #14122b 52%, #0c1729 100%)",
    ),
    "oceano": ("Océano Profundo", "linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)"),
    "aurora": ("Aurora Boreal", "linear-gradient(135deg, #121b28 0%, #1b3b44 45%, #2a1b3d 100%)"),
    "atardecer": ("Atardecer Neón", "linear-gradient(135deg, #1f1428 0%, #3d1d34 55%, #161822 100%)"),
    "minimal": ("Negro Puro", "#131215"),
}

SEARCH_ENGINES: dict[str, tuple[str, str]] = {
    "duckduckgo": ("DuckDuckGo (Privado + Logo Netlis)", "https://duckduckgo.com/?q="),
    "google": ("Google", "https://www.google.com/search?q="),
    "bing": ("Bing", "https://www.bing.com/search?q="),
    "brave": ("Brave Search", "https://search.brave.com/search?q="),
    "startpage": ("Startpage (Google sin rastreo)", "https://www.startpage.com/sp/search?query="),
    "wikipedia": ("Wikipedia (es)", "https://es.wikipedia.org/w/index.php?search="),
    "netlis": ("Netlis Search (Propio con tu logo)", "netlis://search?q="),
}

DEFAULT_SITES: list[dict[str, str]] = [
    {"title": "WhatsApp", "url": "https://web.whatsapp.com", "color": "#25D366"},
    {"title": "YouTube", "url": "https://www.youtube.com", "color": "#FF0000"},
    {"title": "ChatGPT", "url": "https://chatgpt.com", "color": "#10A37F"},
    {"title": "Wikipedia", "url": "https://es.wikipedia.org", "color": "#E6E8EE"},
    {"title": "GitHub", "url": "https://github.com", "color": "#F0F6FC"},
    {"title": "Google", "url": "https://www.google.com", "color": "#4285F4"},
    {"title": "Gmail", "url": "https://mail.google.com", "color": "#EA4335"},
    {"title": "Spotify", "url": "https://open.spotify.com", "color": "#1DB954"},
]


def normalize_wallpaper_path(raw_path: str) -> str:
    """Convierte rutas dentro de assets/ en ruta relativa robusta al proyecto; mantiene rutas externas."""
    clean = (raw_path or "").strip()
    if not clean:
        return ""
    p = Path(clean)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    else:
        p = p.resolve()
    assets_dir = (PROJECT_ROOT / "assets").resolve()
    try:
        rel = p.relative_to(PROJECT_ROOT)
        if assets_dir in p.parents or p.parent == assets_dir:
            return rel.as_posix()
    except ValueError:
        pass
    return str(p)


def resolve_wallpaper_path(stored_path: str) -> Path | None:
    """Resuelve una ruta de wallpaper (relativa al proyecto o absoluta)."""
    clean = (stored_path or "").strip()
    if not clean:
        return None
    p = Path(clean)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


@dataclass
class AppearanceSettings:
    preset: str = "netlis"
    chrome_theme: str = "default"
    show_home_logo: bool = True
    show_home_search: bool = True
    show_search_terms: bool = True
    image_path: str = "assets/netlis_wallpaper.png" if DEFAULT_WALLPAPER.is_file() else ""
    opacity_percent: int = 96
    search_engine: str = "duckduckgo"

    @classmethod
    def load(cls, path: Path) -> "AppearanceSettings":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return cls()
            valid = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
            if "search_engine" not in valid or valid["search_engine"] not in SEARCH_ENGINES:
                valid["search_engine"] = "duckduckgo"
            if "preset" not in valid or valid["preset"] not in BACKGROUND_PRESETS:
                valid["preset"] = "netlis"
            return cls(**valid)
        except (OSError, json.JSONDecodeError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["image_path"] = normalize_wallpaper_path(self.image_path)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def _image_data_uri(image_path: str) -> str:
    p = resolve_wallpaper_path(image_path)
    if p is None or not p.is_file():
        return ""
    try:
        raw = p.read_bytes()
        if not raw or len(raw) > 8 * 1024 * 1024:
            return ""
        ext = p.suffix.lower().lstrip(".") or "png"
        if ext not in ("png", "jpg", "jpeg", "webp"):
            return ""
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:image/{mime};base64,{b64}"
    except OSError:
        return ""


def _domain_of(url: str) -> str:
    return urlparse(url).netloc or "duckduckgo.com"


def render_new_tab_html(
    blocked_count: int,
    https_upgrades: int = 0,
    incognito: bool = False,
    bookmarks: list[dict[str, str]] | None = None,
    appearance: AppearanceSettings | None = None,
) -> str:
    """Genera la Nueva Pestaña minimalista o Antigravity Glass con soporte completo de wallpaper."""
    app_cfg = appearance or AppearanceSettings()
    is_ag = (not incognito) and (app_cfg.preset == "antigravity")

    if incognito:
        bg_css = "background-color: #1b1526; background-image: radial-gradient(circle at 50% 25%, #2c1e45 0%, #1b1526 70%);"
    else:
        img_uri = _image_data_uri(app_cfg.image_path)
        if img_uri:
            overlay = (
                "linear-gradient(rgba(10,12,26,0.52), rgba(16,14,34,0.68))"
                if is_ag
                else "linear-gradient(rgba(16,16,22,0.46), rgba(16,16,22,0.62))"
            )
            bg_css = (
                f"background-color: #131215; "
                f"background-image: {overlay}, url('{img_uri}'); "
                "background-position: center center; "
                "background-size: cover; "
                "background-repeat: no-repeat; "
                "background-attachment: fixed;"
            )
        else:
            _, bg_val = BACKGROUND_PRESETS.get(app_cfg.preset, BACKGROUND_PRESETS["netlis"])
            bg_css = f"background-color: #131215; background: {bg_val};"

    title_text = "Netlis Privado" if incognito else "Netlis"

    logo_file = PROJECT_ROOT / "assets" / "netlis_logo_transparent.png"
    if not logo_file.is_file():
        logo_file = PROJECT_ROOT / "assets" / "netlis_logo.jpg"
    logo_uri = _image_data_uri(str(logo_file))
    if logo_uri:
        logo_html = (
            f'<img src="{logo_uri}" alt="Netlis" '
            'style="width:54px;height:54px;object-fit:contain;'
            'filter:drop-shadow(0 4px 14px rgba(0,0,0,0.55));">'
        )
        small_logo_html = (
            f'<img src="{logo_uri}" alt="" '
            'style="width:22px;height:22px;object-fit:contain;flex-shrink:0;">'
        )
    else:
        logo_html = '<div class="logo-ring">N</div>'
        small_logo_html = (
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#9b9aa8" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0">'
            '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
        )

    if is_ag:
        search_box_css = """
            background: rgba(18, 22, 44, 0.64);
            backdrop-filter: blur(22px);
            border: 1px solid rgba(143, 122, 230, 0.42);
            box-shadow: 0 10px 32px rgba(8, 10, 24, 0.55), 0 0 26px rgba(124, 92, 255, 0.18);
        """
        search_hover_css = "background: rgba(24, 30, 58, 0.74); border-color: rgba(56, 189, 248, 0.55);"
        search_focus_css = "background: rgba(22, 28, 54, 0.84); border-color: #38bdf8; box-shadow: 0 10px 34px rgba(56, 189, 248, 0.22);"
        cust_bg = "linear-gradient(135deg, #8f7ae6, #38bdf8)"
    else:
        search_box_css = """
            background: rgba(37, 36, 40, 0.88);
            backdrop-filter: blur(14px);
            border: 1px solid rgba(255, 255, 255, 0.09);
            box-shadow: 0 4px 18px rgba(0, 0, 0, 0.34);
        """
        search_hover_css = "background: rgba(45, 44, 49, 0.92); border-color: rgba(255, 255, 255, 0.15);"
        search_focus_css = "background: rgba(45, 44, 49, 0.96); border-color: rgba(180, 153, 250, 0.78); box-shadow: 0 6px 24px rgba(0, 0, 0, 0.42);"
        cust_bg = "#b499fa"

    search_base = SEARCH_ENGINES.get(app_cfg.search_engine, SEARCH_ENGINES["duckduckgo"])[1]

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{html.escape(title_text)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }}
  body {{
    min-height: 100vh;
    {bg_css}
    color: #fbfbfe;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 28px 24px 80px;
    position: relative;
  }}
  .wrap {{
    width: 100%;
    max-width: 580px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 28px;
    transform: translateY(-28px);
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 14px;
    user-select: none;
    text-shadow: 0 2px 12px rgba(0, 0, 0, 0.55);
  }}
  .brand h1 {{
    font-size: 32px;
    font-weight: 700;
    letter-spacing: -0.4px;
    color: #ffffff;
  }}
  .logo-ring {{
    width: 52px; height: 52px; border-radius: 50%;
    background: #00aaff;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 24px; color: #fff;
  }}
  .search-box {{
    width: 100%;
    max-width: 560px;
    display: flex;
    align-items: center;
    gap: 12px;
    border-radius: 24px;
    padding: 11px 18px;
    transition: border-color 0.16s, background 0.16s, box-shadow 0.16s;
    {search_box_css}
  }}
  .search-box:hover {{ {search_hover_css} }}
  .search-box:focus-within {{ {search_focus_css} }}
  .search-box input {{
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: #fbfbfe;
    font-size: 14.5px;
  }}
  .search-box input::placeholder {{ color: rgba(235, 235, 245, 0.62); }}
  .customize-btn {{
    position: fixed;
    right: 18px;
    bottom: 18px;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: {cust_bg};
    color: #131215;
    display: flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
    transition: transform 0.14s, filter 0.14s;
  }}
  .customize-btn:hover {{
    transform: scale(1.08);
    filter: brightness(1.08);
  }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="brand" style="display: {'flex' if app_cfg.show_home_logo else 'none'}">{logo_html}<h1>{html.escape(title_text)}</h1></div>

    <form class="search-box" style="display: {'flex' if app_cfg.show_home_search else 'none'}" onsubmit="event.preventDefault(); const q=document.getElementById('q').value.trim(); if(!q) return; const base={json.dumps(search_base)}; window.location.href = (q.includes('://') ? q : (!q.includes(' ') && q.includes('.') ? 'https://' + q : base + encodeURIComponent(q)));">
      {small_logo_html}
      <input id="q" type="text" placeholder="Buscar en la web" autofocus>
    </form>
  </div>

  <a class="customize-btn" href="netlis://appearance" title="Personalizar fondo y apariencia">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#131215" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>
    </svg>
  </a>
</body>
</html>"""
