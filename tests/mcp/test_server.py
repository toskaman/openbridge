"""Raw-protocol tests for the read-only OpenBridge MCP server (stdio, no MCP SDK needed)."""
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from src.fabric import discovery
from src.fabric.registry import Registry
from src.fabric.session import SessionJournal
from src.mcp import server as mcp
from src.server import create_server


def live_base(test, with_graph=True):
    s = create_server(0, fabric_salt=b'x', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
    if with_graph:
        reg = Registry()
        obs = [{'address': 'C0:00:00:00:00:01', 'address_kind': 'static_random', 'rssi': -61, 'name': '', 'company_ids': [], 'service_uuids': []}]
        with mock.patch('src.fabric.discovery.now', return_value='2026-10-27T00:00:00+00:00'):
            discovery.ingest_ble(reg, {'devices': obs}, b'x', observer='pc', source='RELAY:r1')
        s.fabric_registry, s.fabric_snapshot = reg, reg.snapshot()
    threading.Thread(target=s.serve_forever, daemon=True).start()
    test.addCleanup(lambda: (s.shutdown(), s.server_close()))
    return f'http://127.0.0.1:{s.server_port}'


def call(base, method, params=None, mid=1):
    msg = {'jsonrpc': '2.0', 'id': mid, 'method': method}
    if params is not None:
        msg['params'] = params
    return mcp.handle_message(base, msg)


class ProtocolTests(unittest.TestCase):
    def test_initialize_negotiates_version(self):
        r = call('http://127.0.0.1:9', 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '0'}})
        self.assertEqual(r['result']['protocolVersion'], '2025-06-18')
        self.assertEqual(r['result']['serverInfo']['name'], 'openbridge-mcp')
        r = call('http://127.0.0.1:9', 'initialize', {'protocolVersion': '2099-01-01', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '0'}})
        self.assertIn(r['result']['protocolVersion'], mcp.SUPPORTED_PROTOCOL_VERSIONS)

    def test_tools_list_advertises_read_only_tools(self):
        r = call('http://127.0.0.1:9', 'tools/list')
        names = {t['name'] for t in r['result']['tools']}
        self.assertEqual(names, {'openbridge_get_graph', 'openbridge_get_capabilities', 'openbridge_get_facts'})
        for t in r['result']['tools']:
            self.assertTrue(t['annotations']['readOnlyHint']); self.assertFalse(t['annotations']['destructiveHint'])
            self.assertIn('inputSchema', t)

    def test_call_facts_round_trips_live_read_model(self):
        base = live_base(self)
        r = call(base, 'tools/call', {'name': 'openbridge_get_graph', 'arguments': {}})
        key = json.loads(r['result']['content'][0]['text'])['devices'][0]['device_key']
        r = call(base, 'tools/call', {'name': 'openbridge_get_facts', 'arguments': {'device': key}})
        body = json.loads(r['result']['content'][0]['text'])
        self.assertEqual(body['device'], key); self.assertTrue(body['facts'])
        self.assertNotIn('isError', r['result'])

    def test_call_without_graph_returns_actionable_tool_error(self):
        base = live_base(self, with_graph=False)
        r = call(base, 'tools/call', {'name': 'openbridge_get_graph', 'arguments': {}})
        self.assertTrue(r['result']['isError'])
        self.assertIn('discovery', r['result']['content'][0]['text'].lower())

    def test_unreachable_server_returns_actionable_tool_error(self):
        r = call('http://127.0.0.1:9', 'tools/call', {'name': 'openbridge_get_graph', 'arguments': {}})
        self.assertTrue(r['result']['isError'])
        self.assertIn('127.0.0.1:9', r['result']['content'][0]['text'])

    def test_unknown_method_tool_and_args_fail_closed(self):
        base = live_base(self)
        self.assertEqual(call(base, 'tools/evil')['error']['code'], -32601)
        self.assertTrue(call(base, 'tools/call', {'name': 'nope', 'arguments': {}})['result']['isError'])
        self.assertTrue(call(base, 'tools/call', {'name': 'openbridge_get_facts', 'arguments': {'device': 123}})['result']['isError'])
        self.assertTrue(call(base, 'tools/call', {'name': 'openbridge_get_facts', 'arguments': {'device': 'x', 'cmd': 'rm'}})['result']['isError'])
        self.assertIsNone(mcp.handle_message(base, {'jsonrpc': '2.0', 'method': 'notifications/initialized'}))

    def test_stdio_loop_skips_blanks_and_bounds_lines(self):
        stdin = io.StringIO('\n' + json.dumps({'jsonrpc': '2.0', 'id': 7, 'method': 'ping'}) + '\n')
        stdout = io.StringIO()
        mcp.serve('http://127.0.0.1:9', stdin=stdin, stdout=stdout)
        lines = [l for l in stdout.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])['id'], 7)
        out = io.StringIO()
        mcp.serve('http://127.0.0.1:9', stdin=io.StringIO('x' * (mcp.MAX_LINE + 10) + '\n'), stdout=out)
        self.assertEqual(json.loads(out.getvalue().splitlines()[0])['error']['code'], -32700)

    def test_subprocess_stdio_end_to_end(self):
        base = live_base(self)
        root = Path(__file__).resolve().parents[2]
        proc = subprocess.Popen([sys.executable, '-m', 'src.mcp.server', '--base-url', base], cwd=root,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        payload = '\n'.join([json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                                          'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '0'}}}),
                             json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}),
                             json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}),
                             json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                         'params': {'name': 'openbridge_get_graph', 'arguments': {}}})]) + '\n'
        try:
            out, _ = proc.communicate(payload, timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill(); raise
        replies = [json.loads(l) for l in out.splitlines() if l.strip()]
        self.assertEqual([r.get('id') for r in replies], [1, 2, 3])
        self.assertEqual(replies[0]['result']['serverInfo']['name'], 'openbridge-mcp')
        self.assertTrue(json.loads(replies[2]['result']['content'][0]['text'])['devices'])


class Hardening(unittest.TestCase):
    def test_loopback_only_and_redacted_labels(self):
        from src.mcp import server as m
        self.assertEqual(m.loopback_only('http://127.0.0.1:18765/'), 'http://127.0.0.1:18765')
        for bad in ('http://192.168.1.5:18765', 'https://127.0.0.1:1', 'http://example.org'):
            with self.assertRaises(SystemExit):
                m.loopback_only(bad)
        body = m.redact_graph({'devices': [{'key': 'a', 'category': 'tv', 'label': "Marie's TV"}, {'key': 'b', 'category': 'tv', 'label': 'Salon'}]})
        self.assertEqual([d['label'] for d in body['devices']], ['tv 1', 'tv 2'])


class RedirectConfinement(unittest.TestCase):
    """Codex B1 review: a validated loopback URL must not redirect the MCP client to any other destination."""
    def _server(self, handler):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                handler(self)
            def log_message(self, *a):
                pass
        s = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (s.shutdown(), s.server_close()))
        return s

    def test_redirect_is_never_followed(self):
        hits = []
        def target(h):
            hits.append(h.path)
            h.send_response(200); h.send_header('Content-Type', 'application/json'); h.end_headers(); h.wfile.write(b'{"devices": []}')
        dest = self._server(target)
        for code in (301, 302, 303, 307, 308):
            def redirector(h, code=code):
                h.send_response(code); h.send_header('Location', f'http://127.0.0.1:{dest.server_port}/api/v2/graph'); h.end_headers()
            src = self._server(redirector)
            reply = call(f'http://127.0.0.1:{src.server_port}', 'tools/call', {'name': 'openbridge_get_graph', 'arguments': {}})
            self.assertTrue(reply['result'].get('isError'), code)
            self.assertIn('redirect', reply['result']['content'][0]['text'].lower())
        self.assertEqual(hits, [])                        # no request ever reached the redirect destination

    def test_base_url_rejects_credentials_path_query_fragment(self):
        for bad in ('http://user:pw@127.0.0.1:18765', 'http://127.0.0.1:18765/api', 'http://127.0.0.1:18765/?x=1',
                    'http://127.0.0.1:18765/#f', 'http://127.0.0.1:notaport', 'http://127.0.0.1.evil.example:18765'):
            with self.assertRaises(SystemExit, msg=bad):
                mcp.loopback_only(bad)
        self.assertEqual(mcp.loopback_only('http://localhost:18765'), 'http://localhost:18765')
