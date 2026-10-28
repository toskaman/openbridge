"""Loopback-only demo server with explicit host/origin and CSRF boundaries."""
import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
import subprocess
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
from src.ai.glimmer import GlimmerBroker
from src.core.agent import DeviceAgent, AgentBlocked
from src.ai import registry
from src.fabric import discovery as fabric_discovery
from src.fabric import relay as fabric_relay

UI = Path(__file__).parent / 'ui'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript'), '/shell.js': ('shell.js', 'text/javascript'), '/command_center.js': ('command_center.js', 'text/javascript')}


class LocalServer(ThreadingHTTPServer):
    def server_close(self):
        wb=getattr(self,'windows_bridge',None)
        if wb is not None:wb.close()
        monitor=getattr(self,'android_events',None)
        if monitor is not None:monitor.close()
        ex=getattr(self,'runtime_executor',None)
        if ex is not None and getattr(ex,'_watchers',None) is not None:ex._watchers.stop_all()   # session-scoped watches
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

    def v2_post(self):
        from src.runtime import api_v2
        if self.path not in api_v2.POST_ROUTES:
            return self.reply(404, {'error': 'Operation unavailable'})
        if self.headers.get('Content-Type') != 'application/json':
            return self.reply(415, {'error': 'JSON required'})
        try:
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1 or self.headers.get('Transfer-Encoding') or not 0 <= int(lengths[0]) <= (700_000 if self.path == '/api/v2/voice/transcribe' else 8192):
                raise ValueError()
            self.connection.settimeout(5)
            body = json.loads(self.rfile.read(int(lengths[0])))
        except (ValueError, OSError):
            return self.reply(400, {'error': 'Invalid request'})
        return self.reply(*api_v2.post(self.server, self.path, body))

    def host_allowed(self):
        hosts = self.headers.get_all('Host', [])
        return len(hosts) == 1 and hosts[0] == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.host_allowed():
            return self.reply(403, {'error': 'Untrusted host'})
        path = urlsplit(self.path).path
        if path.startswith('/api/v2/'):
            from src.runtime import api_v2
            return self.reply(*api_v2.get(self.server, path, urlsplit(self.path).query))
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
        if path == '/api/session-changes':
            return self.reply(200, {'changes': self.server.session_journal.open_changes()})
        if path == '/api/companion-install':
            return self.reply(200, dict(self.server.companion_install))
        if path == '/api/freebox-authorization':
            return self.reply(200, dict(self.server.freebox_auth))
        if path == '/api/fabric':
            snap=self.server.fabric_snapshot
            return self.reply(200, snap if snap else {'schema_version':1,'devices':[],'links':[],'possible_duplicates':[],'providers':{},'status':'NOT_RUN'})
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
        if self.path.startswith('/api/v2/'):
            return self.v2_post()
        if self.path not in ('/api/inspect', '/api/recommend', '/api/demo-transaction', '/api/agent-plan', '/api/agent-execute', '/api/agent-undo', '/api/agent-recover', '/api/fabric-discover', '/api/freebox-authorize', '/api/relay-pair-start', '/api/relay-pair-confirm', '/api/relay-scan', '/api/companion-install', '/api/fabric-advise', '/api/tv-adb-connect', '/api/session-restore', '/api/watch-pair'):
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
            if self.path == '/api/freebox-authorize':
                if body['device_id'] != 'freebox-local':
                    raise ValueError()
                return self.reply(*self.server.start_freebox_authorization())
            if self.path == '/api/session-restore':
                from src.fabric.session import restore
                ids = body.get('restore')
                if body['device_id'] != 'session' or not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                    raise ValueError()
                results = []
                for change in self.server.session_journal.open_changes():
                    if change['id'] in ids:
                        try:
                            state, detail = restore(change, self.server.android._run)
                        except (ValueError, OSError) as error:
                            state, detail = 'FAILED', str(error)[:120]
                        if state == 'MANUAL' and change['kind'] == 'freebox_app_authorized':
                            from src.fabric.credential_vault import Vault
                            Vault().delete('freebox-app-token')
                        if state != 'FAILED':
                            self.server.session_journal.close(change['id'], state, detail)
                    else:
                        state, detail = 'KEPT', 'Kept by the owner'
                        self.server.session_journal.close(change['id'], 'KEPT', detail)
                    results.append({'id': change['id'], 'title': change['title'], 'device': change['device'], 'state': state, 'detail': detail})
                return self.reply(200, {'results': results})
            if self.path == '/api/tv-adb-connect':
                from src.fabric.guidance import guide
                reg = self.server.fabric_registry
                dev = reg.devices.get(body['device_id']) if reg else None
                if dev is None or dev['category'] not in ('tv', 'media'):
                    return self.reply(409, {'error': 'Select a TV from the current discovery first'})
                ips = sorted({v for k, v in dev['weak'] if k == 'ip' and '.' in v})
                if not ips:
                    return self.reply(409, {'error': 'No local IPv4 address known for this TV'})
                manufacturer = (reg.best_value(dev['key'], 'manufacturer') or type('o', (), {'value': None})).value
                was_connected = any(f'{ips[0]}:5555' == k for k in self.server.android._handles)
                state = self.server.android.connect_network(ips[0])
                if state == 'AUTHORIZED' and not was_connected:
                    self.server.session_journal.record('adb_network_connected', dev['label'], {'address': f'{ips[0]}:5555'}, 'not connected', 'connected')
                issue = {'PORT_CLOSED': 'tv_network_debugging', 'WAITING_FOR_TV_APPROVAL': 'tv_debug_prompt', 'CONNECT_FAILED': 'tv_network_debugging'}.get(state)
                tried = [f'adb connect {ips[0]}:5555 -> {state}']
                return self.reply(200, {'state': state, 'guide': guide(issue, manufacturer=manufacturer or dev['label'], television=True, tried=tried) if issue else None})
            if self.path == '/api/watch-pair':
                from src.fabric.guidance import guide
                if body['device_id'] not in ('watch', 'android'):
                    raise ValueError()
                addr, code = str(body.get('address', '')), str(body.get('code', ''))
                m = __import__('re').fullmatch(r'(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})', addr.strip())
                if not m:
                    return self.reply(200, {'state': 'NEED_INPUT', 'guide': guide('watch_wireless_debugging', manufacturer=body.get('manufacturer'))})
                state, target = self.server.android.pair_wireless(m.group(1), int(m.group(2)), code.strip())
                if state == 'AUTHORIZED':
                    self.server.session_journal.record('adb_network_connected', 'Smartwatch' if body['device_id'] == 'watch' else 'Android device', {'address': target}, 'not connected', 'connected')
                issue = {'PAIR_FAILED': 'watch_pair_failed', 'PAIRED_NOT_ADVERTISED': 'watch_wireless_debugging', 'CONNECT_FAILED': 'watch_wireless_debugging'}.get(state)
                return self.reply(200, {'state': state, 'guide': guide(issue, manufacturer=body.get('manufacturer')) if issue else None})
            if self.path == '/api/fabric-advise':
                from src.fabric import advisor
                goal = body.get('goal')
                if body['device_id'] != 'fabric' or goal not in advisor.GOALS:
                    raise ValueError()
                snap = self.server.fabric_snapshot
                if not snap:
                    return self.reply(409, {'error': 'Run discovery first'})
                steps, _ = advisor.candidate_steps(snap)
                broker = self.server.model_broker
                rules = {'step': advisor.rule_choice(steps, goal) if steps else None, 'source': 'rules', 'candidates': [s['id'] for s in steps]}
                if broker is None or getattr(broker, 'local_only', False) is not True:
                    return self.reply(200, dict(rules, summary='Local Meta model not enabled; deterministic rule shown.'))
                if not broker.ready():
                    return self.reply(409, {'error': 'Pinned local Meta model unavailable; no cloud fallback'})
                try:
                    return self.reply(200, advisor.advise(broker, snap, goal))
                except ModelBlocked as error:
                    return self.reply(200, dict(rules, summary=f'Meta advice rejected by validation ({error}); deterministic rule shown.'))
            if self.path == '/api/companion-install':
                return self.reply(*self.server.start_companion_install(body['device_id']))
            if self.path.startswith('/api/relay-'):
                try:
                    return self.reply(200, self.server.relay_action(self.path, body))
                except (fabric_relay.RelayError, OSError, ValueError) as error:
                    return self.reply(409, {'error': str(error)[:160], 'guide': self.server.guide_for_error(str(error), body.get('device_id'))})
            if self.path == '/api/fabric-discover':
                if body['device_id'] != 'fabric':
                    raise ValueError()
                providers=body.get('providers',['mdns','ssdp','android','freebox','ble'])
                if not isinstance(providers,list) or not set(providers) <= {'mdns','ssdp','android','freebox','ble'}:
                    raise ValueError()
                if not self.server.fabric_lock.acquire(blocking=False):
                    return self.reply(409,{'error':'A discovery is already running'})
                try:
                    snap,_=fabric_discovery.run(self.server.fabric_adapters(tuple(providers)),self.server.fabric_salt,providers=tuple(providers))
                finally:
                    self.server.fabric_lock.release()
                self.server.fabric_snapshot=snap
                self.server.fabric_registry=_
                return self.reply(200,snap)
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
                    if self.path=='/api/agent-recover':
                        return self.reply(200,{'recovered':agent.recover(body['device_id'])})
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


def create_server(port=18765, model_broker=None, demo_engine=None, agent_dir=None, fabric_salt=None, session_journal=None):
    server = LocalServer(('127.0.0.1', port), Handler)
    server.csrf_token = secrets.token_urlsafe(32)
    server.android = AndroidAdapter()
    server.android_events = AndroidEventMonitor(server.android)
    server.freebox = FreeboxAdapter()
    server.model_broker = model_broker
    server.demo_engine = demo_engine
    server.fabric_snapshot = None
    from src.fabric.session import SessionJournal
    server.session_journal = session_journal or SessionJournal()
    server.fabric_lock = threading.Lock()
    server.fabric_salt = fabric_salt if fabric_salt is not None else fabric_discovery.install_salt()
    def fabric_adapters(providers=None):
        from src.adapters.freebox_auth import FreeboxSession
        from src.fabric.credential_vault import Vault
        session=None
        tuya=None
        try:
            from src.adapters.tuya_local import TuyaVacuum, owner_link
            link=owner_link()
            tuya=getattr(server,'tuya',None) or (TuyaVacuum(link) if link else None)
            server.tuya=tuya
        except (ImportError,PermissionError,ValueError):
            tuya=None
        if providers is not None and 'freebox' not in providers:   # never probe the gateway unless asked
            return {'android':server.android,'freebox':None,'windows':server.windows_bridge,'tuya':tuya}
        try:
            facts=server.freebox.discover()['devices'][0]['facts']
            session=FreeboxSession(Vault(),facts['api_version'].split('.')[0])
        except (IndexError,KeyError,ValueError):
            pass
        return {'android':server.android,'freebox':{'public':server.freebox,'session':session},'windows':server.windows_bridge,'tuya':tuya}
    server.fabric_adapters = fabric_adapters
    server.windows_bridge = None
    server.freebox_auth = {'state': 'IDLE'}
    def start_freebox_authorization(session_factory=None):
        if server.freebox_auth.get('state') == 'PENDING':
            return 409, {'error': 'Authorization already pending on the Freebox screen'}
        session = (session_factory or (lambda: fabric_adapters()['freebox']['session']))()
        if session is None:
            return 409, {'error': 'Freebox not reachable on this network'}
        if session.state() == 'AUTHORIZED':
            server.freebox_auth = {'state': 'GRANTED', 'detail': 'Already authorized'}
            return 200, server.freebox_auth
        try:
            session.request_authorization()
        except Exception as error:
            server.freebox_auth = {'state': 'FAILED', 'detail': str(error)[:120]}
            return 409, server.freebox_auth
        server.freebox_auth = {'state': 'PENDING', 'detail': 'Press the check mark on the Freebox front panel'}
        def poll():
            import time
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                try:
                    st = session.poll_authorization()
                except Exception as error:
                    server.freebox_auth = {'state': 'FAILED', 'detail': str(error)[:120]}; return
                if st in ('granted', 'denied', 'timeout'):
                    if st == 'granted':
                        server.session_journal.record('freebox_app_authorized', 'Freebox', {'app_id': 'fr.openbridge.devicefabric'}, 'not authorized', 'authorized (read-only)')
                    server.freebox_auth = {'state': st.upper()}; return
                time.sleep(2)
            server.freebox_auth = {'state': 'TIMEOUT'}
        threading.Thread(target=poll, daemon=True).start()
        return 202, server.freebox_auth
    server.start_freebox_authorization = start_freebox_authorization
    server.fabric_registry = None
    server.relays = fabric_relay.RelayManager(lambda relay, msg: relay['send'](relay, msg))
    from src.runtime.relay_health import RelayLedger
    server.relay_ledger = RelayLedger()
    server.relay_pending = {}          # device handle -> pairing in progress (isolated per device)
    server.relay_pending_lock = threading.Lock()
    PAIRING_TTL = 120                  # mirrors the Companion 2-minute code expiry
    def relay_action(path, body, transport_factory=fabric_relay.http_transport):
        import time
        if path == '/api/relay-pair-start':
            handle = body.get('device_id')
            if not isinstance(handle, str) or not handle:
                raise fabric_relay.RelayError('Unknown device handle')
            url = server.android.forward_companion(handle)
            send = transport_factory(url)
            pc_nonce = secrets.token_hex(16)
            hello = send(None, {'op': 'pair_request', 'pc_nonce': pc_nonce})
            if hello.get('protocol') != fabric_relay.PROTOCOL or not isinstance(hello.get('relay_nonce'), str):
                raise fabric_relay.RelayError('Not an OpenBridge Companion')
            with server.relay_pending_lock:
                now = time.monotonic()
                for h in [h for h, p in server.relay_pending.items() if now - p['started_at'] > PAIRING_TTL]:
                    del server.relay_pending[h]
                server.relay_pending[handle] = {'send': send, 'hello': hello, 'pc_nonce': pc_nonce, 'handle': handle, 'started_at': now}
            return {'state': 'CODE_SHOWN_ON_DEVICE', 'relay_id': hello['relay_id'], 'declared': hello.get('declared', {})}
        if path == '/api/relay-pair-confirm':
            handle = body.get('device_id')
            code = body.get('code')
            if not isinstance(handle, str) or not handle or not isinstance(code, str):
                raise fabric_relay.RelayError('No pairing in progress for this device')
            with server.relay_pending_lock:
                pending = server.relay_pending.get(handle)
                if pending is None:
                    raise fabric_relay.RelayError('No pairing in progress for this device')
                if time.monotonic() - pending['started_at'] > PAIRING_TTL:
                    del server.relay_pending[handle]
                    raise fabric_relay.RelayError('Pairing code expired; start pairing again')
            key = fabric_relay.derive_key(code, pending['hello']['relay_nonce'], pending['pc_nonce'])
            rid = pending['hello']['relay_id']
            reply = pending['send'](None, fabric_relay.command(key, rid, 'discover_capabilities'))
            declared = fabric_relay.verify(key, reply, None).get('params', {})
            server.relays.enroll(rid, key, pending['handle'], declared)
            server.relays.relays[rid]['send'] = pending['send']
            server.relay_ledger.proved(rid)
            with server.relay_pending_lock:
                server.relay_pending.pop(handle, None)
            return {'state': 'PAIRED', 'relay_id': rid, 'declared': declared, 'eligible_for_ble': rid in server.relays.eligible('ble_scan')}
        if path == '/api/relay-scan':
            rid = body.get('relay_id')
            relay = server.relays.relays.get(rid)
            if relay is None:
                raise fabric_relay.RelayError('Unknown relay')
            try:
                status = fabric_relay.verify(relay['key'], relay['send'](relay, fabric_relay.command(relay['key'], rid, 'get_status')), relay['seen']).get('params', {})
            except (OSError, TimeoutError) as error:
                relay['online'] = False          # Companion stopped or unreachable: its routes go link_down until it answers again
                relay['failures'] = relay.get('failures', 0) + 1
                server.relay_ledger.failure(rid)
                raise fabric_relay.RelayError(f'Relay unreachable: {type(error).__name__}; open the Companion app on the device and retry') from None
            relay['online'] = True               # a signed status reply is the read-back that brings a relay back
            server.relay_ledger.proved(rid)
            relay['permissions'] = dict(status.get('permissions', {}))
            rid, observations = server.relays.scan(int(body.get('seconds', 8)), relay_id=rid)
            server.relay_ledger.record(rid, observations)
            registry = server.fabric_registry
            if registry is None:
                raise fabric_relay.RelayError('Run discovery first so the relay device is in the graph')
            observer = next((k for k, d in registry.devices.items() if relay['device_key'] in d.get('handles', {}).values()), None)
            if observer is None:
                raise fabric_relay.RelayError('Relay device not found in the current graph')
            fabric_discovery.ingest_ble(registry, {'devices': observations}, server.fabric_salt, observer=observer, source='RELAY:' + rid)
            caps = registry.devices[observer]['capabilities']
            for k in [k for k in caps if k[0] == 'ble_relay']:
                del caps[k]      # the proven relay replaces the earlier 'requires Companion' entry
            registry.capability(observer, __import__('src.fabric.contracts', fromlist=['Capability']).Capability('ble_relay', 'observe', 'REAL_HARDWARE_VERIFIED', 'RELAY:' + rid, f'{len(observations)} advertisers reported'))
            snap = registry.snapshot(); snap['providers'] = dict((server.fabric_snapshot or {}).get('providers', {}), relay={'status': 'OK', 'devices': len(observations)})
            server.fabric_snapshot = snap
            return snap
        raise ValueError()
    server.relay_action = relay_action
    def device_profile(handle):
        reg = server.fabric_registry
        if reg is None:
            return {}
        for key, dev in reg.devices.items():
            if handle in dev.get('handles', {}).values():
                val = lambda f: (reg.best_value(key, f).value if reg.best_value(key, f) else None)
                sdk = val('sdk')
                return {'manufacturer': val('manufacturer'), 'sdk': int(sdk) if str(sdk).isdigit() else None, 'television': bool(val('is_television'))}
        return {}
    def guide_for_error(message, handle=None):
        from src.fabric.guidance import guide
        m = message.lower()
        issue = ('companion_not_running' if ('refused' in m and 'relay' not in m) or 'connection' in m or 'not an openbridge' in m or 'unreachable' in m else
                 'bluetooth_service_disabled' if 'system bluetooth app is disabled' in m else
                 'bluetooth_off' if 'bluetooth is off' in m else 'ble_permission' if 'permission not granted' in m else
                 'owner_scan_disabled' if 'owner has not enabled' in m or 'lacks permission' in m else None)
        return guide(issue, tried=[message[:120]], **device_profile(handle)) if issue else None
    server.guide_for_error = guide_for_error
    server.companion_install = {'state': 'IDLE'}
    server.companion_apk = Path(os.environ.get('OPENBRIDGE_COMPANION_APK', 'artifacts/companion/openbridge-companion.apk'))
    def start_companion_install(handle, attempts=40, delay=15):
        from src.fabric.guidance import classify_install, guide
        if server.companion_install.get('state') == 'RETRYING':
            return 409, {'error': 'Installation already in progress'}
        if not server.companion_apk.exists():
            return 409, {'error': 'Companion APK not built. Run: python -m dev.build_companion'}
        serial0 = next((k for k, v in server.android._handles.items() if v == handle), None)
        try:
            was_installed = bool(serial0) and 'package:fr.openbridge.companion' in server.android._run(['-s', serial0, 'shell', 'pm', 'list', 'packages', 'fr.openbridge.companion']).split()
        except (ValueError, OSError):
            was_installed = False
        def worker():
            import time
            for attempt in range(attempts):
                try:
                    code, issue = classify_install(server.android.install_companion(handle, server.companion_apk))
                except (ValueError, OSError, subprocess.SubprocessError):
                    code, issue = 'DEVICE_UNAVAILABLE', 'usb_authorization_pending'
                if code == 'SUCCESS':
                    serial = next((k for k, v in server.android._handles.items() if v == handle), None)
                    if serial and not was_installed:
                        server.session_journal.record('companion_installed', handle, {'serial': serial}, 'not installed', 'installed')
                    server.companion_install = {'state': 'INSTALLED', 'attempts': attempt + 1}; return
                g = guide(issue, tried=[f'adb install attempt {attempt + 1}: {code}'], **device_profile(handle)) if issue else None
                server.companion_install = {'state': 'RETRYING' if issue else 'FAILED', 'code': code, 'attempts': attempt + 1, 'guide': g}
                if not issue:
                    return
                time.sleep(delay)
            server.companion_install = dict(server.companion_install, state='GAVE_UP')
        server.companion_install = {'state': 'RETRYING', 'attempts': 0}
        threading.Thread(target=worker, daemon=True).start()
        return 202, server.companion_install
    server.start_companion_install = start_companion_install
    server.agent = DeviceAgent(model_broker,server.android,agent_dir) if agent_dir is not None and getattr(model_broker,'local_only',False) is True else None
    return server


def start_windows_bridge(port=9876):
    from src.adapters.windows_bridge import WindowsBridge
    from src.fabric.credential_vault import Vault
    from src.fabric.mdns import lan_interface_ip, default_scope
    psk=None
    try:
        psk=Vault().get('windows-bridge-psk')
    except Exception:
        pass
    psk=psk or os.environ.get('OPENBRIDGE_WINDOWS_PSK')
    return WindowsBridge(psk, lan_interface_ip(default_scope()), port).start()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18765)
    parser.add_argument('--glimmer',action='store_true',help='With --local-meta: use pinned Meta Muse Glimmer (open weights, local GPU/CPU) instead of Llama 3.2 3B')
    parser.add_argument('--agent',action='store_true',help='Enable the consent-gated physical agent (requires --local-meta)')
    parser.add_argument('--windows-bridge',action='store_true',help='Accept one BridgeWindows agent on the LAN interface (read-only allowlist). Key: vault entry windows-bridge-psk or OPENBRIDGE_WINDOWS_PSK')
    parser.add_argument('--local-meta',action='store_true',help='Use the pinned private CPU-local Meta model; never falls back to cloud')
    args = parser.parse_args()
    broker = None
    if args.local_meta:
        broker=GlimmerBroker() if args.glimmer else LocalMetaBroker()
        registry.require(broker.model_id,broker.endpoint)
    elif os.environ.get('OPENBRIDGE_CREDIT_VERIFIED_AT'):
        try:
            api_key = os.environ.get('MODEL_API_KEY')
            if not api_key:
                from src.fabric.credential_vault import Vault
                api_key = Vault().get('meta-api-key')        # owner stores it in the OS vault
            if not api_key:
                raise KeyError('no Meta API key in env or vault')
            permit = CreditPermit(os.environ['OPENBRIDGE_CREDIT_OBSERVATION_ID'],
                                  datetime.fromisoformat(os.environ['OPENBRIDGE_CREDIT_VERIFIED_AT']),
                                  float(os.environ['OPENBRIDGE_FREE_CREDITS_USD']), 0.20)
            private_root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
            broker = RuntimeModelBroker(private_root / 'runtime-budget.sqlite', permit, MetaTransport(api_key))
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
        if args.windows_bridge:
            server.windows_bridge=start_windows_bridge()
        print(f'OpenBridge: http://127.0.0.1:{server.server_port} (SIMULATED; read-only)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
