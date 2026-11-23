"""Chaos network: the Home Assistant client against a hostile loopback server.

Every wire failure must fail closed as HAError (or HABlocked for a refused
token): no half-read state, no phantom success, no unexpected exception type
escaping the adapter.
"""
import functools
import json
import socket
import struct
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from src.adapters import home_assistant as HA


def serve(handler):
    srv = HTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def client_for(srv, timeout=2.0):
    return HA.HomeAssistant('http://127.0.0.1:%d' % srv.server_port, 'tok',
                            http=functools.partial(HA._http, timeout=timeout))


class Chaos(unittest.TestCase):
    def test_connection_refused(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        closed = HA.HomeAssistant('http://127.0.0.1:%d' % port, 't')
        with self.assertRaises(HA.HAError):
            closed.ping()

    def test_timeout(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                time.sleep(5)

        srv = serve(H)
        try:
            with self.assertRaises(HA.HAError):
                client_for(srv, timeout=0.3).ping()
        finally:
            srv.shutdown()
            srv.server_close()

    def test_truncated_body(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', '5000')
                self.end_headers()
                try:
                    self.wfile.write(b'[{"entity_id": "ligh')
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = True

        srv = serve(H)
        try:
            with self.assertRaises(HA.HAError):
                client_for(srv).states()
        finally:
            srv.shutdown()
            srv.server_close()

    def test_reset_without_answer(self):
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        lsock.bind(('127.0.0.1', 0))
        lsock.listen(1)
        stop = threading.Event()

        def killer():
            while not stop.is_set():
                try:
                    conn, _ = lsock.accept()
                except OSError:
                    return
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                conn.close()

        threading.Thread(target=killer, daemon=True).start()
        try:
            cli = HA.HomeAssistant('http://127.0.0.1:%d' % lsock.getsockname()[1], 't')
            with self.assertRaises(HA.HAError):
                cli.ping()
        finally:
            stop.set()
            lsock.close()

    def test_http_errors(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _send(self, code, doc):
                body = json.dumps(doc).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == '/api/err500':
                    return self._send(500, {})
                if self.path == '/api/err401':
                    return self._send(401, {})
                if self.path == '/api/redir':
                    self.send_response(302)
                    self.send_header('Location', '/api/')
                    self.end_headers()
                    return
                if self.path == '/api/notjson':
                    body = b'<html>nope</html>'
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return self._send(200, {'message': 'ok'})

        srv = serve(H)
        try:
            base = 'http://127.0.0.1:%d' % srv.server_port
            with self.assertRaises(HA.HAError):
                HA._http('GET', base + '/api/err500', 't')
            with self.assertRaises(HA.HABlocked):
                HA._http('GET', base + '/api/err401', 't')
            with self.assertRaisesRegex(HA.HAError, 'redirect'):
                HA._http('GET', base + '/api/redir', 't')
            with self.assertRaises(HA.HAError):
                HA._http('GET', base + '/api/notjson', 't')
        finally:
            srv.shutdown()
            srv.server_close()

    def test_oversize_body(self):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                body = b'{"blob":"' + b'x' * (HA.MAX_BYTES + 8) + b'"}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        srv = serve(H)
        try:
            with self.assertRaises(HA.HAError):
                client_for(srv).states()
        finally:
            srv.shutdown()
            srv.server_close()

    def test_wrong_shapes_and_rogue_entities(self):
        seen = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _send(self, doc):
                body = json.dumps(doc).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == '/api/states':
                    return self._send(seen['doc'])
                return self._send({'message': 'ok'})

        srv = serve(H)
        try:
            cli = client_for(srv)
            seen['doc'] = {'not': 'a list'}
            with self.assertRaises(HA.HAError):
                cli.states()
            seen['doc'] = [None, 42, 'x', {}, {'entity_id': 'not an id!!'},
                           {'entity_id': 'camera.living'}, {'entity_id': 'person.me'},
                           {'entity_id': 'light.ok', 'state': 'on', 'attributes': {}}]
            rows = cli.states()
            self.assertEqual([r['entity_id'] for r in rows], ['light.ok'])   # rogue rows dropped, camera/person never listed
        finally:
            srv.shutdown()
            srv.server_close()

    def test_action_plan_survives_flapping_server(self):
        """A server that answers, dies, then answers: calls fail or succeed, never lie."""
        up = {'on': True}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _send(self, doc):
                body = json.dumps(doc).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if not up['on']:
                    self.close_connection = True
                    return
                if self.path == '/api/':
                    return self._send({'message': 'API running.'})
                return self._send([])

        srv = serve(H)
        try:
            cli = client_for(srv)
            self.assertTrue(cli.ping()['ok'])
            up['on'] = False
            with self.assertRaises(HA.HAError):
                cli.ping()
            up['on'] = True
            self.assertTrue(cli.ping()['ok'])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == '__main__':
    unittest.main()
