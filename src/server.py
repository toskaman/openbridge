"""Loopback-only demo server with explicit host/origin and CSRF boundaries."""
import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import os
import sqlite3
import queue
from datetime import datetime
from urllib.parse import urlsplit, parse_qs
from src.adapters.android import AndroidAdapter
from src.adapters.freebox import FreeboxAdapter
from src.adapters.simulated import discover
from src.core.policy import inspect_device
from src.ai.broker import RuntimeModelBroker, MetaTransport, CreditPermit, ModelBlocked
from src.core.transactions import TransactionEngine, TransactionBlocked
from src.adapters.simulated_setting import SimulatedSetting
from src.adapters.android_events import AndroidEventMonitor
from src.ai.local_meta import LocalMetaBroker
from src.core.agent import DeviceAgent, AgentBlocked
from src.ai import registry

UI = Path(__file__).parent / 'ui'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}


class LocalServer(ThreadingHTTPServer):
    def server_close(self):
        monitor=getattr(self,'android_events',None)
        if monitor is not None:monitor.close()
        super().server_close()


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
        if path == '/api/device-events':
            if parse_qs(urlsplit(self.path).query).get('source') != ['android']:
                return self.reply(400,{'error':'Explicit Android event source required'})
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.connection.settimeout(10)
            try:
                with self.server.android_events.subscribe() as subscription:
                    while True:
                        try:event=subscription.get(timeout=5)
                        except queue.Empty:
                            self.wfile.write(b': heartbeat\n\n');self.wfile.flush()
                            continue
                        if event.get('type')=='closed':break
                        self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())
                        self.wfile.flush()
            except (ConnectionError,TimeoutError,ValueError):pass
            return
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
            broker=self.server.model_broker
            local=broker is not None and getattr(broker,'local_only',False) is True
            available=broker is not None and (not local or broker.ready())
            return self.reply(200, {'cloud_inference_enabled': False,
                                   'supervised_session_configured': broker is not None and not local,
                                   'inference_available':available,'inference_mode':'local' if local else 'cloud' if broker else 'blocked',
                                   'model_id':broker.model_id if local else 'muse-spark-1.3',
                                   'status': 'LOCAL_META_READY' if local and available else 'LOCAL_META_UNAVAILABLE' if local else 'SUPERVISED_ONLY' if broker else 'CREDIT_VERIFICATION_REQUIRED',
                                   'detail': 'Automatic cloud calls disabled. Explicit supervised requests require fresh verified free credits.',
                                   'agent_enabled': self.server.agent is not None,
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
            if self.server.demo_engine is None or self.server.demo_engine.adapter.source != 'SIMULATED':
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
        if self.path not in ('/api/inspect', '/api/recommend', '/api/demo-transaction', '/api/agent-plan', '/api/agent-execute', '/api/agent-undo'):
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
                if self.server.demo_engine is None or self.server.demo_engine.adapter.source != 'SIMULATED':
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
            if self.path.startswith('/api/agent-'):
                agent=self.server.agent
                if agent is None:
                    return self.reply(409,{'error':'Physical agent disabled. Start with --local-meta --agent.'})
                if source!='android':
                    raise ValueError('Agent works on an authorized Android USB device only')
                try:
                    if self.path=='/api/agent-plan':
                        if not agent.broker.ready():
                            return self.reply(409,{'error':'Pinned local Meta model unavailable; no cloud fallback'})
                        goal=body.get('goal','review')
                        if goal not in ('review','declutter'):raise ValueError()
                        return self.reply(200,agent.plan(body['device_id'],goal))
                    plan_id=body.get('plan_id')
                    if not isinstance(plan_id,str):raise ValueError()
                    if self.path=='/api/agent-execute':
                        return self.reply(200,agent.execute(plan_id,body.get('consent')))
                    return self.reply(200,agent.undo(plan_id))
                except (AgentBlocked,ModelBlocked,TransactionBlocked) as error:
                    return self.reply(409,{'error':str(error)})
            if self.path == '/api/recommend':
                broker=self.server.model_broker
                local=broker is not None and getattr(broker,'local_only',False) is True
                if source=='android' and local:
                    if not broker.ready():
                        return self.reply(409,{'error':'Pinned local Meta model unavailable; no cloud fallback'})
                    report=self.server.android.inspect(body['device_id'])
                    facts={item['key']:item['value'] for item in report['evidence'] if item['key'] in ('battery_percent','storage_free_gb','screen_timeout_seconds')}
                    evidence_source='ADB'
                elif source=='demo' and body['device_id']=='demo-android':
                    facts=discover()[0]['facts'];evidence_source='SIMULATED'
                else:
                    raise ValueError('Physical facts may only use the explicitly enabled local Meta provider')
                if self.server.model_broker is None:
                    return self.reply(409, {'error': 'Supervised free-credit verification required; no model called'})
                try:
                    result = broker.recommend(facts,source=evidence_source) if local else broker.recommend(facts)
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


def create_server(port=18765, model_broker=None, demo_engine=None, agent_dir=None):
    server = LocalServer(('127.0.0.1', port), Handler)
    server.csrf_token = secrets.token_urlsafe(32)
    server.android = AndroidAdapter()
    server.android_events = AndroidEventMonitor(server.android)
    server.freebox = FreeboxAdapter()
    server.model_broker = model_broker
    server.demo_engine = demo_engine
    server.agent = DeviceAgent(model_broker,server.android,agent_dir) if agent_dir is not None and getattr(model_broker,'local_only',False) is True else None
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18765)
    parser.add_argument('--agent',action='store_true',help='Enable the consent-gated physical agent (requires --local-meta)')
    parser.add_argument('--local-meta',action='store_true',help='Use the pinned private CPU-local Meta model; never falls back to cloud')
    args = parser.parse_args()
    broker = None
    if args.local_meta:
        broker=LocalMetaBroker()
        registry.require(broker.model_id,broker.endpoint)
    elif os.environ.get('MODEL_API_KEY') and os.environ.get('OPENBRIDGE_CREDIT_VERIFIED_AT'):
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
    agent_dir=private_root/'agent' if args.agent and args.local_meta else None
    with create_server(args.port, model_broker=broker,demo_engine=demo_engine,agent_dir=agent_dir) as server:
        print(f'OpenBridge: http://127.0.0.1:{server.server_port} (SIMULATED; read-only)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
