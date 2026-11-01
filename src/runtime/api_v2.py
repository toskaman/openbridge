"""/api/v2: versioned, local-only read model + single execute endpoint (contract v1).
No route accepts commands, shell strings, packages or addresses: writes are primitives run by the Executor."""
from urllib.parse import parse_qs

from src.runtime import capabilities, contract
from src.runtime.primitives import PRIMITIVES, Executor
from src.runtime.contract import to_json, DeviceIdentity, RelayRoute, EvidenceFact

# Campaign One §3.6 HTTP hardening: defense-in-depth query caps for direct
# (in-process) callers; the HTTP front end enforces its own URL ceiling first.
MAX_QUERY_BYTES = 8192
MAX_QUERY_FIELDS = 100

GET_ROUTES = ('/api/v2/hardware/facts', '/api/v2/permissions/catalog', '/api/v2/permissions/state', '/api/v2/contract', '/api/v2/workflows/receipts', '/api/v2/primitives/catalog', '/api/v2/facts/signed', '/api/v2/manifests/receipts', '/api/v2/remote_controls', '/api/v2/skills', '/api/v2/skill_routes',
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
              '/api/v2/onboarding',
              '/api/v2/command/tiers',
              '/api/v2/companion/commands',
              '/api/v2/capabilities/explore',
              '/api/v2/capabilities/layouts',
              '/api/v2/capabilities/render',
              '/api/v2/orchestration/status',
              '/api/v2/dashboards/list')
POST_ROUTES = ('/api/v2/hardware/rank', '/api/v2/hardware/bench', '/api/v2/permissions/open', '/api/v2/permissions/recheck', '/api/v2/workflows/grant', '/api/v2/workflows/run', '/api/v2/workflows/revoke', '/api/v2/manifests/ui_install', '/api/v2/manifests/compile', '/api/v2/manifests/grant', '/api/v2/manifests/revoke', '/api/v2/manifests/invoke', '/api/v2/remote_controls', '/api/v2/remote_controls/invoke',
              '/api/v2/remote_controls/full_control', '/api/v2/skill_policy', '/api/v2/skill_arm', '/api/v2/skill_invoke', '/api/v2/onboarding/apk-portal', '/api/v2/execute', '/api/v2/recovery/acknowledge', '/api/v2/cloud/preview', '/api/v2/cloud/confirm', '/api/v2/voice/intent', '/api/v2/voice/transcribe', '/api/v2/command/parse', '/api/v2/command/approve', '/api/v2/command/execute', '/api/v2/capabilities/layouts', '/api/v2/capabilities/followup', '/api/v2/orchestration/run', '/api/v2/orchestration/approve', '/api/v2/orchestration/cancel', '/api/v2/dashboards/create', '/api/v2/dashboards/patch', '/api/v2/dashboards/save', '/api/v2/dashboards/load', '/api/v2/dashboards/delete', '/api/v2/dashboards/restore',)


import threading
_ROUTER_INIT_LOCK = threading.Lock()
_REMOTE_CONTROL_INIT_LOCK = threading.Lock()
_HTTP_IDEM_INIT_LOCK = threading.Lock()


def router(server):
    with _ROUTER_INIT_LOCK:
        if getattr(server, 'skill_router', None) is None:
            from src.runtime.routing import Router
            server.skill_router = Router(server)
        return server.skill_router


def remote_controls(server):
    with _REMOTE_CONTROL_INIT_LOCK:
        if getattr(server, 'remote_controls', None) is None:
            from src.runtime.remote_controls import RemoteControls
            server.remote_controls = rc = RemoteControls(server)
            close = getattr(server, 'server_close', None)
            if close is not None:                          # server shutdown stops the poller: no late dispatch
                def server_close(*a, **k):
                    rc.close()
                    return close(*a, **k)
                server.server_close = server_close
        return server.remote_controls


def substrate(server):
    if getattr(server, 'v4_substrate', None) is None:
        from src.substrate.kernel import Substrate
        server.v4_substrate = Substrate(server)
    return server.v4_substrate


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


def _explorer_data(server):
    """§6: assemble live exploration inputs. Auxiliary sources degrade to
    empty (exploration never 500s because fingerprints or probes are missing);
    statuses then conservatively downgrade (e.g. unprobed -> DISCOVERABLE)."""
    from src.fabric import capability_explorer as X
    from src.substrate import registry as R
    snap = server.fabric_snapshot
    try:
        sub = substrate(server)
    except Exception:
        sub = None
    fps = {}
    for d in snap['devices']:
        try:
            fps[d['key']] = sub.fingerprint(d['key']) if sub else None
        except Exception:
            fps[d['key']] = None
    try:
        probes = getattr(executor(server), 'probes', {}) or {}
    except Exception:
        probes = {}
    reg = getattr(server, 'fabric_registry', None)
    reg_devs = []
    for k, dv in (getattr(reg, 'devices', None) or {}).items():
        if isinstance(dv, dict):
            reg_devs.append({'key': k, 'category': dv.get('category'), 'label': dv.get('label', k)})
    try:
        perms = _relay_permissions(server)
    except Exception:
        perms = {}
    try:
        descs = capabilities.describe(snap, perms)
    except Exception:
        descs = []
    blocked = {}
    for x in descs:
        if getattr(x, 'verified', '') == 'BLOCKED':
            blocked.setdefault(x.device_key, []).extend(list(x.limitations or ()))
    return X.explore(snap['devices'], snap.get('links', []), R.catalog(), probes=probes,
                     fingerprints=fps, registry=reg_devs, blocked=blocked)


def _explorer_store(server):
    from src.runtime.state_store import StateStore
    return StateStore.for_server(server)


def _hardware_inspect(server, device):
    android = getattr(server, 'android', None)
    if android is None:
        return []
    handle = next(iter((device.get('handles') or {}).values()), None)
    if handle is None:
        return []
    try:
        rep = android.inspect(handle)
    except Exception:
        return []
    units = {'battery_percent': '%', 'storage_free_gb': 'GB', 'ram_total_gb': 'GB',
             'screen_timeout_seconds': 's'}
    out = []
    for e in rep.get('evidence', []):
        v = e.get('value')
        unit = units.get(e.get('key'), 'str' if isinstance(v, str) else 'bool' if isinstance(v, bool) else 'x')
        out.append({'name': e.get('key'), 'value': v, 'unit': unit, 'source': e.get('source', 'ADB'),
                    'observed_at': e.get('observed_at'), 'confidence': 'measured', 'availability': 'available'})
    return out


def _hardware_runner(server, key):
    try:
        actions = executor(server)._actions(key)
    except Exception:
        return None
    shell = getattr(actions, 'shell', None)
    return shell if callable(shell) else None


def _nvidia_runner():
    import subprocess

    def run(*argv):
        r = subprocess.run(list(argv), capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            raise OSError('nvidia-smi failed')
        return r.stdout
    return run


def _hardware_facts(server, only=None):
    from src.fabric import hardware_intel as H
    snap = server.fabric_snapshot
    devices = []
    for d in snap['devices']:
        if only is not None and d['key'] != only:
            continue
        metrics = {}
        if d.get('category') in ('phone', 'tv', 'watch', 'android', 'tablet'):
            for m in _hardware_inspect(server, d):
                metrics[m['name']] = m
            runner = _hardware_runner(server, d['key'])
            if runner is not None:
                for m in H.android_facts(runner):
                    metrics[m['name']] = m
        devices.append({'key': d['key'], 'category': d.get('category'), 'label': d.get('label', d['key']),
                        'metrics': list(metrics.values())})
    if only is None or only == 'pc':
        devices.append({'key': 'pc', 'category': 'pc', 'label': 'This PC',
                        'metrics': H.pc_facts(run=_nvidia_runner())})
    return {'devices': devices}


def _hardware_relays(server):
    import time as _time
    try:
        rows = route_rows(server)
    except Exception:
        return {}
    out = {}
    for r in rows:
        key = r.get('device_key') or r.get('key') or ''
        if not key:
            continue
        last = r.get('last_success_at')
        fresh = None
        if isinstance(last, (int, float)) and not isinstance(last, bool):
            fresh = max(0, int(_time.time() - last))
        prev = out.get(key, {})
        if prev.get('fresh_s') is None or (fresh is not None and fresh < prev['fresh_s']):
            out[key] = {'paired': True, 'fresh_s': fresh}
    return out


def get(server, path, query):
    if len(query) > MAX_QUERY_BYTES:
        return 414, {'error': 'Query string too long'}
    try:
        q = parse_qs(query, max_num_fields=MAX_QUERY_FIELDS)
    except ValueError:
        return 400, {'error': 'Too many query parameters'}
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
    if path == '/api/v2/remote_controls':
        return 200, remote_controls(server).state()
    if path == '/api/v2/command/tiers':
        from src.runtime import command as cmd
        return 200, cmd.tiers(server)
    if path == '/api/v2/companion/commands':
        from src.runtime.companion_commands import companion_commands
        cc = companion_commands(server)
        if (q.get('poll') or [''])[0] == '1':
            cc.poll_once()
        return 200, {'pending': cc.list()}
    if path == '/api/v2/orchestration/status':
        from src.runtime import workflows as W
        from src.runtime.state_store import StateStore
        store = StateStore.for_server(server)
        if store is None:
            return 409, {'error': 'no state store on this server'}
        rec = W.StateStoreJournal(store).get((q.get('workflow_id') or [''])[0])
        if rec is None:
            return 404, {'error': 'unknown workflow id'}
        return 200, rec
    if path == '/api/v2/dashboards/list':
        from src.runtime import dashboards as D
        from src.runtime.state_store import StateStore
        store = StateStore.for_server(server)
        if store is None:
            return 409, {'error': 'no state store on this server'}
        return 200, {'dashboards': D.DashStore(store).list()}
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
    if path == '/api/v2/primitives/catalog':
        from src.substrate import kernel, registry
        return 200, {'contract_version': kernel.CONTRACT_VERSION, 'primitives': registry.catalog(), 'schema': kernel.CONTRACT}
    if path == '/api/v2/facts/signed':
        from src.substrate.kernel import SubstrateError
        try:
            s = substrate(server)
            key = (q.get('device') or [''])[0]
            return 200, {'device_fingerprint': s.fingerprint(key), 'facts': s.facts(key)}
        except SubstrateError as e:
            return e.status, {'error': str(e), 'code': e.code}
    if path == '/api/v2/workflows/receipts':
        return 200, {'receipts': list(workflows(server).receipts[-30:])}
    if path == '/api/v2/manifests/receipts':
        return 200, {'receipts': list(substrate(server).receipts[-50:])}
    if path == '/api/v2/onboarding':
        from src.fabric import agent_matrix, onboarding
        apk = getattr(server, 'companion_apk', None)
        portal = getattr(server, 'apk_portal', None)
        agent_dir = getattr(server, 'agent_dir', None) or 'artifacts/agent'
        matrix = [{k: v for k, v in m.items() if k != 'path'}
                  for m in agent_matrix.matrix_status(apk, agent_dir)]
        return 200, {'candidates': onboarding.candidates(server.fabric_snapshot, server.fabric_registry, bool(apk and apk.exists())),
                     'discovered': server.fabric_snapshot is not None,
                     'apk_portal': portal.state() if portal else {'running': False},
                     'agent_matrix': matrix,
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
    if path == '/api/v2/permissions/catalog':
        from src.fabric import permissions as P
        return 200, {'package': P.COMPANION_PKG, 'permissions': P.CATALOG,
                     'capability_map': P.CAPABILITY_MAP}
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
    if path == '/api/v2/capabilities/explore':
        out = _explorer_data(server)
        dev = (q.get('device') or [None])[0]
        if dev is not None:
            out = {'devices': [d for d in out['devices'] if d['key'] == dev]}
        return 200, out
    if path == '/api/v2/capabilities/layouts':
        store = _explorer_store(server)
        if store is None:
            return 409, {'error': 'no state store on this server'}
        layouts = store.load().get('explorer_layouts', {})
        return 200, {'layouts': [{'layout_id': lid, 'name': l.get('name', lid),
                                  'version': l.get('version', 1),
                                  'widgets': len(l.get('widgets', []))} for lid, l in layouts.items()]}
    if path == '/api/v2/capabilities/render':
        from src.fabric import capability_explorer as X
        lid = (q.get('layout') or [''])[0]
        if not lid:
            return 400, {'error': 'layout query param is required'}
        store = _explorer_store(server)
        if store is None:
            return 409, {'error': 'no state store on this server'}
        layout = store.load().get('explorer_layouts', {}).get(lid)
        if layout is None:
            return 404, {'error': 'unknown layout'}
        try:
            return 200, X.render_layout(layout, _explorer_data(server))
        except X.ExplorerError as e:
            return 409, {'error': 'saved layout failed validation: %s' % e}
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
    if path == '/api/v2/hardware/facts':
        dev = (q.get('device') or [None])[0]
        return 200, _hardware_facts(server, only=dev)
    if path == '/api/v2/permissions/state':
        from src.fabric import permissions as P
        dev = (q.get('device') or [None])[0]
        devices = [d for d in snap['devices'] if dev in (None, d['key'])]
        if dev is not None and not devices:
            return 404, {'error': 'Unknown device'}
        out = []
        for d in devices:
            if d.get('category') not in ('phone', 'tv', 'watch', 'android', 'tablet'):
                out.append({'key': d['key'], 'supported': False, 'note': 'android only in v1'})
                continue
            runner = _hardware_runner(server, d['key'])
            if runner is None:
                out.append({'key': d['key'], 'supported': False, 'note': 'no shell runner for that device'})
                continue
            sdk = _perm_sdk(runner)
            out.append({'key': d['key'], 'category': d.get('category'), 'label': d.get('label', d['key']),
                        'supported': True, 'sdk': sdk, 'states': P.verify_all(runner, sdk=sdk)})
        return 200, {'devices': out}
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
    # Local-only (Sol audit): on-device Meta STT costs nothing and keeps audio home.
    # No silent cloud fallback — a cloud call would need explicit owner consent plus a
    # fresh credit reservation, which this endpoint does not take.
    from src.ai import stt_local
    try:
        if not stt_local.available():
            raise voice_stt.STTBlocked('local STT model not installed on this PC')
        try:
            return 200, stt_local.transcribe_pcm(bytes(pcm), body.get('language', 'fr'))
        except voice_stt.STTBlocked:
            raise
        except Exception as e:
            raise OSError(f'local STT failed ({type(e).__name__})') from e
    except voice_stt.STTBlocked as e:
        return 409, {'error': str(e), 'fallback': 'type the command instead'}
    except OSError as e:
        return 503, {'error': f'Meta STT unreachable ({type(e).__name__})', 'fallback': 'type the command instead'}


def apk_portal(server, body):
    from src.fabric.apk_portal import ApkPortal
    from src.fabric import agent_matrix
    from src.fabric.mdns import default_scope, lan_interface_ip
    if set(body) - {'minutes', 'stop', 'artifact'}:
        return 400, {'error': 'Unexpected fields'}
    old = getattr(server, 'apk_portal', None)
    if body.get('stop') is True:
        if old:
            old.stop()
        return 200, {'running': False}
    if old and old.running():
        return 200, old.state()
    artifact_id = body.get('artifact')
    serve_path, filename, content_type, url_path = server.companion_apk, None, None, None
    if artifact_id is not None:
        if not isinstance(artifact_id, str):
            return 400, {'error': 'artifact must be an entry id'}
        agent_dir = getattr(server, 'agent_dir', None) or 'artifacts/agent'
        hit = next((m for m in agent_matrix.matrix_status(server.companion_apk, agent_dir)
                    if m['id'] == artifact_id), None)
        if hit is None:
            return 400, {'error': f'Unknown artifact: {artifact_id[:32]}'}
        if 'path' not in hit:
            return 409, {'error': hit['reason']}
        serve_path, filename, content_type = hit['path'], hit['filename'], hit['content_type']
        url_path = '/' + hit['filename']
    ip = lan_interface_ip(default_scope())
    if not ip:
        return 409, {'error': 'No private LAN interface found on this PC'}
    try:
        server.apk_portal = ApkPortal(serve_path, ip, body.get('minutes', 10), filename=filename,
                                      content_type=content_type, url_path=url_path).start()
    except FileNotFoundError as e:
        if artifact_id is not None:
            return 409, {'error': str(e)}
        return 409, {'error': 'Companion APK not built on this PC (python -m dev.build_companion)'}
    except (ValueError, OSError) as e:
        return 409, {'error': f'Cannot open the LAN download: {type(e).__name__}'}
    return 200, server.apk_portal.state() | {'artifact': artifact_id}


def workflows(server):
    if getattr(server, 'v4_workflows', None) is None:
        from src.substrate.workflow import Workflows
        server.v4_workflows = Workflows(substrate(server))
    return server.v4_workflows


def _idem_seen(server):
    seen = getattr(server, 'http_idem_keys', None)
    if seen is None:
        with _HTTP_IDEM_INIT_LOCK:
            seen = getattr(server, 'http_idem_keys', None)
            if seen is None:
                seen = server.http_idem_keys = {}
                server.http_idem_lock = threading.Lock()
    return seen


def _idem_begin(server, key):
    """Claim an idempotency key: None when this call owns it, else (status, body)."""
    import time as _t
    from src.runtime.state_store import StateStore, StateError
    store = StateStore.for_server(server)
    if store is not None:
        try:
            claimed, row = store.claim_invocation('http-v2', key, _t.time())
        except StateError as e:
            return {'status': 503, 'body': {'error': '%s: %s' % (e.code, e)}}
        if claimed:
            return None
        if row['state'] == 'DONE':
            return {'status': 409, 'body': {'error': 'DUPLICATE_REQUEST: this idempotency_key was already handled'}}
        return {'status': 409, 'body': {'error': 'UNCERTAIN_OUTCOME: this idempotency_key is already running elsewhere or was interrupted; use a fresh key'}}
    seen = _idem_seen(server)
    with server.http_idem_lock:
        now = _t.monotonic()
        for k in [k for k, v in seen.items() if v[0] == 'DONE' and now - v[1] > 600]:
            del seen[k]
        state = seen.get(key, (None, 0))[0]
        if state == 'DONE':
            return {'status': 409, 'body': {'error': 'DUPLICATE_REQUEST: this idempotency_key was already handled'}}
        if state == 'EXECUTING':
            return {'status': 409, 'body': {'error': 'UNCERTAIN_OUTCOME: this idempotency_key is already running; use a fresh key'}}
        if len(seen) >= 4096:
            victim = next((k for k, v in seen.items() if v[0] == 'DONE'), None)
            if victim is None:
                return {'status': 503, 'body': {'error': 'STATE_JOURNAL_FULL: idempotency cache is full of running keys'}}
            del seen[victim]
        seen[key] = ('EXECUTING', now)
        return None


def _idem_fingerprint(primitive_id, device_key, params):
    import hashlib
    import json as _json
    canon = _json.dumps({'primitive': primitive_id, 'device': device_key, 'params': params},
                        sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(canon.encode()).hexdigest()


def _idem_finish(server, key, fingerprint):
    from src.runtime.state_store import StateStore, StateError
    import time as _t
    store = StateStore.for_server(server)
    if store is not None:
        try:
            store.finish_invocation('http-v2', key, fingerprint, _t.time())
        except StateError:
            pass   # leftover EXECUTING fails closed: retries refuse as uncertain, never re-dispatch
        return
    with server.http_idem_lock:
        _idem_seen(server)[key] = ('DONE', _t.monotonic())


def _perm_sdk(runner):
    try:
        return int((runner('getprop', 'ro.build.version.sdk') or '').strip())
    except Exception:
        return None


def post(server, path, body):
    if path in ('/api/v2/permissions/open', '/api/v2/permissions/recheck') and isinstance(body, dict):
        from src.fabric import permissions as P
        if server.fabric_snapshot is None:
            return 409, {'error': 'No graph yet; execute bounded_discovery first'}
        key = body.get('device', '')
        d = next((x for x in server.fabric_snapshot['devices'] if x['key'] == key), None)
        if d is None:
            return 404, {'error': 'Unknown device'}
        entry = next((e for e in P.CATALOG if e['id'] == body.get('permission', '')), None)
        if entry is None:
            return 400, {'error': 'unknown permission'}
        runner = _hardware_runner(server, key)
        if runner is None:
            return 409, {'error': 'no shell runner for that device'}
        if path == '/api/v2/permissions/recheck':
            return 200, P.verify_one(runner, entry['id'], sdk=_perm_sdk(runner))
        if body.get('consent') is not True:
            return 400, {'error': 'consent: true is required'}
        argv = P.grant_command(entry, P.COMPANION_PKG) or P.intent_command(entry, P.COMPANION_PKG)
        if argv is None:
            return 400, {'error': 'no open action for this permission (in-app only)'}
        try:
            text = runner(*argv)
        except Exception as e:
            return 409, {'error': 'command failed: %s' % e}
        return 200, {'argv': argv, 'output': (text or '')[:500]}
    if path in ('/api/v2/hardware/rank', '/api/v2/hardware/bench') and isinstance(body, dict):
        from src.fabric import hardware_intel as H
        if server.fabric_snapshot is None:
            return 409, {'error': 'No graph yet; execute bounded_discovery first'}
        if path == '/api/v2/hardware/rank':
            try:
                devs = _hardware_facts(server)['devices']
                if isinstance(body.get('devices'), list):
                    want = set(body['devices'])
                    devs = [d for d in devs if d['key'] in want]
                return 200, H.rank(body.get('task', ''), devs, relays=_hardware_relays(server))
            except H.HardwareError as e:
                return 400, {'error': str(e)}
        if body.get('consent') is not True:
            return 400, {'error': 'consent: true is required (benchmarks consume resources)'}
        kind = body.get('kind', '')
        kw = {}
        if kind == 'cpu_loop' and body.get('iterations') is not None:
            kw['iterations'] = body.get('iterations')
        if kind == 'disk_write' and body.get('megabytes') is not None:
            kw['megabytes'] = body.get('megabytes')
        if kind == 'device_rtt':
            if body.get('attempts') is not None:
                kw['attempts'] = body.get('attempts')
            runner = _hardware_runner(server, body.get('device', ''))
            if runner is None:
                return 409, {'error': 'no shell runner for that device'}
            kw['runner'] = runner
        try:
            return 200, H.microbench(kind, consent=True, **kw)
        except H.HardwareError as e:
            return 400, {'error': str(e)}
    if path in ('/api/v2/orchestration/run', '/api/v2/orchestration/approve', '/api/v2/orchestration/cancel') and isinstance(body, dict):
        import secrets as _secrets
        from src.runtime import workflows as W
        from src.runtime.state_store import StateStore
        store = StateStore.for_server(server)
        if store is None:
            return 409, {'error': 'no state store on this server'}
        journal = W.StateStoreJournal(store)
        try:
            if path == '/api/v2/orchestration/run':
                wid = body.get('workflow_id') or ('wf-' + _secrets.token_hex(6))
                return 200, W.run(body, router(server), journal, wid)
            if path == '/api/v2/orchestration/approve':
                if not isinstance(body.get('consent'), bool):
                    return 400, {'error': 'consent must be an explicit boolean (true approves, false denies)'}
                return 200, W.approve(str(body.get('workflow_id', '')), str(body.get('step_id', '')),
                                      body['consent'], router(server), journal)
            return 200, W.cancel(str(body.get('workflow_id', '')), journal)
        except W.WorkflowError as e:
            return 400, {'error': str(e)}
    if path.startswith('/api/v2/dashboards/') and isinstance(body, dict):
        from src.runtime import dashboards as D
        from src.runtime.remote_controls import RemoteControlError
        from src.runtime.state_store import StateStore
        store = StateStore.for_server(server)
        if store is None:
            return 409, {'error': 'no state store on this server'}
        journal = D.DashStore(store)
        rc = remote_controls(server)
        try:
            if path == '/api/v2/dashboards/create':
                return 200, D.create(rc, str(body.get('relay_id', '')), str(body.get('area', '')),
                                     str(body.get('target', '')), body.get('consent'))
            if path == '/api/v2/dashboards/patch':
                return 200, D.patch(rc, str(body.get('relay_id', '')), body.get('add') or (),
                                    body.get('remove') or (), body.get('consent'))
            if path == '/api/v2/dashboards/save':
                journal.save(str(body.get('relay_id', '')), str(body.get('name', '')),
                             D.defs(rc, str(body.get('relay_id', ''))))
                return 200, {'saved': body.get('name')}
            if path == '/api/v2/dashboards/load':
                return 200, D.load(journal, rc, str(body.get('name', '')),
                                   body.get('relay_id') or None, body.get('consent'))
            if path == '/api/v2/dashboards/delete':
                journal.delete(str(body.get('name', '')))
                return 200, {'deleted': body.get('name')}
            if path == '/api/v2/dashboards/restore':
                return 200, {'restored': D.restore_on_reconnect(rc, journal,
                                                                str(body.get('relay_id', '')))}
            return 404, {'error': 'unknown dashboards route'}
        except D.DashboardError as e:
            return 400, {'error': str(e)}
        except RemoteControlError as e:
            return e.status, {'error': str(e)}
    if path.startswith('/api/v2/workflows/') and isinstance(body, dict):
        from src.substrate.kernel import SubstrateError
        w = workflows(server)
        try:
            if path == '/api/v2/workflows/grant':           # owner path only (CSRF + Origin enforced by the server)
                return 200, {'wgrant': w.issue_grant(body.get('workflow'), body.get('bindings'), body.get('consent'), body.get('ttl_s', 900))}
            if path == '/api/v2/workflows/revoke':
                w.revoke(str(body.get('wgrant_id', '')))
                return 200, {'revoked': body.get('wgrant_id')}
            if path == '/api/v2/workflows/run':
                return 200, w.run(body.get('workflow'), body.get('wgrant'), body.get('bindings'), body.get('operation_id'))
        except SubstrateError as e:
            return e.status, dict({'error': str(e), 'code': e.code}, **e.extra)
    if path.startswith('/api/v2/manifests/') and isinstance(body, dict):
        from src.substrate.kernel import SubstrateError
        s = substrate(server)
        try:
            if path == '/api/v2/manifests/compile':          # dry run: no side effect, no grant
                c = s.compile(body.get('manifest'), body.get('facts') or [], body.get('inputs'))
                return 200, {k: v for k, v in c.items() if k != 'device_key'}
            if path == '/api/v2/manifests/grant':            # owner path only (CSRF + Origin enforced by the server)
                g, c = s.issue_grant(body.get('manifest'), body.get('facts') or [], body.get('consent'), body.get('max_uses', 1), body.get('ttl_s', 900))
                return 200, {'grant': g, 'manifest_hash': c['manifest_hash'], 'permissions': c['permissions'], 'effects': c['effects']}
            if path == '/api/v2/manifests/revoke':
                s.revoke(str(body.get('grant_id', '')))
                return 200, {'revoked': body.get('grant_id')}
            if path == '/api/v2/manifests/ui_install':
                return 200, s.install_ui_plan(body)
            if path == '/api/v2/manifests/invoke':
                return 200, s.invoke(body.get('manifest'), body.get('grant'), body.get('facts') or [], body.get('request') or {})
        except SubstrateError as e:
            return e.status, dict({'error': str(e), 'code': e.code}, **e.extra)
    if path in ('/api/v2/command/parse', '/api/v2/command/approve', '/api/v2/command/execute') and isinstance(body, dict):
        from src.runtime import command as cmd
        try:
            if path == '/api/v2/command/parse':
                return 200, cmd.parse_request(server, body)
            if path == '/api/v2/command/approve':
                return 200, cmd.approve(server, body.get('intent'))
            return 200, cmd.execute(server, body.get('intent'), body.get('consent', False),
                                    body.get('preview'))
        except cmd.CommandError as e:
            return e.status, {'error': str(e)}
    if path == '/api/v2/remote_controls':
        from src.runtime.remote_controls import RemoteControlError
        from src.fabric.relay import RelayError
        try:
            return 200, remote_controls(server).set_controls(body)
        except RemoteControlError as e:
            return e.status, {'error': str(e)}
        except RelayError as e:
            return 409, {'error': str(e)}
    if path == '/api/v2/remote_controls/invoke':
        from src.runtime.remote_controls import RemoteControlError
        try:
            if not isinstance(body, dict) or body.get('consent') is not True:
                return 400, {'error': 'relay_id, control_id and consent: true are required'}
            return 200, remote_controls(server).invoke_now(body.get('relay_id'), body.get('control_id'))
        except RemoteControlError as e:
            return e.status, {'error': str(e)}
    if path == '/api/v2/remote_controls/full_control':
        from src.runtime.remote_controls import RemoteControlError
        try:
            if not isinstance(body, dict) or not isinstance(body.get('blocked'), bool) or body.get('consent') is not True:
                return 400, {'error': 'relay_id, blocked: bool and consent: true are required'}
            return 200, remote_controls(server).set_full_control_block(body.get('relay_id'), body.get('blocked'))
        except RemoteControlError as e:
            return e.status, {'error': str(e)}
    if path in ('/api/v2/skill_policy', '/api/v2/skill_arm', '/api/v2/skill_invoke') and isinstance(body, dict):
        from src.runtime.routing import RouteError
        r = router(server)
        try:
            out = {'/api/v2/skill_policy': r.set_policy, '/api/v2/skill_arm': r.arm, '/api/v2/skill_invoke': r.invoke}[path](body)
        except RouteError as e:
            return e.status, {'error': str(e), 'code': e.code}
        return (409 if isinstance(out, dict) and out.get('state') == 'BLOCKED' else 200), out
    if path in ('/api/v2/capabilities/layouts', '/api/v2/capabilities/followup') and isinstance(body, dict):
        import secrets
        from src.fabric import capability_explorer as X
        store = _explorer_store(server)
        if store is None:
            return 409, {'error': 'no state store on this server'}
        if path == '/api/v2/capabilities/layouts':
            try:
                if body.get('draft'):
                    layout = X.draft_layout(_explorer_data(server), (body.get('name') or 'Untitled layout')[:80])
                else:
                    layout = X.validate_layout({'schema_version': 1, 'name': (body.get('name') or 'Untitled layout')[:80],
                                                'version': 1, 'origin': 'user', 'widgets': body.get('widgets', [])})
            except X.ExplorerError as e:
                return 400, {'error': str(e)}
            lid = 'lay-' + secrets.token_hex(4)
            layout = dict(layout, layout_id=lid)
            store.update_layouts(lambda m: m.__setitem__(lid, layout))
            return 200, {'layout_id': lid, 'version': 1, 'widgets': len(layout['widgets'])}
        lid = body.get('layout_id', '')
        saved = store.load().get('explorer_layouts', {}).get(lid)
        if saved is None:
            return 404, {'error': 'unknown layout'}
        if body.get('expected_version') is None:
            return 400, {'error': 'expected_version is required'}
        try:
            op, args = ((body.get('op'), body.get('args', {})) if body.get('op')
                        else X.parse_followup(body.get('text', '')))
            layout = X.followup(saved, op, args or {}, body.get('expected_version'),
                                explored=_explorer_data(server))
        except X.ExplorerError as e:
            if str(e) == 'VERSION_CONFLICT':
                return 409, {'error': 'layout changed; reload and retry'}
            return 400, {'error': str(e)}
        layout = dict(layout, layout_id=lid)
        store.update_layouts(lambda m: m.__setitem__(lid, layout))
        return 200, layout
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
            recovery = executor(server).recovery()
            if recovery.blocked_reason.startswith('STATE_'):
                return 503, {'error': recovery.blocked_reason, 'recovery': to_json(recovery)}
            return 404, {'error': 'No unresolved transaction with this id'}
        return 200, to_json(executor(server).recovery())
    if path != '/api/v2/execute' or not isinstance(body, dict):
        return 404, {'error': 'Operation unavailable'}
    allowed = {'primitive_id', 'device_key', 'params', 'consent', 'idempotency_key'}
    if set(body) - allowed:
        return 400, {'error': 'Unexpected fields'}
    key = body.get('idempotency_key')
    if key is not None and (not isinstance(key, str) or not key or len(key) > 96):
        return 400, {'error': 'idempotency_key must be a non-empty string of at most 96 characters'}
    if key is not None:
        refused = _idem_begin(server, key)
        if refused is not None:
            return refused['status'], refused['body']
    r = executor(server).execute(body.get('primitive_id'), body.get('device_key'), body.get('params') or {}, body.get('consent') is True)
    if key is not None:
        _idem_finish(server, key, _idem_fingerprint(body.get('primitive_id'), body.get('device_key'), body.get('params') or {}))
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
