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
