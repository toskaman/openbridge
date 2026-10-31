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
ACTOR = 'owner'                     # the local UI; B3 remote controls act as 'relay:<relay_id>'

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
    'screen_capture': {'version': 1, 'reversibility': 'NONE', 'idempotent': True, 'consent': 'per_invocation', 'targeted': True,
                       'input': {'type': 'object', 'properties': {'label': {'type': 'string', 'maxLength': 64}}, 'additionalProperties': False},
                       'plain': 'Capture one screenshot PNG now and store it on this PC under a capture id.'},
    # Skill-level IRREVERSIBLE is the conservative B2-contract label (it has no MANUAL yet);
    # the primitives stay MANUAL: deleting the pushed file on the device undoes the change.
    'capture_send': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': False, 'consent': 'per_invocation', 'targeted': True,
                     'input': {'type': 'object', 'properties': {'capture_id': {'type': 'string', 'maxLength': 32}, 'name': {'type': 'string', 'maxLength': 64}}, 'required': ['capture_id'], 'additionalProperties': False},
                     'plain': 'Push a stored capture to /sdcard/OpenBridge/ on this device, hash-verified. Undo: delete the file on the device.'},
    'capture_montage': {'version': 1, 'reversibility': 'NONE', 'idempotent': True, 'consent': 'none', 'targeted': False,
                        'input': {'type': 'object', 'properties': {'capture_ids': {'type': 'array', 'maxItems': 16, 'items': {'type': 'string', 'maxLength': 32}}, 'layout': {'type': 'string', 'enum': ['row', 'grid']}}, 'required': ['capture_ids'], 'additionalProperties': False},
                        'plain': 'Combine stored captures into one PNG on this PC (row or grid). No new device capture is made.'},
    'file_pull': {'version': 1, 'reversibility': 'NONE', 'idempotent': True, 'consent': 'per_invocation', 'targeted': True,
                  'input': {'type': 'object', 'properties': {'remote': {'type': 'string', 'maxLength': 256}}, 'required': ['remote'], 'additionalProperties': False},
                  'plain': 'Copy one file from under /sdcard/ to this PC. The device is not modified.'},
    'file_push': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': False, 'consent': 'per_invocation', 'targeted': True,
                  'input': {'type': 'object', 'properties': {'transfer_id': {'type': 'string', 'maxLength': 32}, 'name': {'type': 'string', 'maxLength': 64}}, 'required': ['transfer_id', 'name'], 'additionalProperties': False},
                  'plain': 'Push stored bytes to /sdcard/OpenBridge/<name> on this device, hash-verified. Undo: delete the file on the device.'},
    'app_launch': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': False, 'consent': 'per_invocation', 'targeted': True,
                   'input': {'type': 'object', 'properties': {'package': {'type': 'string', 'maxLength': 120}}, 'required': ['package'], 'additionalProperties': False},
                   'plain': 'Launch one app package on this Android device.'},
    'capability_probe': {'version': 1, 'reversibility': 'NONE', 'idempotent': True, 'consent': 'none', 'targeted': True,
                         'input': {'type': 'object', 'properties': {}, 'additionalProperties': False},
                         'plain': 'Measure which typed actions this Android device supports (read-only probe).'},
    'vacuum_command': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': False, 'consent': 'per_invocation', 'targeted': True,
                       'input': {'type': 'object', 'properties': {'command': {'type': 'string', 'enum': ['start', 'pause', 'mode', 'dock', 'move', 'seek', 'empty_dust', 'reset_side_brush', 'reset_main_brush', 'reset_filter', 'water_level', 'work_mode']}, 'value': {'type': 'string', 'maxLength': 16}, 'move_s': {'type': 'number'}}, 'required': ['command'], 'additionalProperties': False},
                       'plain': 'Send one typed command to the Tuya robot. Momentary commands report verified=null.'},
    'retro_command': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': False, 'consent': 'per_invocation', 'targeted': False,
                      'input': {'type': 'object', 'properties': {'command': {'type': 'string', 'enum': ['VERSION', 'GET_STATUS', 'PAUSE_TOGGLE', 'VOLUME_UP', 'VOLUME_DOWN']}}, 'required': ['command'], 'additionalProperties': False},
                      'plain': 'Send one allowlisted command to the RetroArch running on this PC (loopback only).'},
    'pc_run': {'version': 1, 'reversibility': 'IRREVERSIBLE', 'idempotent': False, 'consent': 'per_invocation', 'targeted': True,
               'input': {'type': 'object', 'properties': {'command': {'type': 'string', 'maxLength': 2000}, 'shell': {'type': 'string', 'enum': ['cmd', 'powershell']}, 'timeout_s': {'type': 'integer', 'minimum': 1, 'maximum': 600}}, 'required': ['command'], 'additionalProperties': False},
               'plain': 'Run one owner-confirmed command on this Windows PC via its agent. Use inside an approval-gated workflow.'},
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
        self._inflight = set()         # (actor, invocation_id) between lease checks and ledger handoff (same-process joiners skip the journal claim)
        self._lock = threading.RLock()
        from src.runtime.state_store import StateStore
        self._store = StateStore.for_server(server)
        self._state_error = ''
        self._refresh_state()
        if self._store is not None and not self._state_error:
            from src.runtime.state_store import StateError
            try:                       # a restart must not re-execute a re-sent id: DONE rows refuse as duplicates,
                for row in self._store.load_invocations(time.time()):   # leftover EXECUTING rows (fingerprint None) refuse as uncertain
                    self.completed[(row['actor'], row['invocation_id'])] = (None, row.get('fingerprint'), self.clock())
            except StateError as error:
                self._state_error = str(error)

    def _refresh_state(self):
        if self._store is None or self._state_error:
            return
        try:
            saved = self._store.load().get('policies', {})
        except OSError as error:
            self._state_error = str(error)
            return
        if saved != self.policies:
            for key in list(self.invocations):
                if self.invocations[key]['status'] == 'armed' and saved.get(key[0]) != self.policies.get(key[0]):
                    self.invocations.pop(key)
            self.policies = saved

    def _require_state(self):
        self._refresh_state()
        if self._state_error:
            ex = getattr(self.server, 'runtime_executor', None)
            if ex is not None:
                ex._state_error = self._state_error
            raise RouteError(503, self._state_error.split(':', 1)[0], self._state_error)

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
                entry = (led.routes.get(rid) or {}) if led else {}
                last_ok = entry.get('last_success_at')
                proof = max([x for x in (last_ok, entry.get('last_proof_at')) if x is not None], default=None)
                reason = detail = None
                if not r.get('online'):
                    reason = 'link_down'
                elif GRANT_RANK.get(g, -1) < GRANT_RANK['control']:
                    reason, detail = 'grant_insufficient', {'missing_grant': 'control', 'hop_index': 0, 'blocking_device_key': None}
                elif not r['permissions'].get('BLUETOOTH_SCAN'):
                    reason, detail = 'grant_insufficient', {'missing_grant': 'control', 'hop_index': 1, 'blocking_device_key': key}
                elif not r['permissions'].get('owner_enabled'):
                    reason = 'policy_blocked'
                else:
                    last = self._last_receipt('relay_ble_scan', key)
                    if last and last['state'] in ('UNKNOWN_TIMEOUT', 'PARTIAL') and not (last_ok and last_ok >= _epoch(last['finished_at'])):
                        reason = 'backend_unknown'   # uncertain outcome: unavailable until a successful read-back
                route = self._route(skill_id, snap, key, hops, 'op:relay_ble_scan', 'relay_ble_scan', proof if proof else self.clock(),
                                    LEASE_S['RELAY'], 'relay ledger' if last_ok else 'signed relay reply (no scan yet)', reason, detail)
                if not last_ok:
                    route['_age'] = LEASE_S['RELAY']   # never scanned: ranks after any proven relay, deterministically
                route['_params'] = lambda p, rid=rid: {'relay_id': rid, 'seconds': p.get('seconds', 8)}
                out.append(route)
            return out
        if skill_id == 'capture_montage':
            # Server-local compute: the 'fabric' hop runs on this PC, no device link needed.
            hops = [{'device_key': 'fabric', 'transport': 'LAN', 'primitive_id': 'capture_montage',
                     'grant': 'read', 'required_grant': 'read'}]
            r = self._route(skill_id, snap, 'fabric', hops, 'op:capture_montage', 'capture_montage',
                            self.clock(), LEASE_S['LAN'], 'server-local compute', None, None)
            r['_params'] = lambda p: {'capture_ids': list(p['capture_ids']), 'layout': p.get('layout', 'row')}
            return [r]
        if skill_id == 'retro_command':
            hops = [{'device_key': 'fabric', 'transport': 'LAN', 'primitive_id': 'retro_command',
                     'grant': 'read', 'required_grant': 'read'}]
            r = self._route(skill_id, snap, 'fabric', hops, 'op:retro_command', 'retro_command',
                            self.clock(), LEASE_S['LAN'], 'localhost RetroArch', None, None)
            r['_params'] = lambda p: {'command': p['command']}
            return [r]
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
        if skill_id in ('screen_capture', 'file_pull', 'capture_send', 'file_push', 'app_launch', 'capability_probe'):
            # §7 media/file/action skills: ADB link (USB, Wi-Fi or emulator); reads need 'read', writes need 'control'.
            if d.get('category') not in ANDROID:
                return out
            adb = link is not None and link['transport'] in ('USB', 'WIFI', 'EMULATOR') and bool(d.get('handles'))
            prim = {'app_launch': 'device_action', 'capability_probe': 'device_capabilities'}.get(skill_id, skill_id)
            need = 'read' if skill_id in ('screen_capture', 'file_pull', 'capability_probe') else 'control'
            hops = [{'device_key': target, 'transport': tr, 'primitive_id': prim, 'grant': g, 'required_grant': need}]
            reason = detail = None
            if not adb:
                reason = 'link_down'
            elif GRANT_RANK.get(g, -1) < GRANT_RANK[need]:
                reason, detail = 'grant_insufficient', {'missing_grant': need, 'hop_index': 0, 'blocking_device_key': None}
            op = {'app_launch': 'op:device_action:launch_app', 'capability_probe': 'op:device_capabilities'}.get(skill_id, 'op:' + skill_id)
            r = self._route(skill_id, snap, target, hops, op, prim, observed,
                            LEASE_S.get(tr, 60), 'adb discovery', reason, detail)
            r['_params'] = {'screen_capture': lambda p: {'label': p['label']} if 'label' in p else {},
                            'file_pull': lambda p: {'remote': p['remote']},
                            'capture_send': lambda p: dict(p, name=p.get('name') or (p['capture_id'] + '.png')),
                            'file_push': lambda p: {'transfer_id': p['transfer_id'], 'name': p['name']},
                            'app_launch': lambda p: {'action': 'launch_app', 'args': {'package': p['package']}},
                            'capability_probe': lambda p: {}}[skill_id]
            return [r]
        if skill_id == 'vacuum_command':
            if d.get('category') != 'vacuum':
                return out
            hops = [{'device_key': target, 'transport': tr, 'primitive_id': 'tuya_command', 'grant': g, 'required_grant': 'control'}]
            reason = detail = None
            if link is None:
                reason = 'link_down'
            elif GRANT_RANK.get(g, -1) < GRANT_RANK['control']:
                reason, detail = 'grant_insufficient', {'missing_grant': 'control', 'hop_index': 0, 'blocking_device_key': None}
            r = self._route(skill_id, snap, target, hops, 'op:tuya_command', 'tuya_command', observed,
                            LEASE_S.get(tr, 300), 'tuya discovery', reason, detail)
            r['_params'] = lambda p: {'command': p['command'], **({'value': p['value']} if 'value' in p else {}),
                                      **({'move_s': p['move_s']} if 'move_s' in p else {})}
            return [r]
        if skill_id == 'pc_run':
            # The graph grants computers at most 'read' (ingest design: run_command is
            # BLOCKED for autonomous use). Routing over the read link is honest here
            # because the write itself is gated by per-invocation consent at the Router
            # AND an approval step in §7 workflows, plus the primitive's own consent gate.
            agent = link is not None and bool((d.get('handles') or {}).get('WINDOWS_AGENT'))
            hops = [{'device_key': target, 'transport': tr, 'primitive_id': 'pc_job', 'grant': g, 'required_grant': 'read'}]
            reason = detail = None
            if d.get('category') != 'computer' or not agent:
                reason = 'link_down'
            elif GRANT_RANK.get(g, -1) < GRANT_RANK['read']:
                reason, detail = 'grant_insufficient', {'missing_grant': 'read', 'hop_index': 0, 'blocking_device_key': None}
            r = self._route(skill_id, snap, target, hops, 'op:pc_job', 'pc_job', observed,
                            LEASE_S.get(tr, 300), 'windows agent discovery', reason, detail)
            r['_params'] = lambda p: {'command': p['command'], 'shell': p.get('shell', 'powershell'),
                                      'timeout_s': p.get('timeout_s', 120)}
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
        self._require_state()
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

    def resolve_target(self, target):
        """Map a label (or live key) to the current live device key.

        Keys rotate every discovery, so labels are the stable reference stored
        in specs; resolution happens here, at dispatch, against the live
        snapshot. Ghost rows collapse by the shared nl_plan rule, openly."""
        snap = self._snap()
        devices = snap.get('devices', []) if isinstance(snap, dict) else []
        if target == 'fabric' or any(d.get('key') == target for d in devices):
            return target
        from src.runtime import nl_plan
        try:
            _, key, _ = nl_plan.resolve_target(target, devices)
        except nl_plan.PlanError as e:
            raise RouteError(404, 'TARGET_UNRESOLVED', str(e))
        return key

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
        policy = {'mode': mode, 'failover': failover, 'pinned_route_id': pinned, 'preferred': preferred, 'set_by': 'owner'}
        with self._lock:
            self._require_state()
            if self._store is not None:
                try:
                    self._store.set_policy(skill_id, policy)
                except OSError as error:
                    self._state_error = str(error)
                    self._require_state()
            self.policies[skill_id] = policy
            for k in [k for k in self.invocations if k[0] == skill_id and self.invocations[k]['status'] == 'armed']:
                self.invocations.pop(k)
        self._ex().emit('skill_policy', skill_id=skill_id, mode=mode)
        return policy

    # ---------- arm + invoke ----------
    def arm(self, body, actor=ACTOR, invocation_id=None):
        """One consented invocation on the selected route: returns a 30 s lease bound to it and to the actor.
        Internal actors (B3 remote controls) pass an invocation id derived from their request id, so a re-sent press
        is recognised and never dispatched twice."""
        skill_id, target, params = body.get('skill_id'), body.get('target'), body.get('params') or {}
        if body.get('consent') is not True:
            raise RouteError(400, 'CONSENT_REQUIRED', 'consent: true is required to arm an invocation')
        with self._lock:
            done = self.completed.get((actor, invocation_id)) if invocation_id is not None else None
            if done is not None:
                if done[1] is None:    # journal EXECUTING row with no DONE: a crash interrupted it; never re-arm it
                    raise RouteError(409, 'UNCERTAIN_OUTCOME', 'A previous invocation with this id was interrupted; use a fresh invocation id')
                raise RouteError(409, 'DUPLICATE_REQUEST', 'This request was already handled')
            doc = self._evaluate(skill_id, target)
            self._validate_input(skill_id, params)
            route = next((r for r in doc['routes'] if r['route_id'] == body.get('route_id')), None)
            if route is None or route['route_id'] != doc['selected_route_id']:
                raise RouteError(409, 'ROUTE_NOT_SELECTED', 'Only the selected READY route can be armed; review the routes again')
            inv = {'status': 'armed', 'actor': actor, 'invocation_id': invocation_id or 'inv-' + secrets.token_hex(16), 'route_id': route['route_id'], 'lease_id': 'ls-' + secrets.token_hex(8),
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
        with self._lock:
            self._require_state()
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
            known = inv and inv['invocation_id'] == req['invocation_id'] and inv.get('actor', ACTOR) == actor   # another actor cannot use this lease
            if not known:
                done = self.completed.get((actor, req['invocation_id']))
                if done is None:
                    raise RouteError(409, 'CONSENT_VOID', 'No armed invocation with this id (expired, voided by a route change, or never armed); review again')
                if done[1] is None:
                    raise RouteError(409, 'UNCERTAIN_OUTCOME', 'A previous invocation with this id was interrupted; use a fresh invocation id')
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
            if not inv or inv['invocation_id'] != req['invocation_id'] or inv.get('actor', ACTOR) != actor:
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
            ikey = (actor, req['invocation_id'])
            join = ikey in self._inflight
            if not join:
                self._inflight.add(ikey)
        def dispatch():
            ex = self._ex()
            return ex.execute(route['_primitive'], route['_key'], route['_params'](req['params']), consent=True)
        if not join and self._store is not None:      # pre-dispatch journal claim (atomic cross-process admission);
            from src.runtime.state_store import StateError   # same-process joiners skip it and let the ledger hand them the one result
            try:
                claimed, row = self._store.claim_invocation(actor, req['invocation_id'], time.time())
            except StateError as error:
                with self._lock:
                    self._inflight.discard(ikey)
                raise RouteError(503, error.code, str(error)) from None
            if not claimed:
                with self._lock:
                    self._inflight.discard(ikey)
                    self.completed[ikey] = (binding, row.get('fingerprint'), self.clock())
                if row['state'] == 'DONE':
                    raise RouteError(409, 'DUPLICATE_REQUEST', 'This request was already handled')
                raise RouteError(409, 'UNCERTAIN_OUTCOME', 'An invocation with this id is already running elsewhere or was interrupted; use a fresh invocation id')
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
                self._inflight.discard((actor, req['invocation_id']))
            if self._store is not None:
                from src.runtime.state_store import StateError
                try:
                    self._store.finish_invocation(actor, req['invocation_id'], _fp(dict(req, target=target)), time.time())
                except StateError as error:
                    self._state_error = str(error)   # durability unproven: block further changing ops until review + restart
        return dict(receipt, invocation_id=req['invocation_id'], route_id=req['route_id'], skill_id=req['skill_id'])
