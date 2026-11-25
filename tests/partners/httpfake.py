"""Shared loopback HTTP fakes for partner-adapter tests (stdlib only).

`serve(handler)` starts a ThreadingHTTPServer on 127.0.0.1 with an ephemeral port and returns it;
the caller shuts it down in a finally. `json_handler(routes)` builds a handler from
{(method, path): (code, doc) | callable} for the common static/dynamic JSON case.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve(handler):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _read_body(self):
        ln = int(self.headers.get('Content-Length') or 0)
        # Always drain the body before answering: answering a POST with an unread body aborts
        # the connection on some stacks (the client then sees a reset instead of the reply).
        return self.rfile.read(ln) if ln else b''

    def _send_json(self, doc, code=200, headers=()):
        raw = json.dumps(doc).encode()
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_raw(self, raw, code=200, ctype='text/plain'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def json_handler(routes):
    """A Quiet handler serving {(method, path): (code, doc)} or {(method, path): fn(handler) -> None}."""
    class H(Quiet):
        def _route(self, method):
            route = routes.get((method, self.path))
            body = self._read_body()
            if route is None:
                return self._send_json({}, 404)
            if callable(route):
                return route(self, body)
            code, doc = route
            return self._send_json(doc, code)

        def do_GET(self):
            self._route('GET')

        def do_POST(self):
            self._route('POST')

        def do_PUT(self):
            self._route('PUT')

        def do_DELETE(self):
            self._route('DELETE')

    return H
