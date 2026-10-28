"""B2 runtime: typed skills, provider derivation, route truth, selection policies, invocation leases and dispatch.

Implements docs/contracts/B2_SKILL_ROUTING_CONTRACT.md (rev 2). Every response validates against
src/runtime/b2_skill_routes.schema.json + route_contract.semantic_errors (tested). No model is involved: providers come
from the registry graph, the relay manager/ledger and measured probes; selection is deterministic; every dispatch goes
through the existing Executor (consent, locks, receipts, recovery).
"""
import hashlib
import json
import secrets
import threading
import time
from datetime import datetime, timezone

from src.runtime import route_contract as rc

GRANT_RANK = {'observe': 0, 'read': 1, 'control': 2}
TRANSPORTS = ('USB', 'WIFI', 'LAN', 'BLE', 'RELAY', 'CLOUD_API', 'AGENT')
LEASE_S = {'USB': 60, 'WIFI': 60, 'RELAY': 120, 'LAN': 300, 'BLE': 120, 'CLOUD_API': 60, 'AGENT': 60}
INVOCATION_LEASE_S = 30
ACTOR = 'owner'                     # the local UI; Companion/Watch actors arrive with B3

SKILLS = {
    'ble_scan_room': {'version': 1, 'reversibility': 'SESSION_CLEANUP', 'idempotent': True, 'consent': 'per_invocation', 'targeted': False,
                      'input': {'type': 'object', 'properties': {'seconds': {'type': 'integer', 'minimum': 1, 'maximum': 15}}, 'additionalProperties': False},
                      'plain': 'Find nearby Bluetooth devices through a paired relay (scan only).'},
    'device_facts': {'version': 1, 'reversibility': 'NONE', 'idempotent': True, 'consent': 'none', 'targeted': True,
                     'input': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     'plain': 'Read the verified facts OpenBridge holds for one device.'},
    'tv_volume_set': {'version': 2, 'reversibility': 'EXACT', 'idempotent': False, 'consent': 'per_invocation', 'targeted': True,
                      'input': {'type': 'object', 'properties': {'value': {'type': 'integer', 'minimum': 0, 'maximum': 100}}, 'required': ['value'], 'additionalProperties': False},
                      'plain': 'Set media volume to an exact value, read it back, keep the previous value for exact Undo.'},
    'tv_volume_step': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': False, 'consent': 'per_invocation', 'targeted': True,
                       'input': {'type': 'object', 'properties': {'direction': {'type': 'string', 'enum': ['up', 'down']}}, 'required': ['direction'], 'additionalProperties': False},
                       'plain': 'Press volume up or down once (one press per invocation).'},
}
ANDROID = ('phone', 'tv', 'android', 'watch')


class RouteError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def _iso(t):
    """epoch seconds or ISO string -> contract timestamp (UTC, Z)."""
    if t is None:
        return None
    if isinstance(t, str):
        try:
            t = datetime.fromisoformat(t.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    return datetime.fromtimestamp(int(t), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _epoch(ts):
    return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()


def _fp(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


class Router:
    def __init__(self, server, clock=time.time):
        self.server, self.clock = server, clock
        self.epoch = 'boot-' + secrets.token_hex(4)
        self.seq, self._graph_fp = 0, None
        self._authority = {}         # device_key -> (fingerprint, rev)
        self.policies = {}           # skill_id -> {'mode','failover','pinned_route_id','preferred':[route_ids],'set_by'}
        self.invocations = {}        # skill_id -> armed/executing invocation
        self.selected = {}           # (skill_id, target) -> last selected route_id (for route_changed)
        self.ledger = rc.InvocationLedger()
        self.completed = {}          # (actor, invocation_id) -> (binding, request fingerprint, finished)
        self._lock = threading.RLock()

    # ---------- inputs ----------
    def _ex(self):
        from src.runtime.api_v2 import executor
        return executor(self.server)

    def _snap(self):
        return self.server.fabric_snapshot or {'devices': [], 'links': []}

    def _revision(self, snap):
        relays = getattr(getattr(self.server, 'relays', None), 'relays', {}) or {}
        state = {'d': [(d['key'], d.get('category'), sorted(d.get('handles', {}).items()),
                        sorted((c.get('name'), c.get('status')) for c in d.get('capabilities', []))) for d in snap['devices']],
                 'l': sorted((l['parent'], l['child'], l['transport'], tuple(l['grants'])) for l in snap['links']),
                 'r': sorted((rid, r.get('device_key'), r.get('online'), sorted((r.get('permissions') or {}).items())) for rid, r in relays.items()),
                 'p': self.policies}
        fp = _fp(state)
        if fp != self._graph_fp:
            self._graph_fp, self.seq = fp, self.seq + 1
        return {'epoch': self.epoch, 'seq': self.seq}

    def _authority_rev(self, snap, key):
        grants = sorted((l['parent'], l['transport'], tuple(l['grants'])) for l in snap['links'] if l['child'] == key)
        dev = next((d for d in snap['devices'] if d['key'] == key), {})
        fp = _fp([grants, sorted(dev.get('handles', {}).items())])
        old = self._authority.get(key)
        if old is None or old[0] != fp:
            self._authority[key] = (fp, (old[1] + 1) if old else 1)
        return self._authority[key][1]

    def _best_link(self, snap, key):
        links = [l for l in snap['links'] if l['parent'] == 'pc' and l['child'] == key]
        if not links:
            return None
        return max(links, key=lambda l: max((GRANT_RANK.get(g, -1) for g in l['grants']), default=-1))

    @staticmethod
    def _grant(link):
        return max(link['grants'], key=lambda g: GRANT_RANK.get(g, -1)) if link and link['grants'] else 'observe'

    @staticmethod
    def _transport(t):
        return t if t in TRANSPORTS else 'LAN'

    def _target_identity(self, key):
        reg = self.server.fabric_registry
        dev = reg.devices.get(key, {}) if reg else {}
        strong = sorted(f'{i.kind}:{i.value}' for i in dev.get('identifiers', ()) if getattr(i, 'strong', False))
        return strong[0] if strong else f'device:{key}'

    def _last_receipt(self, primitive_id, key):
        ex = self._ex()
        with ex._guard:
            rs = [r for r in ex.receipts.values() if r.primitive_id == primitive_id and r.device_key == key]
        if not rs:
            return None
        r = max(rs, key=lambda r: r.finished_at)
        sim = key.startswith('sim-') or 'SIMULATED' in json.dumps(r.errors)
        return {'transaction_id': r.transaction_id, 'state': r.state if r.state in ('VERIFIED', 'EXECUTED', 'REVERTED', 'FAILED', 'PARTIAL', 'UNKNOWN_TIMEOUT', 'BLOCKED') else 'BLOCKED',
                'evidence': 'NONE' if r.state == 'BLOCKED' else 'SIMULATED' if sim else 'REAL_HARDWARE', 'finished_at': _iso(r.finished_at) or _iso(self.clock())}

    def _success_rate(self, primitive_id, key):
        ex = self._ex()
        with ex._guard:
            rs = sorted((r for r in ex.receipts.values() if r.primitive_id == primitive_id and r.device_key == key), key=lambda r: r.finished_at)[-10:]
        return sum(r.state in ('VERIFIED', 'EXECUTED', 'REVERTED') for r in rs) / len(rs) if rs else 0.0

    # ---------- providers ----------
    def _route(self, skill_id, snap, key, hops, op, primitive_id, observed, lease_s, source, reason=None, detail=None, exactness=None):
        rid = rc.route_id(skill_id, hops, op)
        now = self.clock()
        obs = observed if observed is not None else now
        expires = obs + lease_s
        if reason is None and expires < now:
            reason = 'lease_stale'
        last = self._last_receipt(primitive_id, key)
        consent = 'none' if SKILLS[skill_id]['consent'] == 'none' else 'required'
        return {'route_id': rid, 'provider_id': rc.provider_id(key, hops[-1]['transport'], primitive_id, op), 'operation_id': op,
                'state': 'UNAVAILABLE' if reason else 'READY', 'reason': reason, 'reason_detail': detail, 'consent': consent, 'hops': hops,
                'authority': {'grants_checked': [f"{h['required_grant']}@{h['device_key']}" for h in hops][:8], 'authority_rev': self._authority_rev(snap, key)},
                'freshness': {'observed_at': _iso(obs), 'expires_at': _iso(expires), 'lease_s': lease_s, 'source': source[:64]},
                'exactness': exactness, 'last_receipt': last, 'evidence': last['evidence'] if last else 'NONE',
                '_key': key, '_primitive': primitive_id, '_age': now - obs}

    def _providers(self, skill_id, target):
        snap = self._snap()
        devs = {d['key']: d for d in snap['devices']}
        out = []
        if skill_id == 'ble_scan_room':
            relays = getattr(getattr(self.server, 'relays', None), 'relays', {}) or {}
            led = getattr(self.server, 'relay_ledger', None)
            reg = self.server.fabric_registry
            for rid, r in sorted(relays.items()):
                key = next((k for k, d in (reg.devices.items() if reg else ()) if r['device_key'] in d.get('handles', {}).values()), None)
                if key is None or key not in devs:
                    continue
                link = self._best_link(snap, key)
                g = self._grant(link)
                hops = [{'device_key': key, 'transport': self._transport(link['transport'] if link else 'LAN'), 'primitive_id': 'relay_ble_scan', 'grant': g, 'required_grant': 'control'},
                        {'device_key': key, 'transport': 'RELAY', 'primitive_id': 'relay_ble_scan', 'grant': 'control' if r['permissions'].get('BLUETOOTH_SCAN') else 'observe', 'required_grant': 'control'}]
                last_ok = (led.routes.get(rid) or {}).get('last_success_at') if led else None
                reason = detail = None
                if not r.get('online'):
                    reason = 'link_down'
                elif GRANT_RANK.get(g, -1) < GRANT_RANK['control']:
                    reason, detail = 'grant_insufficient', {'missing_grant': 'control', 'hop_index': 0, 'blocking_device_key': None}
                elif not r['permissions'].get('BLUETOOTH_SCAN'):
                    reason, detail = 'grant_insufficient', {'missing_grant': 'control', 'hop_index': 1, 'blocking_device_key': key}
                elif not r['permissions'].get('owner_enabled'):
                    reason = 'policy_blocked'
                route = self._route(skill_id, snap, key, hops, 'op:relay_ble_scan', 'relay_ble_scan', last_ok if last_ok else self.clock(),
                                    LEASE_S['RELAY'], 'relay ledger' if last_ok else 'relay pairing (no scan yet)', reason, detail)
                if not last_ok:
                    route['_age'] = LEASE_S['RELAY']   # never scanned: ranks after any proven relay, deterministically
                route['_params'] = lambda p, rid=rid: {'relay_id': rid, 'seconds': p.get('seconds', 8)}
                out.append(route)
            return out
        if target not in devs:
            return out
        d = devs[target]
        link = self._best_link(snap, target)
        g = self._grant(link)
        tr = self._transport(link['transport']) if link else 'LAN'
        seen = d.get('last_seen') or None
        observed = _epoch(_iso(seen)) if _iso(seen) else None
        if skill_id == 'device_facts':
            hops = [{'device_key': target, 'transport': tr, 'primitive_id': 'read_facts', 'grant': g, 'required_grant': 'read'}]
            reason = 'link_down' if link is None else None
            detail = None
            if reason is None and GRANT_RANK.get(g, -1) < GRANT_RANK['read']:
                reason, detail = 'grant_insufficient', {'missing_grant': 'read', 'hop_index': 0, 'blocking_device_key': None}
            r = self._route(skill_id, snap, target, hops, 'op:read_facts', 'read_facts', observed, LEASE_S.get(tr, 300), 'registry last_seen', reason, detail)
            r['_params'] = lambda p: {}
            return [r]
        # Android volume skills: ADB link with control grant.
        if d.get('category') not in ANDROID:
            return out
        adb = link is not None and link['transport'] in ('USB', 'WIFI') and bool(d.get('handles'))
        if skill_id == 'tv_volume_set':
            op, prim = 'op:device_action:set_media_volume', 'device_action'
        else:
            op, prim = 'op:device_action:key_volume', 'device_action'
        hops = [{'device_key': target, 'transport': tr, 'primitive_id': prim, 'grant': g, 'required_grant': 'control'}]
        reason = detail = exact = None
        if not adb:
            reason = 'link_down'
        elif GRANT_RANK.get(g, -1) < GRANT_RANK['control']:
            reason, detail = 'grant_insufficient', {'missing_grant': 'control', 'hop_index': 0, 'blocking_device_key': None}
        if skill_id == 'tv_volume_set':
            probe = (getattr(self._ex(), 'probes', {}) or {}).get(target)
            rng = ((probe or {}).get('ranges') or {}).get('media_volume') if probe else None
            if rng:
                exact = {'range': [int(rng[0]), int(rng[1])], 'before_snapshot': True, 'readback': 'independent', 'restore': 'exact'}
            elif reason is None:   # never claim EXACT without a measured, readable range: measure first (read-only probe)
                reason, detail = 'dependency_unready', {'missing_grant': None, 'hop_index': 0, 'blocking_device_key': target}
        r = self._route(skill_id, snap, target, hops, op, prim, observed, LEASE_S.get(tr, 60), 'adb discovery', reason, detail, exact)
        if skill_id == 'tv_volume_set':
            r['_params'] = lambda p: {'action': 'set', 'args': {'setting': 'media_volume', 'value': p['value']}}
        else:
            r['_params'] = lambda p: {'action': 'key', 'args': {'key': 'volume_up' if p['direction'] == 'up' else 'volume_down'}}
        return [r]

    # ---------- truth ----------
    def policy(self, skill_id):
        return self.policies.get(skill_id) or {'mode': 'AUTO', 'failover': 'none', 'pinned_route_id': None, 'preferred': [], 'set_by': 'default'}

    def _evaluate(self, skill_id, target):
        if skill_id not in SKILLS:
            raise RouteError(404, 'UNKNOWN_SKILL', 'Unknown skill')
        if SKILLS[skill_id]['targeted'] and not target:
            raise RouteError(400, 'TARGET_REQUIRED', 'This skill needs target=<device key>')
        snap = self._snap()
        rev = self._revision(snap)
        routes = self._providers(skill_id, target)
        pol = self.policy(skill_id)
        eligible = [r for r in routes if r['state'] == 'READY']
        sel, rule = None, 'none_eligible'
        if pol['mode'] == 'PINNED':
            for r in eligible:
                if r['route_id'] != pol['pinned_route_id']:
                    r['state'] = 'STANDBY'
            sel = next((r['route_id'] for r in eligible if r['route_id'] == pol['pinned_route_id']), None)
            rule = 'pinned' if sel else 'none_eligible'
        elif eligible:
            if pol['mode'] == 'PREFERRED' and any(r['route_id'] in pol['preferred'] for r in eligible):
                order = {rid: i for i, rid in enumerate(pol['preferred'])}
                sel = min(eligible, key=lambda r: (order.get(r['route_id'], 10 ** 6), r['route_id']))['route_id']
                rule = 'preferred_order'
            else:
                sel = min(eligible, key=lambda r: (int(r['_age']), len(r['hops']), -self._success_rate(r['_primitive'], r['_key']), r['route_id']))['route_id']
                rule = 'auto_score'
        # backend order: selected first, then READY, STANDBY, UNAVAILABLE; stable by route_id
        rank = {'READY': 1, 'STANDBY': 2, 'UNAVAILABLE': 3}
        routes.sort(key=lambda r: (0 if r['route_id'] == sel else rank[r['state']], r['route_id']))
        key = (skill_id, target)
        prev = self.selected.get(key)
        if prev != sel:
            self.selected[key] = sel
            if prev is not None:
                self._ex().emit('route_changed', skill_id=skill_id, target=target or '', from_route=prev, to_route=sel or '', graph_seq=rev['seq'])
                inv = self.invocations.get(key)
                if inv and inv['status'] == 'armed':
                    self.invocations.pop(key, None)       # route changed: consent is void, review again
        inv = self.invocations.get(key)
        if inv and inv['status'] == 'armed' and inv['expires'] < self.clock():
            self.invocations.pop(key, None); inv = None
        for r in routes:
            if inv and r['route_id'] == inv['route_id'] and r['route_id'] == sel:
                r['consent'] = 'armed'
        now = self.clock()
        invocation = {'status': 'idle', 'invocation_id': None, 'route_id': None, 'lease_id': None, 'lease_expires_at': None, 'lease_expires_in_s': None}
        if inv and inv['route_id'] == sel:
            invocation = {'status': inv['status'], 'invocation_id': inv['invocation_id'], 'route_id': inv['route_id'], 'lease_id': inv['lease_id'],
                          'lease_expires_at': _iso(inv['expires']), 'lease_expires_in_s': max(0, min(INVOCATION_LEASE_S, int(inv['expires'] - now)))}
        s = SKILLS[skill_id]
        doc = {'schema_version': rc.SCHEMA_VERSION, 'server_time': _iso(now), 'graph_revision': rev,
               'skill': {'skill_id': skill_id, 'version': s['version'], 'reversibility': s['reversibility'], 'idempotent': s['idempotent'], 'consent': s['consent']},
               'policy': {k: pol[k] for k in ('mode', 'failover', 'pinned_route_id', 'set_by')},
               'selected_route_id': sel, 'selection': {'rule': rule, 'decided_at': _iso(now)}, 'invocation': invocation,
               'routes': routes, 'delivery': {'mode': 'poll', 'poll_after_s': 2 if invocation['status'] != 'idle' else 8,
                                              'events_since': self._ex()._seq}}
        return doc

    @staticmethod
    def public(doc):
        return dict(doc, routes=[{k: v for k, v in r.items() if not k.startswith('_')} for r in doc['routes']])

    def skill_routes(self, skill_id, target=None):
        with self._lock:
            doc = self._evaluate(skill_id, target)
            out = self.public(doc)
        self._ex().emit('route_decision', skill_id=skill_id, target=target or '', graph_seq=out['graph_revision']['seq'],
                        selected_route_id=out['selected_route_id'] or '', rule=out['selection']['rule'],
                        candidates=[{'route_id': r['route_id'], 'state': r['state'], 'reason': r['reason']} for r in out['routes']][:32])
        return out

    # ---------- owner policy ----------
    def set_policy(self, body):
        skill_id = body.get('skill_id')
        if skill_id not in SKILLS:
            raise RouteError(404, 'UNKNOWN_SKILL', 'Unknown skill')
        mode, failover = body.get('mode'), body.get('failover', 'none')
        if mode not in ('PINNED', 'PREFERRED', 'AUTO') or failover not in ('none', 'idempotent_read_retry'):
            raise RouteError(400, 'INVALID_POLICY', 'mode PINNED|PREFERRED|AUTO, failover none|idempotent_read_retry')
        s = SKILLS[skill_id]
        if failover != 'none' and not (s['idempotent'] and s['reversibility'] == 'NONE'):
            raise RouteError(400, 'FAILOVER_NOT_ALLOWED', 'Failover retry is only allowed for idempotent read-only skills')
        pinned = body.get('route_id') if mode == 'PINNED' else None
        preferred = body.get('preferred') or []
        if mode == 'PINNED' and not (isinstance(pinned, str) and pinned.startswith('rt-')):
            raise RouteError(400, 'INVALID_POLICY', 'PINNED needs route_id')
        if not isinstance(preferred, list) or len(preferred) > 32 or not all(isinstance(x, str) for x in preferred):
            raise RouteError(400, 'INVALID_POLICY', 'preferred must be a list of route ids')
        with self._lock:
            self.policies[skill_id] = {'mode': mode, 'failover': failover, 'pinned_route_id': pinned, 'preferred': preferred, 'set_by': 'owner'}
            for k in [k for k in self.invocations if k[0] == skill_id and self.invocations[k]['status'] == 'armed']:
                self.invocations.pop(k)                  # a policy change voids armed consent
        self._ex().emit('skill_policy', skill_id=skill_id, mode=mode)
        return self.policies[skill_id]

    # ---------- arm + invoke ----------
    def arm(self, body):
        """Owner consents to one exact invocation on the selected route: returns a 30 s lease bound to it."""
        skill_id, target, params = body.get('skill_id'), body.get('target'), body.get('params') or {}
        if body.get('consent') is not True:
            raise RouteError(400, 'CONSENT_REQUIRED', 'consent: true is required to arm an invocation')
        with self._lock:
            doc = self._evaluate(skill_id, target)
            self._validate_input(skill_id, params)
            route = next((r for r in doc['routes'] if r['route_id'] == body.get('route_id')), None)
            if route is None or route['route_id'] != doc['selected_route_id']:
                raise RouteError(409, 'ROUTE_NOT_SELECTED', 'Only the selected READY route can be armed; review the routes again')
            inv = {'status': 'armed', 'invocation_id': 'inv-' + secrets.token_hex(16), 'route_id': route['route_id'], 'lease_id': 'ls-' + secrets.token_hex(8),
                   'expires': self.clock() + INVOCATION_LEASE_S, 'graph_revision': doc['graph_revision'], 'params': params,
                   'target_identity': self._target_identity(route['_key']), 'authority_rev': route['authority']['authority_rev']}
            self.invocations[(skill_id, target)] = inv
        return {'invocation_id': inv['invocation_id'], 'lease_id': inv['lease_id'], 'route_id': inv['route_id'], 'graph_revision': inv['graph_revision'],
                'lease_expires_at': _iso(inv['expires']), 'lease_expires_in_s': INVOCATION_LEASE_S}

    def _validate_input(self, skill_id, params):
        from src.runtime.primitives import validate, PrimitiveError
        try:
            validate(SKILLS[skill_id]['input'], params)
        except PrimitiveError as e:
            raise RouteError(400, 'INVALID_PARAMS', str(e)) from None

    def invoke(self, body, actor=ACTOR):
        req = {k: body.get(k) for k in ('invocation_id', 'skill_id', 'route_id', 'lease_id', 'graph_revision', 'params', 'consent')}
        extra = set(body) - set(req) - {'target'}
        errs = rc.schema_errors(req, rc.SCHEMA['$defs']['invoke_request']) + ([f'unexpected field {sorted(extra)[0]}'] if extra else [])
        if errs:
            raise RouteError(400, 'INVALID_REQUEST', errs[0])
        if req['consent'] is not True:
            raise RouteError(400, 'CONSENT_REQUIRED', 'consent: true is required')
        target = body.get('target')
        key = (req['skill_id'], target)
        with self._lock:
            inv = self.invocations.get(key)
            known = inv and inv['invocation_id'] == req['invocation_id']
            if not known:
                done = self.completed.get((actor, req['invocation_id']))
                if done is None:
                    raise RouteError(409, 'CONSENT_VOID', 'No armed invocation with this id (expired, voided by a route change, or never armed); review again')
                if done[1] != _fp(dict(req, target=target)):
                    raise RouteError(409, 'INVOCATION_ID_REUSED', 'invocation_id reused with a different skill, route, lease or params')
                b = done[0]
            else:
                b = None
        if b is not None:   # retry of a finished invocation: the ledger returns the original outcome, nothing is dispatched again
            try:
                return dict(self.ledger.run(actor, req['invocation_id'], b, lambda: {'state': 'BLOCKED', 'errors': ['ledger entry expired']}),
                            invocation_id=req['invocation_id'], route_id=req['route_id'], skill_id=req['skill_id'])
            except rc.InvocationIdReused:
                raise RouteError(409, 'INVOCATION_ID_REUSED', 'invocation_id reused with a different binding') from None
        with self._lock:
            inv = self.invocations.get(key)
            if not inv or inv['invocation_id'] != req['invocation_id']:
                raise RouteError(409, 'CONSENT_VOID', 'route changed: review again')
            doc = self._evaluate(req['skill_id'], target)
            route = next((r for r in doc['routes'] if r['route_id'] == req['route_id']), None)
            void = None
            if inv['status'] == 'armed' and inv['expires'] < self.clock():
                void = 'lease expired'
            elif route is None or doc['selected_route_id'] != req['route_id'] or inv['route_id'] != req['route_id']:
                void = 'route changed'
            elif inv['lease_id'] != req['lease_id'] or inv['graph_revision'] != req['graph_revision']:
                void = 'lease or graph revision mismatch'
            elif route['authority']['authority_rev'] != inv['authority_rev'] or self._target_identity(route['_key']) != inv['target_identity']:
                void = 'authority or target changed'
            elif json.dumps(inv['params'], sort_keys=True) != json.dumps(req['params'], sort_keys=True):
                void = 'params edited after consent'
            if void:
                if inv['status'] == 'armed':
                    self.invocations.pop(key, None)
                raise RouteError(409, 'CONSENT_VOID', f'{void}: review again')
            binding = rc.binding_hash(actor, req, inv['target_identity'], inv['authority_rev'])
            inv['status'] = 'executing'
        def dispatch():
            ex = self._ex()
            return ex.execute(route['_primitive'], route['_key'], route['_params'](req['params']), consent=True)
        try:
            receipt = self.ledger.run(actor, req['invocation_id'], binding, dispatch)
        except rc.InvocationIdReused:
            raise RouteError(409, 'INVOCATION_ID_REUSED', 'invocation_id reused with a different binding') from None
        finally:
            with self._lock:
                now = self.clock()
                for k in [k for k, v in self.completed.items() if now - v[2] > self.ledger.ttl_s]:
                    del self.completed[k]
                if len(self.completed) < 4096:
                    self.completed[(actor, req['invocation_id'])] = (binding, _fp(dict(req, target=target)), now)
                if self.invocations.get(key, {}).get('invocation_id') == req['invocation_id']:
                    self.invocations.pop(key, None)
        return dict(receipt, invocation_id=req['invocation_id'], route_id=req['route_id'], skill_id=req['skill_id'])
