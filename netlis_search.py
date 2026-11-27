"""Buscador propio Netlis Search: metabuscador privado multi-fuente con tu logo y 0% rastreo."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import base64
import html
import json
from pathlib import Path
import re
import socket
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

from newtab import _image_data_uri
import security_shield
from tor_manager import SOCKS_HOST, SOCKS_PORT, fetch_text_via_socks5


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    sources: list[str]
    score: float = 1.0


def _is_tor_up() -> bool:
    try:
        with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=0.2):
            return True
    except OSError:
        return False


def _fetch_text(url_str: str, use_tor: bool, timeout: float = 6.5, custom_ua: str = "") -> str:
    if use_tor and _is_tor_up():
        return fetch_text_via_socks5(url_str, socks_port=SOCKS_PORT, timeout=timeout)
    ua = custom_ua or "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    req = Request(
        url_str,
        headers={
            "User-Agent": ua,
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _unwrap_bing_url(href: str) -> str:
    parsed = urlparse(href)
    if "bing.com" in parsed.netloc and parsed.path.startswith("/ck/a"):
        qs = parse_qs(parsed.query)
        u_val = (qs.get("u") or [""])[0]
        if u_val.startswith("a1") and len(u_val) > 2:
            b64_part = u_val[2:]
            pad = "=" * ((4 - len(b64_part) % 4) % 4)
            try:
                decoded = base64.urlsafe_b64decode(b64_part + pad).decode("utf-8", errors="ignore")
                if decoded.startswith(("http://", "https://")):
                    return decoded
            except Exception:
                pass
    return href


def _search_bing(query: str, use_tor: bool) -> list[SearchResult]:
    url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=es"
    raw = _fetch_text(url, use_tor=use_tor, timeout=6.5)
    results: list[SearchResult] = []
    blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', raw, flags=re.DOTALL | re.IGNORECASE)
    for blk in blocks[:15]:
        m_link = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, flags=re.DOTALL | re.IGNORECASE)
        if not m_link:
            continue
        clean_url = _unwrap_bing_url(html.unescape(m_link.group(1)).strip())
        if not clean_url.startswith(("http://", "https://")):
            continue
        title = _clean_html_text(m_link.group(2))
        m_desc = re.search(r'<p[^>]*>(.*?)</p>', blk, flags=re.DOTALL | re.IGNORECASE)
        snippet = _clean_html_text(m_desc.group(1)) if m_desc else ""
        results.append(SearchResult(title=title or clean_url, url=clean_url, snippet=snippet, sources=["WebIndex"], score=1.3))
    return results


def _clean_html_text(raw: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _unwrap_ddg_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
    return href


def _search_brave(query: str, use_tor: bool) -> list[SearchResult]:
    url = f"https://search.brave.com/search?q={quote_plus(query)}&source=web"
    raw = _fetch_text(url, use_tor=use_tor, timeout=6.5)
    results: list[SearchResult] = []
    # Bloques principales de resultados web en Brave Search
    blocks = re.split(r'<div[^>]+class="[^"]*snippet[^"]*"[^>]*>', raw)
    for blk in blocks[1:22]:
        m_link = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', blk, flags=re.DOTALL | re.IGNORECASE)
        if not m_link:
            continue
        href = html.unescape(m_link.group(1)).strip()
        if "search.brave.com" in href:
            continue
        title = _clean_html_text(m_link.group(2))
        if not title or len(title) < 3:
            continue
        m_desc = re.search(
            r'<(?:p|div)[^>]+class="[^"]*(?:snippet-description|content|desc)[^"]*"[^>]*>(.*?)</(?:p|div)>',
            blk,
            flags=re.DOTALL | re.IGNORECASE,
        )
        snippet = _clean_html_text(m_desc.group(1)) if m_desc else ""
        results.append(SearchResult(title=title, url=href, snippet=snippet, sources=["Brave"], score=1.25))
    return results


def _search_ddg_html(query: str, use_tor: bool) -> list[SearchResult]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    raw = _fetch_text(url, use_tor=use_tor, timeout=6.5)
    results: list[SearchResult] = []
    links = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    snippets = re.findall(
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    for idx, (raw_href, raw_title) in enumerate(links[:15]):
        clean_url = _unwrap_ddg_url(html.unescape(raw_href).strip())
        if not clean_url.startswith(("http://", "https://")) or "duckduckgo.com/y.js" in clean_url:
            continue
        title = _clean_html_text(raw_title)
        snip_raw = ""
        if idx < len(snippets):
            snip_raw = snippets[idx][0] or snippets[idx][1]
        results.append(
            SearchResult(
                title=title or clean_url,
                url=clean_url,
                snippet=_clean_html_text(snip_raw),
                sources=["WebIndex"],
                score=1.0,
            )
        )
    return results


def _search_wikipedia_card(query: str, use_tor: bool) -> dict[str, str] | None:
    api_url = (
        "https://es.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={quote_plus(query)}&srlimit=1&utf8=1&format=json"
    )
    raw = _fetch_text(
        api_url,
        use_tor=use_tor,
        timeout=5.0,
        custom_ua="NetlisBrowser/1.0 (Linux; +https://netlis.local)",
    )
    data = json.loads(raw)
    hits = data.get("query", {}).get("search", [])
    if not hits:
        return None
    title = str(hits[0].get("title", "")).strip()
    snippet = _clean_html_text(str(hits[0].get("snippet", "")))
    if not title:
        return None
    wiki_url = f"https://es.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}"
    return {"title": title, "snippet": snippet, "url": wiki_url}


def run_netlis_metasearch(query: str, use_tor: bool = True) -> dict:
    """Ejecuta búsqueda paralela privada (WebIndex + Brave + Wikipedia) fusionando y limpiando resultados."""
    clean_q = query.strip()
    if not clean_q:
        return {"query": "", "results": [], "wiki": None, "via_tor": use_tor and _is_tor_up()}

    via_tor = use_tor and _is_tor_up()
    bing_res: list[SearchResult] = []
    brave_res: list[SearchResult] = []
    wiki_card: dict[str, str] | None = None

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_bing = pool.submit(_search_bing, clean_q, via_tor)
        f_brave = pool.submit(_search_brave, clean_q, via_tor)
        f_wiki = pool.submit(_search_wikipedia_card, clean_q, via_tor)
        try:
            bing_res = f_bing.result(timeout=7.5)
        except Exception:
            bing_res = []
        try:
            brave_res = f_brave.result(timeout=7.5)
        except Exception:
            brave_res = []
        try:
            wiki_card = f_wiki.result(timeout=5.5)
        except Exception:
            wiki_card = None

    merged: dict[str, SearchResult] = {}
    for pos, item in enumerate(bing_res + brave_res):
        bad, _ = security_shield.analyze_url_threat(item.url)
        if bad:
            continue
        norm = item.url.rstrip("/").lower()
        if norm in merged:
            existing = merged[norm]
            for src in item.sources:
                if src not in existing.sources:
                    existing.sources.append(src)
            existing.score += 0.9
            if len(item.snippet) > len(existing.snippet):
                existing.snippet = item.snippet
        else:
            item.score += max(0.0, 0.5 - pos * 0.02)
            merged[norm] = item

    ordered = sorted(merged.values(), key=lambda r: r.score, reverse=True)[:18]
    return {
        "query": clean_q,
        "results": ordered,
        "wiki": wiki_card,
        "via_tor": via_tor,
    }


def _logo_html() -> str:
    logo_file = Path(__file__).resolve().parent / "assets" / "netlis_logo.jpg"
    logo_uri = _image_data_uri(str(logo_file))
    if logo_uri:
        return (
            f'<img src="{logo_uri}" alt="Netlis" '
            'style="width:40px;height:40px;border-radius:50%;object-fit:cover;'
            'box-shadow:0 4px 14px rgba(0,0,0,0.4);border:1.5px solid rgba(255,255,255,0.22);">'
        )
    return '<div class="logo-fallback">N</div>'


def render_search_loading_html(query: str, via_tor: bool) -> str:
    safe_q = html.escape(query)
    mode_txt = "Circuito Tor cifrado" if via_tor else "Modo Turbo directo"
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{safe_q} — Netlis Search</title>
<style>
  body {{ margin:0; min-height:100vh; background:#1c1b22; color:#f4f4fc;
          font:15px/1.5 system-ui,-apple-system,sans-serif; display:flex; align-items:center; justify-content:center; }}
  .box {{ text-align:center; padding:32px 36px; border-radius:20px; background:rgba(255,255,255,0.05);
          border:1px solid rgba(255,255,255,0.12); box-shadow:0 16px 40px rgba(0,0,0,0.4); }}
  .brand {{ display:flex; align-items:center; justify-content:center; gap:12px; margin-bottom:14px; }}
  .spin {{ width:28px; height:28px; margin:12px auto; border-radius:50%;
           border:3px solid rgba(0,221,255,0.22); border-top-color:#00ddff; animation:s 0.8s linear infinite; }}
  @keyframes s {{ to {{ transform:rotate(360deg); }} }}
  .sub {{ color:rgba(235,235,248,0.68); font-size:13px; }}
</style></head><body>
  <div class="box">
    <div class="brand">{_logo_html()}<strong style="font-size:20px;">Netlis Search</strong></div>
    <div class="spin"></div>
    <div>Buscando <b>«{safe_q}»</b>…</div>
    <div class="sub">{mode_txt} • Cero cookies • Cero anuncios</div>
  </div>
</body></html>"""


def render_search_results_html(data: dict) -> str:
    query = str(data.get("query", ""))
    safe_q = html.escape(query)
    results: list[SearchResult] = data.get("results", [])
    wiki = data.get("wiki")
    via_tor = bool(data.get("via_tor", False))

    badge_mode = "Tor SOCKS5h" if via_tor else "Modo Turbo"
    wiki_html = ""
    if wiki:
        w_title = html.escape(wiki["title"])
        w_snip = html.escape(wiki["snippet"])
        w_url = html.escape(wiki["url"])
        wiki_html = f"""
        <div class="wiki-card">
          <div class="wiki-tag">Respuesta rápida · Wikipedia</div>
          <a class="wiki-title" href="{w_url}">{w_title}</a>
          <p class="wiki-snip">{w_snip}…</p>
        </div>"""

    cards_html = ""
    if not results:
        cards_html = """
        <div class="empty-card">
          <h3>No se pudieron obtener resultados en este intento</h3>
          <p>Si estás en Modo Tor y el circuito aún está iniciando, recarga en un par de segundos o cambia a Modo Turbo.</p>
        </div>"""
    else:
        for res in results:
            parsed = urlparse(res.url)
            domain = parsed.netloc or res.url
            fav = f"https://www.google.com/s2/favicons?sz=32&domain={html.escape(domain)}"
            src_pill = " + ".join(res.sources)
            cards_html += f"""
            <article class="res-card">
              <div class="res-meta">
                <img class="fav" src="{fav}" alt="" onerror="this.style.display='none'">
                <span class="dom">{html.escape(domain)}</span>
                <span class="src-pill">{html.escape(src_pill)}</span>
              </div>
              <a class="res-title" href="{html.escape(res.url)}">{html.escape(res.title)}</a>
              <div class="res-url">{html.escape(res.url[:110])}</div>
              <p class="res-snip">{html.escape(res.snippet or 'Sin descripción disponible.')}</p>
            </article>"""

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>{safe_q} — Netlis Search</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; font-family:system-ui,-apple-system,'Segoe UI',sans-serif; }}
  body {{ background:#1c1b22; color:#f2f2fa; min-height:100vh; padding-bottom:48px; }}
  header {{
    position:sticky; top:0; z-index:10;
    background:rgba(36,35,48,0.88); backdrop-filter:blur(18px);
    border-bottom:1px solid rgba(255,255,255,0.1);
    padding:14px 28px; display:flex; align-items:center; gap:18px; flex-wrap:wrap;
  }}
  .brand {{ display:flex; align-items:center; gap:10px; text-decoration:none; color:#fff; font-weight:800; font-size:18px; }}
  .search-form {{
    flex:1; max-width:640px; min-width:240px; display:flex; align-items:center;
    background:#15141c; border:1px solid rgba(255,255,255,0.16); border-radius:14px; padding:4px 10px;
  }}
  .search-form:focus-within {{ border-color:#00ddff; }}
  .search-form input {{
    flex:1; background:transparent; border:none; outline:none; color:#fff; font-size:15px; padding:8px;
  }}
  .search-form button {{
    background:linear-gradient(180deg,#0a84ff,#0066cc); color:#fff; border:none; border-radius:10px;
    padding:7px 14px; font-weight:600; cursor:pointer; font-size:13px;
  }}
  .pill {{
    margin-left:auto; font-size:12px; font-weight:600; color:#6ceaff;
    background:rgba(0,221,255,0.12); border:1px solid rgba(0,221,255,0.35);
    padding:5px 12px; border-radius:12px;
  }}
  main {{ max-width:860px; margin:22px auto 0; padding:0 24px; display:flex; flex-direction:column; gap:14px; }}
  .stats {{ font-size:12px; color:rgba(235,235,248,0.58); }}
  .wiki-card {{
    background:rgba(255,255,255,0.06); border:1px solid rgba(0,221,255,0.32);
    border-radius:16px; padding:16px 20px;
  }}
  .wiki-tag {{ font-size:11px; font-weight:700; color:#6ceaff; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }}
  .wiki-title {{ font-size:18px; font-weight:700; color:#fff; text-decoration:none; display:inline-block; margin-bottom:6px; }}
  .wiki-title:hover {{ text-decoration:underline; }}
  .wiki-snip {{ font-size:13.5px; line-height:1.55; color:#d8d8e6; }}
  .res-card {{
    background:rgba(255,255,255,0.035); border:1px solid rgba(255,255,255,0.08);
    border-radius:14px; padding:14px 18px; transition:border-color 0.15s, background 0.15s;
  }}
  .res-card:hover {{ background:rgba(255,255,255,0.065); border-color:rgba(255,255,255,0.2); }}
  .res-meta {{ display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
  .fav {{ width:16px; height:16px; border-radius:4px; }}
  .dom {{ font-size:12px; color:#c8c8d8; font-weight:600; }}
  .src-pill {{
    margin-left:auto; font-size:10px; color:#b4b4c8;
    background:rgba(255,255,255,0.08); padding:2px 8px; border-radius:8px;
  }}
  .res-title {{ font-size:17px; font-weight:700; color:#7cc4ff; text-decoration:none; display:block; margin-bottom:2px; }}
  .res-title:hover {{ text-decoration:underline; color:#9ed4ff; }}
  .res-url {{ font-size:11px; color:rgba(200,200,220,0.48); margin-bottom:6px; word-break:break-all; }}
  .res-snip {{ font-size:13.5px; line-height:1.5; color:#d7d7e5; }}
  .empty-card {{ padding:28px; text-align:center; background:rgba(255,255,255,0.04); border-radius:16px; }}
  .empty-card p {{ margin-top:8px; color:#b8b8ca; font-size:13px; }}
</style></head><body>
  <header>
    <a class="brand" href="netlis://newtab">{_logo_html()}<span>Netlis Search</span></a>
    <form class="search-form" onsubmit="event.preventDefault(); const v=document.getElementById('sq').value.trim(); if(v) window.location.href='netlis://search?q='+encodeURIComponent(v);">
      <input id="sq" type="text" value="{safe_q}" placeholder="Buscar con Netlis Search...">
      <button type="submit">Buscar</button>
    </form>
    <div class="pill">{badge_mode} • Sin rastreo</div>
  </header>
  <main>
    <div class="stats">{len(results)} resultados privados para «{safe_q}» • 0 rastreadores</div>
    {wiki_html}
    {cards_html}
  </main>
</body></html>"""
