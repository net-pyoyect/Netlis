"""Real Qt/Chromium probes in isolated processes (also runnable on Linux)."""
import os
import sys
import tempfile
import threading
import socketserver
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
mode = sys.argv[1]
from privacy import PrivacySettings, build_chromium_flags
from newtab import AppearanceSettings

socks_targets = []
class RejectSocks(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            if self.request.recv(3) != b'\x05\x01\x00':
                return
            self.request.sendall(b'\x05\x00')
            header = self.request.recv(4)
            if header != b'\x05\x01\x00\x03':
                return
            size = self.request.recv(1)[0]
            host = b''
            while len(host) < size:
                host += self.request.recv(size-len(host))
            self.request.recv(2)
            socks_targets.append(host.decode('ascii'))
            self.request.sendall(b'\x05\x01\x00\x01' + b'\x00'*6)
        except OSError:
            pass
class SocksServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
socks = SocksServer(('127.0.0.1', 0), RejectSocks)
threading.Thread(target=socks.serve_forever, daemon=True).start()
class Page(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'<title>Netlis Windows probe</title><p>Local test only</p>'
        self.send_response(200); self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *args):
        pass
http = ThreadingHTTPServer(('127.0.0.1', 0), Page)
threading.Thread(target=http.serve_forever, daemon=True).start()
settings = PrivacySettings(proxy_enabled=mode == 'tor', proxy_url=f'socks5://127.0.0.1:{socks.server_address[1]}')
os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = ' '.join(build_chromium_flags(settings))
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer, QUrl
import browser
browser.apply_qt_network_proxy(settings)
app = QApplication(['netlis-windows-probe'])
tmp = tempfile.TemporaryDirectory(prefix='netlis-windows-probe-')
window = browser.BrowserWindow(settings=settings, appearance=AppearanceSettings(image_path=''), data_dir=Path(tmp.name))
window.show()
view = window._current_view()
results = []
loaded = False

def finish(ok, message):
    print(f'{mode}: {message}', flush=True)
    results.append(ok)
    # Destroy the page after returning from its loadFinished signal.
    QTimer.singleShot(0, close_probe)

def close_probe():
    window.close()
    app.quit()

def load_finished(ok):
    global loaded
    if not loaded:
        return
    if mode == 'tor':
        finish(not ok and 'netlis-probe.invalid' in socks_targets,
               f'load={ok}, SOCKS destinations={socks_targets}')
    elif not ok:
        finish(False, 'Local page did not load')
    elif mode == 'direct':
        finish(view.title() == 'Netlis Windows probe', f'Local page title={view.title()}')
    else:
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            window._toggle_turbo_mode()
        saved = PrivacySettings.load(window.settings_path)
        passed = browser._RESTART_REQUESTED and window.interceptor.network_paused and not settings.proxy_enabled and saved.proxy_enabled
        results.append(passed)
        print(f'switch: restart={browser._RESTART_REQUESTED}, paused={window.interceptor.network_paused}, saved_tor={saved.proxy_enabled}', flush=True)
        # The production callback must close all browser windows and stop the event loop.

view.loadFinished.connect(load_finished)
def navigate():
    global loaded
    loaded = True
    target = 'https://netlis-probe.invalid/' if mode == 'tor' else f'http://127.0.0.1:{http.server_port}/'
    view.setUrl(QUrl(target))
QTimer.singleShot(500, navigate)
QTimer.singleShot(30000, lambda: finish(False, 'TIMEOUT'))
app.exec()
http.shutdown(); http.server_close(); socks.shutdown(); socks.server_close()
ok = bool(results) and all(results) and not browser.BrowserWindow._open_windows
# Qt may retain file handles briefly on Windows; temporary profiles contain synthetic data only.
try:
    tmp.cleanup()
except PermissionError:
    pass
os._exit(0 if ok else 1)
