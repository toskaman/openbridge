"""Loopback-only demo server with explicit host/origin and CSRF boundaries."""
import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import os
import sqlite3
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from src.adapters.android import AndroidAdapter
from src.adapters.freebox import FreeboxAdapter
from src.adapters.simulated import discover
from src.core.policy import inspect_device
from src.ai.broker import RuntimeModelBroker, MetaTransport, CreditPermit, ModelBlocked
from src.core.transactions import TransactionEngine, TransactionBlocked
from src.adapters.simulated_setting import SimulatedSetting

UI = Path(__file__).parent / 'ui'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *_):
        pass  # Avoid recording request paths or identifiers.

    def reply(self, status, value, content_type='application/json'):
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def host_allowed(self):
        hosts = self.headers.get_all('Host', [])
        return len(hosts) == 1 and hosts[0] == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.host_allowed():
            return self.reply(403, {'error': 'Untrusted host'})
        path = urlsplit(self.path).path
        if path == '/api/session':
            return self.reply(200, {'csrf_token': self.server.csrf_token})
        if path == '/api/devices':
            source = parse_qs(urlsplit(self.path).query).get('source', ['demo'])
            if source == ['android']:
                return self.reply(200, self.server.android.discover())
            if source == ['freebox']:
                return self.reply(200, self.server.freebox.discover())
            if source != ['demo']:
                return self.reply(400, {'error': 'Unknown inventory source'})
            return self.reply(200, {'devices': discover(), 'status': 'SIMULATED'})
        if path == '/api/model-status':
            return self.reply(200, {'cloud_inference_enabled': False,
                                   'supervised_session_configured': self.server.model_broker is not None,
                                   'status': 'SUPERVISED_ONLY' if self.server.model_broker else 'CREDIT_VERIFICATION_REQUIRED',
                                   'detail': 'Automatic cloud calls disabled. Explicit supervised requests require fresh verified free credits.',
                                   'development_design_model': 'muse-spark-1.3'})
        if path == '/api/model-proof':
            try:
                receipt_path=UI.parents[1] / 'docs' / 'runtime-meta-receipt.json'
                if receipt_path.stat().st_size > 16384:
                    raise ValueError('Oversized proof')
                receipt=json.loads(receipt_path.read_text(encoding='utf-8-sig'))
                if receipt.get('model_id') != 'muse-spark-1.3' or receipt.get('source') != 'SIMULATED':
                    raise ValueError('Invalid proof identity')
                return self.reply(200, {'evidence_kind':'RECORDED_RUNTIME_CORE_CALL','live_request':False,'receipt':receipt})
            except (OSError,ValueError,AttributeError):
                return self.reply(404, {'error':'No verified recorded model proof available'})
        if path == '/api/demo-setting':
            if self.server.demo_engine is None:
                return self.reply(409, {'error':'Simulated transaction journal unavailable'})
            try:
                return self.reply(200,self.server.demo_engine.status())
            except (TransactionBlocked,OSError,sqlite3.Error):
                return self.reply(409,{'error':'Simulated transaction journal is busy or unavailable'})
        if path in ASSETS:
            filename, content_type = ASSETS[path]
            return self.reply(200, (UI / filename).read_bytes(), content_type)
        return self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        token = self.headers.get('X-CSRF-Token', '')
        if (not self.host_allowed() or self.headers.get_all('Origin', []) != [origin]
                or not hmac.compare_digest(token.encode(), self.server.csrf_token.encode())):
            return self.reply(403, {'error': 'Origin or CSRF check failed'})
        if self.path not in ('/api/inspect', '/api/recommend', '/api/demo-transaction'):
            return self.reply(404, {'error': 'Operation unavailable'})
        if self.headers.get('Content-Type') != 'application/json':
            return self.reply(415, {'error': 'JSON required'})
        try:
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            length = int(lengths[0])
            if length < 0:
                raise ValueError()
            if length > 8192:
                return self.reply(413, {'error': 'Request too large'})
            self.connection.settimeout(5)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or not isinstance(body.get('device_id'), str):
                raise ValueError()
            source = body.get('source', 'demo')
            if self.path == '/api/demo-transaction':
                if source != 'demo' or body['device_id'] != 'demo-android' or not isinstance(body.get('transaction_id'),str):
                    raise ValueError('Only the simulated sandbox supports transactions')
                if self.server.demo_engine is None:
                    return self.reply(409,{'error':'Simulated transaction journal unavailable'})
                try:
                    if body.get('operation')=='apply':
                        self.server.demo_engine.prepare(body['transaction_id'],body.get('target'),consent=body.get('consent'))
                        result=self.server.demo_engine.apply(body['transaction_id'])
                    elif body.get('operation')=='undo':
                        result=self.server.demo_engine.revert(body['transaction_id'])
                    else:
                        raise ValueError('Unknown simulated operation')
                    return self.reply(200,result)
                except TransactionBlocked as error:
                    return self.reply(409,{'error':str(error)})
                except (OSError,sqlite3.Error):
                    return self.reply(409,{'error':'Simulated journal unavailable; operation stopped'})
            if self.path == '/api/recommend':
                if source != 'demo' or body['device_id'] != 'demo-android':
                    raise ValueError('Only synthetic demo facts can be sent')
                if self.server.model_broker is None:
                    return self.reply(409, {'error': 'Supervised free-credit verification required; no model called'})
                try:
                    result = self.server.model_broker.recommend(discover()[0]['facts'])
                    return self.reply(200, result)
                except ModelBlocked as error:
                    return self.reply(409, {'error': str(error)})
            if source == 'android':
                result = self.server.android.inspect(body['device_id'])
            elif source == 'freebox':
                result = self.server.freebox.inspect(body['device_id'])
            elif source == 'demo':
                result = inspect_device(body['device_id'])
            else:
                raise ValueError('Unknown source')
        except (ValueError, UnicodeError, TimeoutError):
            return self.reply(400, {'error': 'Invalid request or unknown device'})
        return self.reply(200, result)


def create_server(port=18765, model_broker=None, demo_engine=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.csrf_token = secrets.token_urlsafe(32)
    server.android = AndroidAdapter()
    server.freebox = FreeboxAdapter()
    server.model_broker = model_broker
    server.demo_engine = demo_engine
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18765)
    args = parser.parse_args()
    broker = None
    if os.environ.get('MODEL_API_KEY') and os.environ.get('OPENBRIDGE_CREDIT_VERIFIED_AT'):
        try:
            permit = CreditPermit(os.environ['OPENBRIDGE_CREDIT_OBSERVATION_ID'],
                                  datetime.fromisoformat(os.environ['OPENBRIDGE_CREDIT_VERIFIED_AT']),
                                  float(os.environ['OPENBRIDGE_FREE_CREDITS_USD']), 0.20)
            private_root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
            broker = RuntimeModelBroker(private_root / 'runtime-budget.sqlite', permit, MetaTransport(os.environ['MODEL_API_KEY']))
        except (KeyError,ValueError):
            print('Supervised credit configuration invalid; runtime models disabled.', flush=True)
    private_root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
    demo_engine=None
    try:
        demo_engine=TransactionEngine(private_root/'simulated-transactions.sqlite',SimulatedSetting(private_root/'simulated-setting.sqlite'))
    except (TransactionBlocked,OSError,sqlite3.Error):
        print('Simulated transaction journal unavailable; read-only inventory remains available.',flush=True)
    with create_server(args.port, model_broker=broker,demo_engine=demo_engine) as server:
        print(f'OpenBridge: http://127.0.0.1:{server.server_port} (SIMULATED; read-only)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
