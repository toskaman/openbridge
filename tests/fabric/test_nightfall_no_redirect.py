import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request

from src.adapters import upnp_igd
from src.adapters.freebox import NoRedirect as FreeboxNoRedirect
from src.ai.broker import ModelBlocked, NoRedirect as BrokerNoRedirect
from src.fabric.relay import RelayError, _opener


class _Redirect302(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'<?xml version="1.0"?><root>redirect body, not a reply</root>'
        self.send_response(302)
        self.send_header('Location', 'http://example.invalid/elsewhere')
        self.send_header('Content-Type', 'text/xml')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class NoRedirectTests(unittest.TestCase):
    """Pin redirect refusal across transports (N-24/B-19).

    urllib's HTTPRedirectHandler treats `redirect_request() -> None`
    as 'swallow the redirect and return the 302 body as the reply'.
    Returning None therefore processes a redirect page as gateway /
    provider data (upnp_igd even parses an XML 302 body as SOAP).
    Every transport must RAISE its structured error instead,
    mirroring src/fabric/relay._NoRedirect.
    """

    def test_upnp_redirect_request_raises(self):
        with self.assertRaises(upnp_igd.IGDBlocked):
            upnp_igd._NoRedirect().redirect_request(None, None, 302, 'Found', {}, 'http://x/')

    def test_upnp_http_refuses_redirect_end_to_end(self):
        server = HTTPServer(('127.0.0.1', 0), _Redirect302)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        url = 'http://127.0.0.1:%d/desc.xml' % server.server_port
        with self.assertRaisesRegex(upnp_igd.IGDBlocked, 'redirect'):
            upnp_igd._http(Request(url, method='GET'), 65536, 5)

    def test_broker_redirect_request_raises(self):
        with self.assertRaises(ModelBlocked):
            BrokerNoRedirect().redirect_request(None, None, 302, 'Found', {}, 'http://x/')

    def test_freebox_redirect_request_raises(self):
        with self.assertRaises(ValueError):
            FreeboxNoRedirect().redirect_request(None, None, 302, 'Found', {}, 'http://x/')

    def test_relay_redirect_request_raises_reference(self):
        opener = _opener()
        handler = next(h for h in opener.handlers if type(h).__name__ == '_NoRedirect')
        with self.assertRaises(RelayError):
            handler.redirect_request(None, None, 302, 'Found', {}, 'http://x/')


if __name__ == '__main__':
    unittest.main(verbosity=2)
