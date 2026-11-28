import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from dataclasses import replace

from tor_manager import fetch_text_via_socks5, authenticated_control
from plugins import PluginManager
from privacy import PrivacySettings


class LeakFixTests(unittest.TestCase):
    def test_http_script_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch('plugins.fetch_text_via_socks5') as fetch:
            ok, _ = PluginManager(Path(tmp)).install_from_url('http://example.org/a.user.js')
            self.assertFalse(ok)
            fetch.assert_not_called()

    def test_https_redirect_cannot_downgrade(self):
        raw = MagicMock()
        raw.__enter__.return_value = raw
        raw.recv.side_effect = [b'\x05\x00', b'\x05\x00\x00\x01', b'\x00'*6]
        tls = MagicMock()
        tls.__enter__.return_value = tls
        tls.recv.side_effect = [b'HTTP/1.1 302 Found\r\nLocation: http://example.org/plain.js\r\n\r\n', b'']
        with patch('tor_manager.socket.create_connection', return_value=raw) as connect, patch('tor_manager.ssl.create_default_context') as context:
            context.return_value.wrap_socket.return_value = tls
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                fetch_text_via_socks5('https://example.org/script.js')
            self.assertEqual(connect.call_count, 1)
            context.return_value.wrap_socket.assert_called_once_with(raw, server_hostname='example.org')

    def test_missing_cookie_never_uses_empty_authentication(self):
        with tempfile.TemporaryDirectory() as tmp, patch('tor_manager.socket.create_connection') as connect:
            self.assertFalse(authenticated_control(Path(tmp)/'missing', ['SIGNAL NEWNYM'])[0])
            connect.assert_not_called()

    def test_rejected_authentication_never_sends_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp)/'cookie'; cookie.write_bytes(b'x'*32)
            sock = MagicMock(); sock.__enter__.return_value = sock
            sock.makefile.return_value = io.BytesIO(b'515 Authentication failed\r\n')
            with patch('tor_manager.socket.create_connection', return_value=sock):
                self.assertFalse(authenticated_control(cookie, ['SIGNAL NEWNYM'])[0])
            self.assertEqual(sock.sendall.call_count, 1)
            self.assertIn((b'x'*32).hex().encode(), sock.sendall.call_args.args[0])

    def test_all_network_changes_require_restart(self):
        from browser import BrowserWindow
        current = PrivacySettings(proxy_enabled=False)
        window = SimpleNamespace(settings=current, _restart_for_network_change=MagicMock())
        for updated in [replace(current, proxy_enabled=True), replace(current, proxy_url='socks5://127.0.0.1:1234')]:
            BrowserWindow._apply_privacy_settings(window, updated)
            window._restart_for_network_change.assert_called_with(updated)
            self.assertIs(window.settings, current)

    def test_cancel_restart_preserves_active_and_saved_settings(self):
        import browser
        window = SimpleNamespace(settings=PrivacySettings(proxy_enabled=False))
        updated = MagicMock()
        with patch.object(browser.QMessageBox, 'question', return_value=browser.QMessageBox.StandardButton.No):
            browser.BrowserWindow._restart_for_network_change(window, updated)
        updated.save.assert_not_called()
        self.assertFalse(window.settings.proxy_enabled)

    def test_tor_kill_switch_works_without_optional_plugin(self):
        from PyQt6.QtCore import QUrl
        from privacy import TrackerInterceptor
        interceptor = TrackerInterceptor(PrivacySettings(proxy_enabled=True), anti_spy_enabled=lambda: False)
        info = MagicMock()
        info.requestUrl.return_value = QUrl('https://example.org/')
        info.firstPartyUrl.return_value = QUrl('https://example.org/')
        with patch.object(interceptor, '_is_tor_ready_cached', return_value=False):
            interceptor.interceptRequest(info)
        info.block.assert_called_once_with(True)

    def test_restart_entrypoint_removes_previous_mode_flags(self):
        import ast
        import browser
        source = ast.parse(Path(browser.__file__).read_text(encoding="utf-8"))
        entry = source.body[-1]
        for frozen in (False, True):
            process = SimpleNamespace(executable='/python', argv=['browser.py', '--no-tor', '--incognito'], frozen=frozen)
            os_mock = MagicMock()
            os_mock.environ = {'QTWEBENGINE_CHROMIUM_FLAGS': '--proxy-server=old'}
            scope = {'__name__': '__main__', '__file__': browser.__file__, 'main': lambda: 0,
                     '_RESTART_REQUESTED': True, '_RESTART_TEMP_DIRS': set(), '_INITIAL_CHROMIUM_FLAGS': None,
                     'os': os_mock, 'sys': process, 'Path': Path}
            with self.assertRaises(SystemExit):
                exec(compile(ast.Module(body=[entry], type_ignores=[]), '<restart-test>', 'exec'), scope)
            executable, argv, env = os_mock.execve.call_args.args
            self.assertNotIn('--no-tor', argv)
            self.assertIn('--incognito', argv)
            self.assertNotIn('QTWEBENGINE_CHROMIUM_FLAGS', env)
            self.assertEqual(argv[0], executable)
            self.assertEqual(len(argv), 2 if frozen else 3)
