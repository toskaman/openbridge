"""Safe primitives registry and executor (contract v1).

Every action a client (UI, Capability Forge, Meta planner) can trigger is one of these primitives. There is no free-form
command: each primitive has a strict input schema, preconditions, a verification step and a declared inverse, and runs
through the existing safety layers (deterministic gate + consent + transaction engine for writes, session journal for
environment changes). The executor enforces schema, consent, identity, concurrency and timeouts, and always returns an
honest TransactionReceipt: a result is `verified` only when an independent read-back confirmed it."""
import secrets
import threading
from collections import deque
from datetime import datetime, timezone

from src.runtime.contract import ActionDescriptor, ReversibilityClass, TransactionReceipt, RecoveryState, to_json
from src.runtime import diagnostics

R = ReversibilityClass


class PrimitiveError(Exception):
    """Refusal before anything was attempted (status: BLOCKED)."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _s(type_, **kw):
    return dict(type=type_, **kw)


PRIMITIVES = {p.primitive_id: p for p in (
    ActionDescriptor('read_facts', 'Read diagnostics from one device',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('read grant on a current link',), ('device present in the graph', 'identity re-verified for ADB devices'),
                     ('none: read-only',), 'each finding names its source; INFERRED findings state their basis', '',
                     R.NONE.value, ('DEVICE_UNAVAILABLE', 'IDENTITY_CHANGED', 'NOT_READABLE'), 60, 'single-per-device', False),
    ActionDescriptor('bounded_discovery', 'Run one bounded local discovery',
                     {'type': 'object', 'properties': {'providers': _s('array', items=_s('string', enum=['mdns', 'ssdp', 'android', 'freebox', 'ble']), maxItems=5)},
                      'additionalProperties': False},
                     (), ('no discovery already running',), ('graph replaced by a fresh snapshot',), 'snapshot returned with per-provider status', '',
                     R.NONE.value, ('BUSY',), 60, 'single-global', False),
    ActionDescriptor('relay_ble_scan', 'Ask a paired Companion relay for a bounded BLE advertisement scan',
                     {'type': 'object', 'properties': {'relay_id': _s('string', maxLength=64), 'seconds': _s('integer', minimum=1, maximum=15)},
                      'required': ['relay_id'], 'additionalProperties': False},
                     ('relay paired (HMAC key)', 'BLUETOOTH_SCAN granted on the relay', 'owner enabled scans'),
                     ('relay online and not busy',), ('advertisements added to the graph with RELAY provenance',),
                     'signed relay report validated (nonce, expiry, bounds)', 'relay_revoke', R.SESSION_CLEANUP.value,
                     ('RELAY_UNAVAILABLE', 'RELAY_PERMISSION', 'BAD_SIGNATURE'), 25, 'single-per-device', True),
    ActionDescriptor('relay_revoke', 'Revoke a paired relay (forget its key and tell it to stop)',
                     {'type': 'object', 'properties': {'relay_id': _s('string', maxLength=64)}, 'required': ['relay_id'], 'additionalProperties': False},
                     (), ('relay known',), ('local key deleted; relay asked to revoke access',), 'relay absent from manager after call', '',
                     R.IRREVERSIBLE.value, ('UNKNOWN_RELAY',), 15, 'single-per-device', True),
    ActionDescriptor('android_optional_app_state', 'Disable one allowlisted optional app for Android user 0 (agent plan)',
                     {'type': 'object', 'properties': {'plan_id': _s('string', maxLength=64)}, 'required': ['plan_id'], 'additionalProperties': False},
                     ('owner consent', 'gate decision ALLOW_WITH_CONSENT'),
                     ('plan produced by the agent for this device', 'identity re-verified', 'exact backup recorded before write'),
                     ('package enabled state = disabled-user',), 'independent pm read-back equals target', 'undo_transaction',
                     R.EXACT.value, ('GATE_DENIED', 'CONSENT_REQUIRED', 'READBACK_MISMATCH', 'DEVICE_UNAVAILABLE'), 60, 'single-per-device', True),
    ActionDescriptor('undo_transaction', 'Restore the exact state saved before a verified transaction',
                     {'type': 'object', 'properties': {'plan_id': _s('string', maxLength=64)}, 'required': ['plan_id'], 'additionalProperties': False},
                     ('owner consent',), ('transaction VERIFIED',), ('state equals the recorded before value',),
                     'independent read-back equals the recorded before value', '', R.EXACT.value,
                     ('NOTHING_TO_UNDO', 'RESTORE_NOT_EXACT'), 60, 'single-per-device', True),
    ActionDescriptor('session_cleanup', 'Restore or keep the environment changes OpenBridge made this session',
                     {'type': 'object', 'properties': {'restore': _s('array', items=_s('string', maxLength=64), maxItems=64)},
                      'required': ['restore'], 'additionalProperties': False},
                     ('owner consent',), ('open session changes exist',), ('selected changes restored, others marked KEPT',),
                     'per-change restore result read back where the device allows it', '', R.SESSION_CLEANUP.value,
                     ('PARTIAL',), 120, 'single-global', True),
)}

GLOBAL_KEY = 'fabric'


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate(schema, value, path='params'):
    """Small strict JSON-schema subset: object/array/string/integer/boolean, enum, bounds, required, no extras."""
    t = schema.get('type')
    ok = {'object': lambda v: isinstance(v, dict), 'array': lambda v: isinstance(v, list),
          'string': lambda v: isinstance(v, str), 'boolean': lambda v: isinstance(v, bool),
          'integer': lambda v: isinstance(v, int) and not isinstance(v, bool)}[t](value)
    if not ok:
        raise PrimitiveError('INVALID_PARAMS', f'{path} must be {t}')
    if 'enum' in schema and value not in schema['enum']:
        raise PrimitiveError('INVALID_PARAMS', f'{path} not allowed')
    if t == 'string' and len(value) > schema.get('maxLength', 256):
        raise PrimitiveError('INVALID_PARAMS', f'{path} too long')
    if t == 'integer' and not schema.get('minimum', value) <= value <= schema.get('maximum', value):
        raise PrimitiveError('INVALID_PARAMS', f'{path} out of range')
    if t == 'array':
        if len(value) > schema.get('maxItems', 64):
            raise PrimitiveError('INVALID_PARAMS', f'{path} too many items')
        for i, v in enumerate(value):
            validate(schema['items'], v, f'{path}[{i}]')
    if t == 'object':
        props = schema.get('properties', {})
        extra = set(value) - set(props)
        if extra and schema.get('additionalProperties') is False:
            raise PrimitiveError('INVALID_PARAMS', f'unexpected field {sorted(extra)[0]!r}')
        for k in schema.get('required', ()):
            if k not in value:
                raise PrimitiveError('INVALID_PARAMS', f'{path}.{k} required')
        for k, v in value.items():
            validate(props[k], v, f'{path}.{k}')


class Executor:
    """Binds primitives to a running server context. `ctx` is the LocalServer (or a test double) exposing
    fabric_registry, fabric_salt, android, relays, agent, session_journal, fabric_lock, fabric_adapters."""
    def __init__(self, ctx, events=256):
        self.ctx = ctx
        self.events = deque(maxlen=events)
        self._seq = 0
        self._locks = {}
        self._guard = threading.Lock()
        self.receipts = {}

    # ---------- events ----------
    def emit(self, kind, **data):
        with self._guard:
            self._seq += 1
            self.events.append(dict(seq=self._seq, at=_now(), kind=kind, **data))

    def events_since(self, seq):
        with self._guard:
            return [e for e in self.events if e['seq'] > seq]

    # ---------- helpers ----------
    def _device(self, key):
        reg = self.ctx.fabric_registry
        if reg is None or key not in reg.devices:
            raise PrimitiveError('DEVICE_UNKNOWN', 'Device not in the current graph; run discovery first')
        return reg.devices[key]

    def _adb_handle(self, key):
        dev = self._device(key)
        live = set(self.ctx.android._handles.values())
        handle = next((h for h in dev.get('handles', {}).values() if h in live), None)
        if handle is None:
            raise PrimitiveError('DEVICE_UNAVAILABLE', 'No live ADB link to this device')
        ident = self.ctx.android.stable_identifier(handle, self.ctx.fabric_salt)
        known = {i.value for i in dev['identifiers'] if i.strong}
        if ident is None:
            raise PrimitiveError('DEVICE_UNAVAILABLE', 'Device identity unreadable (disconnected or unauthorized)')
        if known and ident not in known:
            raise PrimitiveError('IDENTITY_CHANGED', 'A different device now answers on this link; re-run discovery')
        return handle

    def _lock_for(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    # ---------- runners: return (state, before, after, verified, result) ----------
    def _read_facts(self, key, params):
        dev = self._device(key)
        if dev['category'] == 'router':
            session = (self.ctx.fabric_adapters().get('freebox') or {}).get('session')
            if session is None or session.state() != 'AUTHORIZED':
                raise PrimitiveError('NOT_READABLE', 'Freebox app not authorized (read-only authorization required)')
            facts = diagnostics.freebox(session)
        elif dev['category'] in ('phone', 'tv', 'android'):
            handle = self._adb_handle(key)
            serial = next(s for s, h in self.ctx.android._handles.items() if h == handle)
            def read(*a):
                if a not in diagnostics.ANDROID_READS:
                    raise ValueError('not in read allowlist')
                return self.ctx.android._run(['-s', serial, 'shell', *a])
            facts = diagnostics.android(read)
        else:
            reg = self.ctx.fabric_registry
            facts = [diagnostics.finding(f, reg.best_value(key, f).value, source=', '.join(sorted(obs))[:80])
                     for f, obs in sorted(dev['observations'].items())
                     if reg.best_value(key, f) is not None and not f.startswith(('mac', 'serial', 'ip', 'address'))][:50]
        return 'VERIFIED', None, None, True, {'facts': facts}

    def _bounded_discovery(self, key, params):
        from src.fabric import discovery
        if not self.ctx.fabric_lock.acquire(blocking=False):
            raise PrimitiveError('BUSY', 'A discovery is already running')
        try:
            snap, reg = discovery.run(self.ctx.fabric_adapters(), self.ctx.fabric_salt,
                                      providers=tuple(params.get('providers') or ('mdns', 'ssdp', 'android', 'freebox')))
        finally:
            self.ctx.fabric_lock.release()
        self.ctx.fabric_snapshot, self.ctx.fabric_registry = snap, reg
        return 'VERIFIED', None, {'devices': len(snap['devices'])}, True, {'providers': snap.get('providers', {})}

    def _relay_ble_scan(self, key, params):
        from src.fabric.relay import RelayError
        relay = self.ctx.relays.relays.get(params['relay_id'])
        if relay is None:
            raise PrimitiveError('RELAY_UNAVAILABLE', 'Unknown relay')
        if self.ctx.fabric_registry is None or relay['device_key'] not in {h for d in self.ctx.fabric_registry.devices.values() for h in d.get('handles', {}).values()} \
                or relay['device_key'] not in self._device(key).get('handles', {}).values():
            raise PrimitiveError('RELAY_UNAVAILABLE', 'Relay does not belong to this device')
        try:
            snap = self.ctx.relay_action('/api/relay-scan', {'relay_id': params['relay_id'], 'seconds': params.get('seconds', 8)})
        except RelayError as e:
            raise PrimitiveError('RELAY_PERMISSION' if 'permission' in str(e).lower() else 'RELAY_UNAVAILABLE', str(e)) from None
        n = (snap.get('providers', {}).get('relay') or {}).get('devices', 0)
        return 'VERIFIED', None, {'advertisers': n}, True, {'advertisers': n}

    def _relay_revoke(self, key, params):
        rid = params['relay_id']
        if rid not in self.ctx.relays.relays:
            raise PrimitiveError('UNKNOWN_RELAY', 'Unknown relay')
        self.ctx.relays.revoke(rid)
        gone = rid not in self.ctx.relays.relays
        return ('VERIFIED' if gone else 'FAILED'), 'paired', ('revoked' if gone else 'paired'), gone, {}

    def _agent(self):
        if self.ctx.agent is None:
            raise PrimitiveError('AGENT_DISABLED', 'Physical agent disabled (start with --local-meta --agent)')
        return self.ctx.agent

    def _app_state(self, key, params):
        from src.core.agent import AgentBlocked
        agent = self._agent()
        handle = self._adb_handle(key)
        plan = agent._get(params['plan_id'])
        if plan.get('handle') != handle:
            raise PrimitiveError('PLAN_DEVICE_MISMATCH', 'Plan was made for another device')
        try:
            r = agent.execute(params['plan_id'], True)
        except AgentBlocked as e:
            raise PrimitiveError('BLOCKED', str(e)) from None
        return r['state'], r['before_code'], r['observed_code'], bool(r['verified']), {'package': r['package']}

    def _undo(self, key, params):
        from src.core.agent import AgentBlocked
        agent = self._agent()
        self._adb_handle(key)
        try:
            r = agent.undo(params['plan_id'])
        except AgentBlocked as e:
            raise PrimitiveError('RESTORE_NOT_EXACT' if 'exact' in str(e).lower() else 'NOTHING_TO_UNDO', str(e)) from None
        return 'REVERTED', None, r['restored_code'], bool(r['exact']), {}

    def _session_cleanup(self, key, params):
        from src.fabric.session import restore
        results, failed = [], 0
        for change in self.ctx.session_journal.open_changes():
            if change['id'] in params['restore']:
                try:
                    state, detail = restore(change, self.ctx.android._run)
                except (ValueError, OSError) as error:
                    state, detail = 'FAILED', str(error)[:120]
                if state != 'FAILED':
                    self.ctx.session_journal.close(change['id'], state, detail)
                else:
                    failed += 1
            else:
                state, detail = 'KEPT', 'Kept by the owner'
                self.ctx.session_journal.close(change['id'], 'KEPT', detail)
            results.append({'id': change['id'], 'title': change['title'], 'state': state, 'detail': detail})
        return ('VERIFIED' if not failed else 'PARTIAL'), None, None, not failed, {'results': results}

    RUNNERS = {'read_facts': _read_facts, 'bounded_discovery': _bounded_discovery, 'relay_ble_scan': _relay_ble_scan,
               'relay_revoke': _relay_revoke, 'android_optional_app_state': _app_state, 'undo_transaction': _undo,
               'session_cleanup': _session_cleanup}

    # ---------- entry point ----------
    def execute(self, primitive_id, device_key, params, consent=False):
        started, tx = _now(), 'tx-' + secrets.token_hex(8)
        p = PRIMITIVES.get(primitive_id)
        def receipt(state, before=None, after=None, verified=False, errors=(), result=None):
            r = TransactionReceipt(tx, primitive_id, str(device_key)[:64], state, before, after, verified, started, _now(), tuple(errors))
            self.receipts[tx] = r
            self.emit('receipt', transaction_id=tx, primitive_id=primitive_id, state=state, verified=verified)
            return dict(to_json(r), result=result or {})
        try:
            if p is None:
                raise PrimitiveError('UNKNOWN_PRIMITIVE', 'Unknown primitive (no free-form commands)')
            if not isinstance(device_key, str) or not device_key or len(device_key) > 64:
                raise PrimitiveError('INVALID_PARAMS', 'device_key required')
            validate(p.input_schema, params if params is not None else {})
            if p.requires_consent and consent is not True:
                raise PrimitiveError('CONSENT_REQUIRED', 'Owner consent is required for this primitive')
        except PrimitiveError as e:
            return receipt('BLOCKED', errors=(f'{e.code}: {e}',))
        lock = self._lock_for(GLOBAL_KEY if p.concurrency == 'single-global' else device_key)
        if not lock.acquire(blocking=False):
            return receipt('BLOCKED', errors=('CONCURRENT: another primitive is running on this target',))
        box, done = {}, threading.Event()
        def work():
            try:
                box['r'] = self.RUNNERS[primitive_id](self, device_key, params or {})
            except PrimitiveError as e:
                box['e'] = ('BLOCKED', f'{e.code}: {e}')
            except Exception as e:  # adapter failure mid-operation: honest FAILED, never success
                box['e'] = ('FAILED', f'{type(e).__name__}: {str(e)[:160]}')
            finally:
                done.set()
                lock.release()
        self.emit('started', transaction_id=tx, primitive_id=primitive_id)
        threading.Thread(target=work, daemon=True).start()
        if not done.wait(p.timeout_s):
            # The worker keeps the lock until it really ends: no second action can race the unfinished one.
            return receipt('UNKNOWN_TIMEOUT', errors=(f'TIMEOUT: no result after {p.timeout_s}s; state not verified, check recovery',))
        if 'e' in box:
            return receipt(box['e'][0], errors=(box['e'][1],))
        state, before, after, verified, result = box['r']
        return receipt(state, before, after, verified, result=result)

    def recovery(self):
        pending = tuple(t for t, r in self.receipts.items() if r.state in ('UNKNOWN_TIMEOUT', 'FAILED', 'PARTIAL'))
        open_changes = tuple(c['id'] for c in self.ctx.session_journal.open_changes())
        return RecoveryState(pending, open_changes, '' if not pending else 'some transactions ended without verification')
