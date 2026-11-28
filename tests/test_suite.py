#!/usr/bin/env python3
"""Suite oficial de pruebas de seguridad, aislamiento, extensiones WebExtension y estabilidad de Netlis."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import netlis_search
import newtab
import plugins
import privacy
import security_shield
import stability
import updater


class TestNetlisCoreSecurity(unittest.TestCase):
    """Pruebas unitarias rápidas (100% sin red) de aislamiento, descargas, resiliencia y mantenimiento."""

    def test_strict_site_isolation_flags(self) -> None:
        cfg = privacy.PrivacySettings()
        flags = privacy.build_chromium_flags(cfg)
        joined = " ".join(flags)
        self.assertIn("--site-per-process", flags)
        self.assertNotIn("--jitless", joined)
        self.assertIn("--max-old-space-size=384", joined)
        self.assertNotIn("--renderer-process-limit", joined)
        feat_flags = [f for f in flags if f.startswith("--enable-features=")]
        self.assertEqual(len(feat_flags), 1, "Debe existir un único --enable-features unificado")
        self.assertIn("StrictOriginIsolation", feat_flags[0])
        self.assertIn("ThirdPartyStoragePartitioning", feat_flags[0])
        self.assertIn("SplitCacheByNetworkIsolationKey", feat_flags[0])

        # Verificar lookup O(1) de rastreadores, reporte por sitio (estilo Brave) y caché de proxy
        self.assertTrue(privacy.is_tracker_host("pixel.facebook.com"))
        self.assertFalse(privacy.is_tracker_host("github.com"))
        inter = privacy.TrackerInterceptor(cfg)
        self.assertIsInstance(inter._is_tor_ready_cached(), bool)
        inter._mark_blocked("www.youtube.com", "doubleclick.net")
        inter._mark_blocked("youtube.com", "doubleclick.net")
        inter._mark_blocked("youtube.com", "youtube.com (Anuncio YouTube)")
        site_tot, site_items = inter.site_report("www.youtube.com")
        self.assertEqual(site_tot, 3)
        self.assertEqual(site_items[0], ("doubleclick.net", 2))

        # Verificar que anti-espionaje-total mantiene navigator.connection para compatibilidad YouTube
        anti_spy = next(p for p in plugins.BUILTIN_PLUGINS if p.plugin_id == "anti-espionaje-total")
        self.assertIn("effectiveType: '4g'", anti_spy.js_code)
        self.assertNotIn("'connection'", anti_spy.js_code.split("for (const api of")[1].split(")")[0])

    def test_deep_download_shield_magic_bytes_and_spoofing(self) -> None:
        # 1. Bloqueo de ataque Unicode RLO y doble extensión
        bad_rlo, reason_rlo = security_shield.inspect_download_request("factura\u202egpj.exe")
        self.assertTrue(bad_rlo)
        self.assertIn("RLO", reason_rlo)

        bad_dbl, reason_dbl = security_shield.inspect_download_request("contrato.pdf.scr")
        self.assertTrue(bad_dbl)
        self.assertIn("Doble extensión", reason_dbl)

        # 2. Bloqueo por origen malicioso o MIME ejecutable camuflado
        bad_mime, _ = security_shield.inspect_download_request(
            "documento.pdf", "https://example.org/doc.pdf", "application/x-dosexec"
        )
        self.assertTrue(bad_mime)

        # 3. Inspección post-descarga de Magic Bytes (binario ELF camuflado de .pdf) + SHA-256
        with tempfile.TemporaryDirectory() as tmp:
            fake_pdf = Path(tmp) / "libro_inocente.pdf"
            fake_pdf.write_bytes(b"\x7fELF\x02\x01\x01\x00PAYLOAD_MALICIOSO")
            safe_ok, digest, reason = security_shield.verify_downloaded_file_safety(fake_pdf)
            self.assertFalse(safe_ok)
            self.assertEqual(len(digest), 64)
            self.assertIn("ELF", reason)
            self.assertFalse(fake_pdf.exists(), "El malware camuflado debe ser eliminado automáticamente")

            real_pdf = Path(tmp) / "informe_real.pdf"
            real_pdf.write_bytes(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n")
            ok2, digest2, _ = security_shield.verify_downloaded_file_safety(real_pdf)
            self.assertTrue(ok2)
            self.assertEqual(len(digest2), 64)
            self.assertTrue(real_pdf.exists())

    def test_atomic_json_corruption_recovery_and_crash_shield(self) -> None:
        stability.install_crash_shield()
        with tempfile.TemporaryDirectory() as tmp:
            cfg_file = Path(tmp) / "privacidad.json"
            stability.atomic_write_json(cfg_file, {"proxy_enabled": True, "ip_region": "ch"})
            # Segunda escritura genera respaldo .bak
            stability.atomic_write_json(cfg_file, {"proxy_enabled": True, "ip_region": "de"})
            # Simular corte de energía que corrompe el archivo primario
            cfg_file.write_text("{corrupt_json_truncated", encoding="utf-8")
            recovered = stability.safe_load_json(cfg_file, {})
            self.assertEqual(recovered.get("ip_region"), "ch")

    def test_cryptographic_updater_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d_dir = Path(tmp)
            valid_domains = {f"malicious-{i}.example.test" for i in range(12_000)}
            ok, count, _ = updater.apply_verified_threat_domains(valid_domains, d_dir)
            self.assertTrue(ok)
            self.assertEqual(count, 12_000)
            st = updater.get_update_status(d_dir)
            self.assertEqual(len(st.get("threat_sha256", "")), 64)

            # Simular fuente truncada/corrupta (< 10,000 dominios): no debe destruir la base buena
            ok_bad, count_after, _ = updater.apply_verified_threat_domains({"only-one.test"}, d_dir)
            self.assertFalse(ok_bad)
            self.assertEqual(count_after, 12_000)

        # Restaurar base real del proyecto
        security_shield.reload_threat_domains(ROOT / "data" / "threat_domains.txt")
        rep = updater.get_security_health_report()
        if sys.platform == "win32":
            self.assertFalse(rep["systemd_timer_installed"])
        else:
            self.assertIsInstance(rep["systemd_timer_installed"], bool)
        self.assertNotEqual(rep["chromium_version"], "desconocido")

    def test_crx3_and_zip_webextension_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t_path = Path(tmp)
            # Construir paquete CRX3 simulado con manifest.json válido
            zip_buf_path = t_path / "payload.zip"
            with zipfile.ZipFile(zip_buf_path, "w") as zf:
                zf.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "manifest_version": 3,
                            "name": "Escudo Prueba CRX",
                            "version": "1.2.0",
                            "description": "Extensión nativa MV3",
                            "permissions": ["storage"],
                            "content_scripts": [{"matches": ["<all_urls>"], "js": ["content.js"]}],
                        }
                    ),
                )
                zf.writestr("content.js", "window.__netlisWebExtLoaded = true;")
            zip_bytes = zip_buf_path.read_bytes()
            fake_crx_header = b"PROTOBUF_HEADER"
            crx_bytes = b"Cr24" + struct.pack("<II", 3, len(fake_crx_header)) + fake_crx_header + zip_bytes
            crx_file = t_path / "escudo.crx"
            crx_file.write_bytes(crx_bytes)

            ok, ext_dir, _ = plugins.extract_web_extension_package(crx_file, t_path / "installed")
            self.assertTrue(ok)
            self.assertIsNotNone(ext_dir)
            summary = plugins.read_manifest_summary(ext_dir)
            self.assertEqual(summary["name"], "Escudo Prueba CRX")
            self.assertEqual(summary["version"], "1.2.0")

    def test_netlis_search_branding_and_rendering(self) -> None:
        html_out = netlis_search.render_search_results_html(
            {
                "query": "quantum linux",
                "via_tor": True,
                "wiki": {"title": "Linux", "snippet": "Núcleo libre", "url": "https://es.wikipedia.org/wiki/Linux"},
                "results": [
                    netlis_search.SearchResult(
                        title="Arch Linux",
                        url="https://archlinux.org/",
                        snippet="Distribución ligera.",
                        sources=["Brave", "WebIndex"],
                    )
                ],
            }
        )
        self.assertIn("Netlis Search", html_out)
        self.assertIn("data:image/jpeg;base64,", html_out)
        self.assertIn("Arch Linux", html_out)
        self.assertIn("Tor SOCKS5h", html_out)

    def test_appearance_antigravity_wallpaper_and_duckduckgo_defaults(self) -> None:
        # 1. DuckDuckGo predeterminado y wallpaper assets/netlis_wallpaper.png si existe
        default_cfg = newtab.AppearanceSettings()
        self.assertEqual(default_cfg.search_engine, "duckduckgo")
        if newtab.DEFAULT_WALLPAPER.is_file():
            self.assertEqual(default_cfg.image_path, "assets/netlis_wallpaper.png")
        self.assertIn("antigravity", newtab.BACKGROUND_PRESETS)

        # 2. Guardar y recargar AppearanceSettings (incluyendo ruta relativa en assets/)
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "apariencia.json"
            saved = newtab.AppearanceSettings(
                preset="antigravity",
                image_path=str(newtab.DEFAULT_WALLPAPER),
                opacity_percent=88,
                search_engine="duckduckgo",
            )
            saved.save(cfg_path)
            raw_json = json.loads(cfg_path.read_text(encoding="utf-8"))
            # No guarda base64 en el JSON, solo la ruta
            self.assertEqual(raw_json["image_path"], "assets/netlis_wallpaper.png")
            self.assertEqual(raw_json["search_engine"], "duckduckgo")

            reloaded = newtab.AppearanceSettings.load(cfg_path)
            self.assertEqual(reloaded.preset, "antigravity")
            self.assertEqual(reloaded.opacity_percent, 88)
            self.assertEqual(reloaded.search_engine, "duckduckgo")

        # 3. Imagen válida genera data URI y cover/overlay; ruta inexistente usa respaldo
        valid_uri = newtab._image_data_uri("assets/netlis_wallpaper.png")
        self.assertTrue(valid_uri.startswith("data:image/png;base64,"))
        html_wp = newtab.render_new_tab_html(0, appearance=reloaded)
        self.assertIn(valid_uri, html_wp)
        self.assertIn("background-size: cover;", html_wp)
        self.assertIn("backdrop-filter: blur(22px);", html_wp)

        broken_cfg = newtab.AppearanceSettings(preset="antigravity", image_path="/ruta/que/no/existe.png")
        self.assertEqual(newtab._image_data_uri(broken_cfg.image_path), "")
        html_fallback = newtab.render_new_tab_html(0, appearance=broken_cfg)
        self.assertIn("#090b16", html_fallback)

        # 4. Modo incógnito mantiene su fondo especial sin mostrar ni sobrescribir el wallpaper normal
        html_inc = newtab.render_new_tab_html(0, incognito=True, appearance=reloaded)
        self.assertIn("#1b1526", html_inc)
        self.assertNotIn(valid_uri, html_inc)

    def test_windows_and_cross_platform_compatibility(self) -> None:
        import gecko_engine
        import tor_manager

        self.assertTrue((ROOT / "launch.bat").is_file())
        self.assertTrue(callable(tor_manager._resolve_tor_bin))
        self.assertTrue(callable(gecko_engine._resolve_firefox_bin))

        # Simular entorno Windows en updater.install_systemd_timer() para verificar salida segura
        orig_plat = sys.platform
        try:
            sys.platform = "win32"
            ok_win, msg_win = updater.install_systemd_timer()
            self.assertFalse(ok_win)
            self.assertIn("Linux", msg_win)
        finally:
            sys.platform = orig_plat

    def test_app_self_updater_and_release_bump(self) -> None:
        import release
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading

        self.assertEqual(release.bump_version_str("1.0.0", "patch"), "1.0.1")
        self.assertEqual(release.bump_version_str("1.0.9", "minor"), "1.1.0")
        self.assertEqual(release.bump_version_str("1.2.3", "major"), "2.0.0")

        with tempfile.TemporaryDirectory() as tmp:
            p_dir = Path(tmp)
            (p_dir / "version.json").write_text(
                json.dumps({"version": "1.0.0", "repo": "demo/netlis", "branch": "main"}),
                encoding="utf-8",
            )
            (p_dir / "data").mkdir()
            (p_dir / "data" / "privacidad.json").write_text('{"keep": true, "proxy_enabled": false}', encoding="utf-8")

            # Construir ZIP de actualización simulada en servidor local
            zip_path = p_dir / "rel.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("netlis-main/version.json", json.dumps({"version": "1.1.0", "notes": "Nueva mejora"}))
                zf.writestr("netlis-main/data/privacidad.json", '{"overwritten": false}')
            zip_bytes = zip_path.read_bytes()

            class _RelHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path.endswith("version.json"):
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(json.dumps({"version": "1.1.0", "notes": "Nueva mejora"}).encode("utf-8"))
                    else:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(zip_bytes)

                def log_message(self, *_args):
                    pass

            srv = HTTPServer(("127.0.0.1", 0), _RelHandler)
            port = srv.server_address[1]
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            try:
                # Mock the Tor transport; the feed must never fall back to direct HTTP.
                with patch.object(updater, "fetch_text_via_socks5", return_value=json.dumps({"version": "1.1.0", "notes": "Nueva mejora"})):
                    chk = updater.check_app_update(p_dir, manifest_url=f"http://127.0.0.1:{port}/version.json")
                self.assertTrue(chk["ok"])
                self.assertTrue(chk["has_update"])
                self.assertEqual(chk["remote_version"], "1.1.0")

                ok_upd, _ = updater.apply_app_update(p_dir, archive_url=f"http://127.0.0.1:{port}/rel.zip")
                self.assertTrue(ok_upd)
                self.assertEqual(updater.get_local_version_info(p_dir)["version"], "1.1.0")
                # data/ del usuario debe permanecer intacto
                self.assertEqual(json.loads((p_dir / "data" / "privacidad.json").read_text())["keep"], True)
            finally:
                srv.shutdown()
                srv.server_close()


class TestNetlisEngineIntegration(unittest.TestCase):
    """Pruebas de integración con el motor C++ QtWebEngine (requiere entorno con soporte de namespaces)."""

    @unittest.skipIf(os.environ.get("NETLIS_SKIP_WEBENGINE") == "1", "Omitido en modo sin namespaces")
    def test_native_cpp_webextension_and_isolated_containers(self) -> None:
        from PyQt6.QtWidgets import QApplication
        import browser

        app = QApplication.instance() or QApplication([sys.argv[0]])
        with tempfile.TemporaryDirectory() as tmp:
            t_dir = Path(tmp)
            cfg = privacy.PrivacySettings(isolated_tab_containers=True, proxy_enabled=False)
            win = browser.BrowserWindow(incognito=True, settings=cfg, data_dir=t_dir / "data")
            win.show()
            app.processEvents()

            # 1. Verificar que una pestaña nueva con contenedor aislado recibe su propio QWebEngineProfile separado
            v_first = win._current_view()
            v_second = win.add_new_tab(None, "Contenedor 2", isolated_container=True)
            self.assertIsNot(v_first.page().profile(), v_second.page().profile())

            # 1b. Verificar compatibilidad web: LocalStorage activo, portapapeles activo y UA alineado con Chromium 140
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            ws = win.profile.settings()
            self.assertTrue(ws.testAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled))
            self.assertTrue(ws.testAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard))
            self.assertIn("Chrome/140.", win.profile.httpUserAgent())

            # 1c. Verificar AppearanceDialog: Quitar limpia image_path, Aplicar actualiza en vivo y DuckDuckGo sigue por defecto
            from dialogs import AppearanceDialog
            applied_list = []
            dlg = AppearanceDialog(
                newtab.AppearanceSettings(preset="netlis", image_path="assets/netlis_wallpaper.png"),
                lambda u: applied_list.append(u),
                win,
            )
            dlg._select_preset("antigravity")
            dlg._clear_image()
            self.assertEqual(dlg.appearance.image_path, "")
            dlg._apply()
            self.assertEqual(len(applied_list), 1)
            self.assertEqual(applied_list[0].preset, "antigravity")
            self.assertEqual(applied_list[0].search_engine, "duckduckgo")
            self.assertIn("duckduckgo.com", browser.normalize_input_to_url("hola", applied_list[0].search_engine).toString())

            # 2. Instalar y cargar una WebExtension MV3 real en QWebEngineExtensionManager C++
            ext_src = t_dir / "demo_mv3"
            ext_src.mkdir()
            (ext_src / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": 3,
                        "name": "Netlis Native MV3 Test",
                        "version": "1.0.0",
                        "description": "Prueba real C++ QWebEngineExtensionManager",
                        "content_scripts": [{"matches": ["https://*/*"], "js": ["c.js"]}],
                    }
                ),
                encoding="utf-8",
            )
            (ext_src / "c.js").write_text("console.log('MV3 ok');", encoding="utf-8")

            ok, msg = win._install_web_extension_path(ext_src)
            self.assertTrue(ok, msg)
            loaded_exts = win._list_web_extensions()
            names = [e["name"] for e in loaded_exts]
            self.assertIn("Netlis Native MV3 Test", names)
            target_id = next(e["id"] for e in loaded_exts if e["name"] == "Netlis Native MV3 Test")
            win._uninstall_web_extension(target_id)
            self.assertEqual(len(win._list_web_extensions()), 0)

            win.close()
            app.processEvents()


if __name__ == "__main__":
    res = unittest.main(exit=False)
    os._exit(0 if res.result.wasSuccessful() else 1)
