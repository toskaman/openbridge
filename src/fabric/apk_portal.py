"""Time-limited LAN download of one staged file (Companion APK by default, agent builds on request), started only
by the owner from the local UI.

Binds to the PC's private LAN address (never 0.0.0.0), serves exactly one file at one path, answers only clients in
private address ranges, and stops by itself after a few minutes. The phone still shows Android's own install prompt;
nothing is installed silently."""
import hashlib
import ipaddress
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PATH = '/openbridge-companion.apk'
APK_FILENAME = 'openbridge-companion.apk'
APK_CONTENT_TYPE = 'application/vnd.android.package-archive'


class ApkPortal:
    def __init__(self, apk, lan_ip, minutes=10, clock=time.monotonic, filename=None, content_type=None, url_path=None):
        apk = Path(apk)
        if not apk.is_file():
            raise FileNotFoundError(f'{apk.name} is not staged on this PC')
        ip = ipaddress.ip_address(lan_ip)
        if not ip.is_private or ip.is_loopback:
            raise ValueError('LAN address must be private')
        self.data = apk.read_bytes()
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        self.lan_ip, self.minutes, self.clock = lan_ip, max(1, min(int(minutes), 30)), clock
        self.filename = filename or APK_FILENAME
        self.content_type = content_type or APK_CONTENT_TYPE
        self.page = url_path or PATH
        self.downloads = 0
        self._srv = None
        self._timer = None

    def start(self):
        portal = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def do_GET(self):
                if portal.clock() >= portal.expires_at:
                    return self.send_error(410, "Download link expired")
                try:
                    if not ipaddress.ip_address(self.client_address[0]).is_private:
                        return self.send_error(403)
                except ValueError:
                    return self.send_error(403)
                if self.path != portal.page:
                    return self.send_error(404)
                portal.downloads += 1
                self.send_response(200)
                self.send_header('Content-Type', portal.content_type)
                self.send_header('Content-Disposition', f'attachment; filename="{portal.filename}"')
                self.send_header('Content-Length', str(len(portal.data)))
                self.end_headers()
                self.wfile.write(portal.data)
        self._srv = ThreadingHTTPServer((self.lan_ip, 0), H)
        self._srv.daemon_threads = True
        self.expires_at = self.clock() + self.minutes * 60
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        self._timer = threading.Timer(self.minutes * 60, self.stop)
        self._timer.daemon = True
        self._timer.start()
        return self

    @property
    def url(self):
        return f'http://{self.lan_ip}:{self._srv.server_address[1]}{self.page}'

    def running(self):
        return self._srv is not None and self.clock() < self.expires_at

    def stop(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._srv:
            self._srv.shutdown(); self._srv.server_close(); self._srv = None

    def state(self):
        return {'running': self.running(), 'url': self.url if self.running() else None, 'sha256': self.sha256,
                'filename': self.filename, 'content_type': self.content_type,
                'expires_in_s': max(0, round(self.expires_at - self.clock())) if self._srv else 0, 'downloads': self.downloads}
