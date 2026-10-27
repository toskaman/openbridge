"""/api/v2: versioned, local-only read model + single execute endpoint (contract v1).
No route accepts commands, shell strings, packages or addresses: writes are primitives run by the Executor."""
from urllib.parse import parse_qs

from src.runtime import capabilities, contract
from src.runtime.primitives import PRIMITIVES, Executor
from src.runtime.contract import to_json, DeviceIdentity, RelayRoute, EvidenceFact

GET_ROUTES = ('/api/v2/contract', '/api/v2/graph', '/api/v2/capabilities', '/api/v2/facts', '/api/v2/routes',
              '/api/v2/primitives', '/api/v2/recovery', '/api/v2/events')
POST_ROUTES = ('/api/v2/execute',)


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
        out.append(RelayRoute('*', key, rid, 'ble', r['permissions'].get('BLUETOOTH_SCAN') is True,
                              r['permissions'].get('owner_enabled') is True, bool(r['online']), r.get('last_success_at')))
    return out


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
    if path == '/api/v2/routes':
        return 200, {'routes': [to_json(r) for r in routes(server)]}
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
        facts = [EvidenceFact(dev, name, f['value'], tuple(f['sources']), d.get('last_seen') or '', bool(f['verified']))
                 for name, f in sorted(d.get('facts', {}).items())]
        return 200, {'device': dev, 'facts': [to_json(f) for f in facts]}
    return 404, {'error': 'Not found'}


def post(server, path, body):
    if path != '/api/v2/execute' or not isinstance(body, dict):
        return 404, {'error': 'Operation unavailable'}
    allowed = {'primitive_id', 'device_key', 'params', 'consent'}
    if set(body) - allowed:
        return 400, {'error': 'Unexpected fields'}
    r = executor(server).execute(body.get('primitive_id'), body.get('device_key'), body.get('params') or {}, body.get('consent') is True)
    status = 200 if r['state'] not in ('BLOCKED',) else 409
    return status, r
