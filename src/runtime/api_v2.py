"""/api/v2: versioned, local-only read model + single execute endpoint (contract v1).
No route accepts commands, shell strings, packages or addresses: writes are primitives run by the Executor."""
from urllib.parse import parse_qs

from src.runtime import capabilities, contract
from src.runtime.primitives import PRIMITIVES, Executor
from src.runtime.contract import to_json, DeviceIdentity, RelayRoute, EvidenceFact

GET_ROUTES = ('/api/v2/contract', '/api/v2/skills', '/api/v2/skill_routes',
              '/api/v2/graph',
              '/api/v2/capabilities',
              '/api/v2/facts',
              '/api/v2/routes',
              '/api/v2/primitives',
              '/api/v2/recovery',
              '/api/v2/events',
              '/api/v2/relays',
              '/api/v2/diagnosis',
              '/api/v2/watches',
              '/api/v2/timeline',
              '/api/v2/hypotheses',
              '/api/v2/relays/samples',
              '/api/v2/catalog',
              '/api/v2/onboarding')
POST_ROUTES = ('/api/v2/skill_policy', '/api/v2/skill_arm', '/api/v2/skill_invoke', '/api/v2/onboarding/apk-portal', '/api/v2/execute', '/api/v2/recovery/acknowledge', '/api/v2/cloud/preview', '/api/v2/cloud/confirm', '/api/v2/voice/intent', '/api/v2/voice/transcribe',)


def router(server):
    if getattr(server, 'skill_router', None) is None:
        from src.runtime.routing import Router
        server.skill_router = Router(server)
    return server.skill_router


def executor(server):
    if getattr(server, 'runtime_executor', None) is None:
        server.runtime_executor = Executor(server)
    return server.runtime_executor


def _relay_permissions(server):
    out = {}
    reg = server.fabric_registry
    if reg is None:
        return out
    for rid, r in server.relays.relays.items():
        key = next((k for k, d in reg.devices.items() if r['device_key'] in d.get('handles', {}).values()), None)
        if key:
            out[key] = {'BLUETOOTH_SCAN': r['permissions'].get('BLUETOOTH_SCAN') is True, 'owner_enabled': r['permissions'].get('owner_enabled') is True}
    return out


def routes(server):
    reg = server.fabric_registry
    out = []
    for rid, r in server.relays.relays.items():
        key = next((k for k, d in (reg.devices.items() if reg else ()) if r['device_key'] in d.get('handles', {}).values()), '')
        led = getattr(server, 'relay_ledger', None)
        last = (led.routes.get(rid) or {}).get('last_success_at') if led else None
        out.append(RelayRoute('*', key, rid, 'ble', r['permissions'].get('BLUETOOTH_SCAN') is True,
                              r['permissions'].get('owner_enabled') is True, bool(r['online']), last))
    return out


def route_rows(server):
    led = getattr(server, 'relay_ledger', None)
    return [dict(to_json(r), status=led.route_status(r.relay_id, r.online) if led else 'UNKNOWN') for r in routes(server)]


def get(server, path, query):
    q = parse_qs(query)
    ex = executor(server)
    if path == '/api/v2/contract':
        return 200, {'version': contract.CONTRACT_VERSION, 'schema': contract.schema()}
    if path == '/api/v2/primitives':
        return 200, {'primitives': [to_json(p) for p in PRIMITIVES.values()]}
    if path == '/api/v2/recovery':
        return 200, to_json(ex.recovery())
    if path == '/api/v2/events':
        try:
            since = int((q.get('since') or ['0'])[0])
        except ValueError:
            return 400, {'error': 'since must be an integer'}
        return 200, {'events': ex.events_since(since)}
    if path == '/api/v2/skills':
        from src.runtime.routing import SKILLS
        return 200, {'skills': [{'skill_id': k, 'plain': v['plain'], 'targeted': v['targeted'], 'reversibility': v['reversibility'],
                                 'consent': v['consent'], 'input': v['input'], 'policy': router(server).policy(k)} for k, v in SKILLS.items()]}
    if path == '/api/v2/skill_routes':
        from src.runtime.routing import RouteError
        try:
            return 200, router(server).skill_routes((q.get('skill') or [''])[0], (q.get('target') or [None])[0])
        except RouteError as e:
            return e.status, {'error': str(e), 'code': e.code}
    if path == '/api/v2/onboarding':
        from src.fabric import onboarding
        apk = getattr(server, 'companion_apk', None)
        portal = getattr(server, 'apk_portal', None)
        return 200, {'candidates': onboarding.candidates(server.fabric_snapshot, server.fabric_registry, bool(apk and apk.exists())),
                     'discovered': server.fabric_snapshot is not None,
                     'apk_portal': portal.state() if portal else {'running': False},
                     'note': None if server.fabric_snapshot else 'Run discovery first: nothing is probed until you ask.'}
    if path == '/api/v2/catalog':
        from src.fabric import android_actions as aa
        from src.adapters import tuya_local as tl
        return 200, {'android': {'actions': aa.ACTIONS, 'keys': sorted(aa.KEYS), 'tv_only_keys': sorted(aa.TV_ONLY),
                                 'settings': {k: {'range': v[2]} for k, v in aa.SETTINGS.items()},
                                 'primitives': ['device_capabilities', 'device_action', 'device_macro']},
                     'tuya_vacuum': {'commands': {k: list(v[1]) for k, v in tl.COMMANDS.items()}, 'settings': {k: list(v[1]) for k, v in tl.WRITABLE.items()},
                                     'primitives': ['tuya_command', 'tuya_setting', 'tuya_undo']},
                     'windows_pc': {'primitives': ['pc_job'], 'shells': ['cmd', 'powershell']},
                     'note': 'Compose new features with device_macro (Android) or sequences of these primitives; every write needs owner consent.'}
    if path == '/api/v2/watches':
        return 200, {'watches': ex.watchers().list()}
    if path in ('/api/v2/timeline', '/api/v2/hypotheses'):
        tl = ex.timeline()
        tl.ingest_routes(route_rows(server))
        dev = (q.get('device') or [None])[0]
        try:
            since = int((q.get('since_s') or ['0'])[0]) or None
            window = int((q.get('window_s') or ['90'])[0])
        except ValueError:
            return 400, {'error': 'since_s and window_s must be integers'}
        if path == '/api/v2/timeline':
            return 200, {'entries': tl.rows(dev, since)}
        if not dev:
            return 400, {'error': 'device is required'}
        if not 10 <= window <= 600:
            return 400, {'error': 'window_s out of range'}
        from src.runtime import hypotheses
        return 200, hypotheses.analyze(tl.rows(), dev, window)
    if path == '/api/v2/routes':
        return 200, {'routes': route_rows(server)}
    if path == '/api/v2/relays/samples':
        gid = (q.get('id') or [''])[0]
        if not gid.startswith(('addr:', 'rot:')) or len(gid) > 40:
            return 400, {'error': 'id must be an advertiser id from /api/v2/relays'}
        try:
            since = int((q.get('since_s') or ['120'])[0])
        except ValueError:
            return 400, {'error': 'since_s must be an integer'}
        led = getattr(server, 'relay_ledger', None)
        return 200, {'id': gid, 'samples': led.samples(gid, min(max(since, 1), 3600)) if led else []}
    if path == '/api/v2/relays':
        snap = server.fabric_snapshot or {'devices': []}
        strong = [d['label'] for d in snap['devices'] if d['category'] != 'ble' and d.get('identifier_kinds')]
        led = getattr(server, 'relay_ledger', None)
        return 200, {'routes': route_rows(server), 'advertisers': led.advertisers(strong) if led else []}
    if path == '/api/v2/diagnosis':
        from src.runtime.fabric_diagnosis import diagnose
        return 200, {'findings': diagnose(server.fabric_snapshot, route_rows(server), to_json(ex.recovery()))}
    snap = server.fabric_snapshot
    if snap is None:
        return 409, {'error': 'No graph yet; execute bounded_discovery first'}
    if path == '/api/v2/graph':
        ids = [DeviceIdentity(d['key'], d['category'], d['label'], tuple(sorted(d.get('identifier_kinds', ()))),
                              tuple(d.get('possibly_same_as', ()))) for d in snap['devices']]
        return 200, {'devices': [to_json(i) for i in ids], 'links': snap['links'], 'providers': snap.get('providers', {})}
    if path == '/api/v2/capabilities':
        descs = capabilities.describe(snap, _relay_permissions(server))
        dev = (q.get('device') or [None])[0]
        return 200, {'capabilities': [to_json(d) for d in descs if dev in (None, d.device_key)]}
    if path == '/api/v2/facts':
        dev = (q.get('device') or [''])[0]
        d = next((x for x in snap['devices'] if x['key'] == dev), None)
        if d is None:
            return 404, {'error': 'Unknown device'}
        # observed_at is the time of the observation whose value is returned, never the device's last_seen.
        source = (q.get('source') or [None])[0]
        if source is None:
            facts = [EvidenceFact(dev, name, f['value'], tuple(f['sources']), f.get('observed_at') or '', bool(f['verified']))
                     for name, f in sorted(d.get('facts', {}).items())]
        else:
            # Source-specific view: only what this one source reported, with its own value and time (no aggregation).
            reg = server.fabric_registry
            if reg is None or dev not in reg.devices:
                return 409, {'error': 'Graph changed during the read; run discovery again'}
            facts = [EvidenceFact(dev, name, o.value, (o.source,), o.observed_at, bool(o.verified))
                     for name, by_src in sorted(reg.devices[dev]['observations'].items()) for o in [by_src.get(source)] if o is not None]
        return 200, {'device': dev, 'facts': [to_json(f) for f in facts]}
    return 404, {'error': 'Not found'}


def escalation(server):
    if getattr(server, 'cloud_escalation', None) is None:
        from src.ai.cloud_escalation import CloudEscalation
        b = getattr(server, 'model_broker', None)
        server.cloud_escalation = CloudEscalation(b if callable(getattr(b, '_reserve', None)) else None)
    return server.cloud_escalation


def cloud(server, path, body):
    from src.ai.broker import ModelBlocked
    from src.runtime import hypotheses
    from src.runtime.redact import LeakDetected
    esc = escalation(server)
    try:
        if path == '/api/v2/cloud/preview':
            if set(body) - {'device_key', 'window_s'} or not isinstance(body.get('device_key'), str):
                return 400, {'error': 'device_key required; no other fields'}
            w = body.get('window_s', hypotheses.DEFAULT_WINDOW_S)
            if isinstance(w, bool) or not isinstance(w, int) or not 10 <= w <= 600:
                return 400, {'error': 'window_s out of range'}
            rows = executor(server).timeline().rows(limit=4000)
            return 200, esc.preview(hypotheses.analyze(rows, body['device_key'], w), rows)
        if set(body) - {'preview_id', 'sha256', 'consent'}:
            return 400, {'error': 'Unexpected fields'}
        return 200, esc.confirm(str(body.get('preview_id', ''))[:40], str(body.get('sha256', ''))[:64], body.get('consent'))
    except LeakDetected as e:
        return 409, {'error': 'Blocked: ' + str(e), 'state': 'BLOCKED_LEAK'}
    except ModelBlocked as e:
        return 409, {'error': str(e), 'state': 'BLOCKED'}


def _meta_key():
    import os
    k = os.environ.get('MODEL_API_KEY')
    if not k:
        try:
            from src.fabric.credential_vault import Vault
            k = Vault().get('meta-api-key')
        except Exception:
            k = None
    return k


def voice(server, path, body):
    from src.ai import voice_intent, voice_stt
    if path == '/api/v2/voice/intent':
        if set(body) != {'text'}:
            return 400, {'error': 'text only'}
        snap = server.fabric_snapshot or {'devices': []}
        return 200, voice_intent.compile_intent(body['text'], [{'key': d['key'], 'category': d['category']} for d in snap['devices']])
    if set(body) - {'audio_b64', 'language'} or not isinstance(body.get('audio_b64'), str):
        return 400, {'error': 'audio_b64 required'}
    import base64, binascii
    try:
        pcm = base64.b64decode(body['audio_b64'], validate=True)
    except (binascii.Error, ValueError):
        return 400, {'error': 'invalid audio'}
    try:
        return 200, voice_stt.transcribe(pcm, _meta_key(), body.get('language', 'fr'))
    except voice_stt.STTBlocked as e:
        return 409, {'error': str(e), 'fallback': 'type the command instead'}
    except OSError as e:
        return 503, {'error': f'Meta STT unreachable ({type(e).__name__})', 'fallback': 'type the command instead'}


def apk_portal(server, body):
    from src.fabric.apk_portal import ApkPortal
    from src.fabric.mdns import default_scope, lan_interface_ip
    if set(body) - {'minutes', 'stop'}:
        return 400, {'error': 'Unexpected fields'}
    old = getattr(server, 'apk_portal', None)
    if body.get('stop') is True:
        if old:
            old.stop()
        return 200, {'running': False}
    if old and old.running():
        return 200, old.state()
    ip = lan_interface_ip(default_scope())
    if not ip:
        return 409, {'error': 'No private LAN interface found on this PC'}
    try:
        server.apk_portal = ApkPortal(server.companion_apk, ip, body.get('minutes', 10)).start()
    except FileNotFoundError:
        return 409, {'error': 'Companion APK not built on this PC (python -m dev.build_companion)'}
    except (ValueError, OSError) as e:
        return 409, {'error': f'Cannot open the LAN download: {type(e).__name__}'}
    return 200, server.apk_portal.state()


def post(server, path, body):
    if path in ('/api/v2/skill_policy', '/api/v2/skill_arm', '/api/v2/skill_invoke') and isinstance(body, dict):
        from src.runtime.routing import RouteError
        r = router(server)
        try:
            out = {'/api/v2/skill_policy': r.set_policy, '/api/v2/skill_arm': r.arm, '/api/v2/skill_invoke': r.invoke}[path](body)
        except RouteError as e:
            return e.status, {'error': str(e), 'code': e.code}
        return (409 if isinstance(out, dict) and out.get('state') == 'BLOCKED' else 200), out
    if path == '/api/v2/onboarding/apk-portal' and isinstance(body, dict):
        return apk_portal(server, body)
    if path.startswith('/api/v2/voice/') and isinstance(body, dict):
        return voice(server, path, body)
    if path in ('/api/v2/cloud/preview', '/api/v2/cloud/confirm') and isinstance(body, dict):
        return cloud(server, path, body)
    if path == '/api/v2/recovery/acknowledge' and isinstance(body, dict):
        if set(body) - {'transaction_id', 'consent'} or not isinstance(body.get('transaction_id'), str) or body.get('consent') is not True:
            return 400, {'error': 'transaction_id and consent: true are required'}
        if not executor(server).acknowledge(body['transaction_id']):
            return 404, {'error': 'No unresolved transaction with this id'}
        return 200, to_json(executor(server).recovery())
    if path != '/api/v2/execute' or not isinstance(body, dict):
        return 404, {'error': 'Operation unavailable'}
    allowed = {'primitive_id', 'device_key', 'params', 'consent'}
    if set(body) - allowed:
        return 400, {'error': 'Unexpected fields'}
    r = executor(server).execute(body.get('primitive_id'), body.get('device_key'), body.get('params') or {}, body.get('consent') is True)
    status = 200 if r['state'] not in ('BLOCKED',) else 409
    return status, r


def reader(server):
    """Trusted in-process GET client for internal consumers (e.g. Capability Forge's RuntimeV1Provider).
    Same handlers as HTTP, no network hop; raises on non-200 so callers fail closed."""
    from urllib.parse import urlsplit
    def read_json(path):
        u = urlsplit(path)
        if not u.path.startswith('/api/v2/') or u.path not in GET_ROUTES:
            raise PermissionError('not a v2 read route')
        status, body = get(server, u.path, u.query)
        if status != 200:
            raise LookupError(body.get('error', status))
        return body
    return read_json
