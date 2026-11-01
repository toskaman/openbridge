"""Campaign One §3.6: HTTP hardening regression tests.

Covers (1) dict-header tolerance in host_allowed (full-suite noise was
`AttributeError: 'dict' object has no attribute 'get_all'` from the HTTP/0.9
path, which hands handlers a plain dict), (2) request size caps, and
(3) pinned slow-client / oversize-header behavior.
"""
import contextlib
import http.client
import io
import json
import socket
import tempfile
import threading
import time
import unittest
from email.message import Message
from types import SimpleNamespace

from src.fabric.session import SessionJournal
from src.runtime import api_v2
from src.server import Handler, MAX_URL_BYTES, _header_all, _header_one, create_server


def raw_exchange(port, payload, read_timeout=10):
    """Send raw bytes, read until the server closes or the read times out."""
    sock = socket.create_connection(('127.0.0.1', port), timeout=read_timeout)
    try:
        sock.sendall(payload)
        sock.settimeout(read_timeout)
        chunks = []
        while True:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)
        return b''.join(chunks)
    finally:
        sock.close()


def status_of(response):
    return int(response.split(b'\r\n', 1)[0].split()[1])


def handler_with(headers, port=18765):
    handler = object.__new__(Handler)
    handler.headers = headers
    handler.server = SimpleNamespace(server_port=port)
    return handler


class HeaderHelperTests(unittest.TestCase):
    def test_dict_headers_never_raise_and_fail_closed(self):
        exact = '127.0.0.1:18765'
        self.assertTrue(handler_with({'Host': exact}).host_allowed())
        self.assertTrue(handler_with({'host': exact}).host_allowed())   # case-insensitive
        self.assertTrue(handler_with({'HOST': exact}).host_allowed())
        self.assertFalse(handler_with({}).host_allowed())               # HTTP/0.9 shape
        self.assertFalse(handler_with({'Host': 'attacker.example'}).host_allowed())
        self.assertFalse(handler_with(None).host_allowed())

    def test_message_headers_keep_single_host_rule(self):
        exact = '127.0.0.1:18765'
        single = Message()
        single['Host'] = exact
        self.assertTrue(handler_with(single).host_allowed())
        missing = Message()
        self.assertFalse(handler_with(missing).host_allowed())
        dup = Message()
        dup['Host'] = exact
        dup['Host'] = exact
        self.assertFalse(handler_with(dup).host_allowed())              # duplicate Host still rejected

    def test_header_helpers(self):
        msg = Message()
        msg['X-Multi'] = 'a'
        msg['X-Multi'] = 'b'
        self.assertEqual(_header_all(msg, 'x-multi'), ['a', 'b'])
        self.assertEqual(_header_all(msg, 'absent'), [])
        self.assertEqual(_header_one(msg, 'X-Multi'), 'a')
        self.assertEqual(_header_one(msg, 'absent', 'dflt'), 'dflt')
        self.assertEqual(_header_all({'Content-Type': 'application/json'}, 'content-type'), ['application/json'])
        self.assertEqual(_header_one({}, 'Host', ''), '')
        self.assertEqual(_header_all(None, 'Host'), [])


class ApiV2QueryCapTests(unittest.TestCase):
    def test_oversized_query_returns_414(self):
        status, body = api_v2.get(SimpleNamespace(), '/api/v2/contract', 'a=' + 'x' * 9000)
        self.assertEqual(status, 414)
        self.assertIn('error', body)

    def test_query_field_flood_returns_400(self):
        flood = '&'.join('f%d=%d' % (i, i) for i in range(500))
        status, body = api_v2.get(SimpleNamespace(), '/api/v2/contract', flood)
        self.assertEqual(status, 400)
        self.assertIn('error', body)

    def test_normal_query_unaffected(self):
        server = create_server(0, fabric_salt=b'f90-http-cap',
                               session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        try:
            status, body = api_v2.get(server, '/api/v2/contract', '')
            self.assertEqual(status, 200)
            self.assertIn('version', body)
        finally:
            server.server_close()


class LiveHttpHardenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.server = create_server(0, fabric_salt=b'f90-http-test',
                                   session_journal=SessionJournal(cls._tmp.name + '/s.json'))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port
        cls.origin = 'http://127.0.0.1:%d' % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls._tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, response.read()
        conn.close()
        return result

    def session_headers(self):
        code, body = self.request('GET', '/api/session')
        self.assertEqual(code, 200)
        return {'Origin': self.origin, 'X-CSRF-Token': json.loads(body)['csrf_token'],
                'Content-Type': 'application/json'}

    def raw(self, payload, read_timeout=10):
        return raw_exchange(self.port, payload, read_timeout)

    # -- backward compatibility smoke ------------------------------------
    def test_normal_get_and_post_still_work(self):
        self.assertEqual(self.request('GET', '/api/session')[0], 200)
        code, body = self.request('POST', '/api/inspect', '{"device_id":"demo-android"}',
                                  self.session_headers())
        self.assertEqual(code, 200)
        self.assertIn('model_status', json.loads(body))

    # -- (1) dict-header tolerance over the wire --------------------------
    def test_versionless_request_fails_closed_without_attribute_error(self):
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            response = self.raw(b'GET /api/session\r\n', read_timeout=10)
            time.sleep(0.5)   # let the handler thread finish before asserting quiet
        # stdlib answers HTTP/0.9 with a body-only reply: fail-closed 403 JSON, no status line.
        self.assertEqual(response, b'{"error": "Untrusted host"}')
        self.assertNotIn('AttributeError', captured.getvalue())
        self.assertNotIn('Traceback', captured.getvalue())

    # -- (2) request size caps --------------------------------------------
    def test_v2_oversize_body_returns_413(self):
        code, _ = self.request('POST', '/api/v2/execute', 'x' * 9000, self.session_headers())
        self.assertEqual(code, 413)

    def test_v2_body_at_cap_is_not_413(self):
        code, _ = self.request('POST', '/api/v2/execute', 'x' * 8192, self.session_headers())
        self.assertEqual(code, 400)   # invalid JSON, but the size itself is accepted

    def test_v2_manifest_route_keeps_larger_cap(self):
        headers = self.session_headers()
        code, _ = self.request('POST', '/api/v2/manifests/compile', 'x' * 60000, headers)
        self.assertEqual(code, 400)   # over 8192 yet under the 64 KiB plan cap: size accepted
        code, _ = self.request('POST', '/api/v2/manifests/compile', 'x' * 70000, headers)
        self.assertEqual(code, 413)

    def test_oversized_url_returns_414(self):
        self.assertEqual(self.request('GET', '/' + 'x' * 9000)[0], 414)
        self.assertEqual(self.request('GET', '/' + 'x' * (MAX_URL_BYTES + 1))[0], 414)

    def test_query_field_flood_rejected(self):
        flood = '&'.join('f%d=%d' % (i, i) for i in range(150))
        self.assertEqual(self.request('GET', '/api/devices?' + flood)[0], 400)
        self.assertEqual(self.request('GET', '/api/device-events?' + flood)[0], 400)
        self.assertEqual(self.request('GET', '/api/v2/contract?' + flood)[0], 400)

    def test_duplicate_content_length_and_transfer_encoding_rejected(self):
        token = self.session_headers()['X-CSRF-Token']
        body = b'{"device_id":"demo-android"}'
        base = ('POST /api/inspect HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nOrigin: %s\r\n'
                'X-CSRF-Token: %s\r\nContent-Type: application/json\r\n' % (self.port, self.origin, token))
        dup = (base + 'Content-Length: %d\r\nContent-Length: %d\r\n\r\n' % (len(body), len(body))).encode() + body
        self.assertEqual(status_of(self.raw(dup)), 400)
        te = (base + 'Content-Length: %d\r\nTransfer-Encoding: chunked\r\n\r\n' % len(body)).encode() + body
        self.assertEqual(status_of(self.raw(te)), 400)

    # -- (3) slow-client / oversize-header pins -----------------------------
    def test_oversize_header_line_returns_431(self):
        payload = ('GET /api/session HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Big: %s\r\n\r\n'
                   % (self.port, 'x' * 70000)).encode()
        self.assertEqual(status_of(self.raw(payload)), 431)

    def test_too_many_headers_returns_431(self):
        lines = ''.join('X-Pad-%d: v\r\n' % i for i in range(150))
        payload = ('GET /api/session HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n%s\r\n'
                   % (self.port, lines)).encode()
        self.assertEqual(status_of(self.raw(payload)), 431)

    def test_slow_client_is_dropped_and_server_stays_healthy(self):
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=20)
        try:
            sock.sendall(('GET /api/session HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nX-Drip: partial'
                          % self.port).encode())
            sock.settimeout(20)
            start = time.monotonic()
            chunks = []
            while True:
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    break
                if not data:
                    break
                chunks.append(data)
            elapsed = time.monotonic() - start
        finally:
            sock.close()
        self.assertEqual(b''.join(chunks), b'')   # headers never completed: no response, just a close
        self.assertLess(elapsed, 15)              # HEADER_TIMEOUT_S bounds the wait
        self.assertGreaterEqual(elapsed, 2.5)     # ...but the server actually waited for the client
        self.assertEqual(self.request('GET', '/api/session')[0], 200)


if __name__ == '__main__':
    unittest.main()
