"""APK portal expiry/stop checks over loopback with no APK installation or LAN exposure."""
import tempfile
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import ProxyHandler, build_opener
from urllib.error import HTTPError
from unittest.mock import patch
from src.fabric import apk_portal as ap

class Timer:
    def __init__(self, interval, callback):
        self.cancelled = False
        self.daemon = False
    def start(self): pass
    def cancel(self): self.cancelled = True

class Lifecycle(unittest.TestCase):
    def test_expiry_is_checked_at_request_time(self):
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder)/'test.apk'; apk.write_bytes(b'fixture-only')
            clock = [0]
            with patch.object(ap, 'ThreadingHTTPServer', lambda address, handler: ThreadingHTTPServer(('127.0.0.1', 0), handler)), patch.object(ap.threading, 'Timer', Timer):
                portal = ap.ApkPortal(apk, '192.168.1.20', minutes=1, clock=lambda: clock[0]).start()
                try:
                    url = f'http://127.0.0.1:{portal._srv.server_port}{ap.PATH}'
                    clock[0] = 61
                    with self.assertRaises(HTTPError) as error:
                        build_opener(ProxyHandler({})).open(url)
                    self.assertEqual(error.exception.code, 410)
                    error.exception.close()
                finally: portal.stop()
    def test_stop_cancels_shutdown_timer(self):
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder)/'test.apk'; apk.write_bytes(b'fixture-only')
            timers = []
            def timer(*args):
                t = Timer(*args); timers.append(t); return t
            with patch.object(ap, 'ThreadingHTTPServer', lambda address, handler: ThreadingHTTPServer(('127.0.0.1', 0), handler)), patch.object(ap.threading, 'Timer', timer):
                portal = ap.ApkPortal(apk, '192.168.1.20').start()
                portal.stop()
                self.assertTrue(timers[0].cancelled)
                self.assertTrue(timers[0].daemon)
                self.assertFalse(portal.running())


class ArtifactFile(unittest.TestCase):
    def test_serves_named_artifact_on_own_path(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder)/'agent_x64.exe'; exe.write_bytes(b'MZfixture')
            with patch.object(ap, 'ThreadingHTTPServer', lambda address, handler: ThreadingHTTPServer(('127.0.0.1', 0), handler)), patch.object(ap.threading, 'Timer', Timer):
                portal = ap.ApkPortal(exe, '192.168.1.20', filename='agent_x64.exe',
                                      content_type='application/octet-stream', url_path='/agent_x64.exe').start()
                try:
                    base = f'http://127.0.0.1:{portal._srv.server_port}'
                    r = build_opener(ProxyHandler({})).open(base + '/agent_x64.exe')
                    self.assertEqual(r.read(), b'MZfixture')
                    self.assertEqual(r.headers.get_content_type(), 'application/octet-stream')
                    self.assertIn('agent_x64.exe', r.headers.get('Content-Disposition'))
                    r.close()
                    with self.assertRaises(HTTPError) as error:
                        build_opener(ProxyHandler({})).open(base + ap.PATH)
                    self.assertEqual(error.exception.code, 404)
                    error.exception.close()
                finally: portal.stop()

    def test_defaults_are_still_the_apk(self):
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder)/'a.apk'; apk.write_bytes(b'PK\x03\x04fake')
            p = ap.ApkPortal(apk, '192.168.1.2')
            with patch.object(ap, 'ThreadingHTTPServer', lambda address, handler: ThreadingHTTPServer(('127.0.0.1', 0), handler)), patch.object(ap.threading, 'Timer', Timer):
                p.start()
                try:
                    self.assertTrue(p.url.endswith(ap.PATH))
                    self.assertEqual(p.state()['filename'], 'openbridge-companion.apk')
                finally: p.stop()
