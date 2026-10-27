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
                     {'type': 'object', 'properties': {'providers': _s('array', items=_s('string', enum=['mdns', 'ssdp', 'android', 'freebox', 'ble', 'windows', 'tuya']), maxItems=7)},
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
    ActionDescriptor('watch_start', 'Watch one diagnostic finding on a device and raise an event when it crosses a threshold',
                     {'type': 'object', 'properties': {
                         'finding': _s('string', maxLength=48), 'op': _s('string', enum=['lt', 'le', 'gt', 'ge', 'eq', 'ne']),
                         'threshold_number': _s('number'), 'threshold_text': _s('string', maxLength=32),
                         'interval_s': _s('integer', minimum=30, maximum=3600), 'lifetime_s': _s('integer', minimum=30, maximum=86400)},
                      'required': ['finding', 'op', 'interval_s'], 'additionalProperties': False},
                     ('owner consent',), ('device present in the graph', 'at most 16 running watches'),
                     ('periodic read_facts on this device; events only, never an action',),
                     'watch listed RUNNING in /api/v2/watches; every run is a normal read_facts receipt', 'watch_stop',
                     R.SESSION_CLEANUP.value, ('INVALID_WATCH', 'DEVICE_UNKNOWN'), 10, 'single-global', True),
    ActionDescriptor('diagnostic_report', 'Read every readable device once and build a redacted report',
                     {'type': 'object', 'properties': {'redact': _s('boolean')}, 'additionalProperties': False},
                     ('read grants of each device',), ('graph exists',), ('none: read-only',),
                     'each device section is a normal read_facts receipt (state + verified)', '', R.NONE.value,
                     ('DEVICE_UNKNOWN',), 120, 'single-global', False),
    ActionDescriptor('diagnostic_probe', 'Re-measure a few devices a bounded number of times and update the timeline hypotheses (read-only)',
                     {'type': 'object', 'properties': {
                         'device_keys': _s('array', items=_s('string', maxLength=64), maxItems=4),
                         'samples': _s('integer', minimum=1, maximum=5), 'interval_s': _s('integer', minimum=2, maximum=30),
                         'window_s': _s('integer', minimum=10, maximum=600)},
                      'required': ['device_keys'], 'additionalProperties': False},
                     ('read grants of each device',), ('devices present in the graph', 'samples x interval <= 120 s'),
                     ('none: read-only; timeline gains the new samples',),
                     'every sample is a normal read_facts receipt; hypotheses recomputed before/after', '', R.NONE.value,
                     ('DEVICE_UNKNOWN', 'INVALID_PARAMS'), 180, 'single-global', False),
    ActionDescriptor('visual_readback', 'Capture one screenshot and compare a local Muse Glimmer reading with the structured screen state',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('owner consent (screenshots are sensitive)', 'read grant on a current ADB link'),
                     ('identity re-verified', 'local Glimmer only; no cloud path'),
                     ('none: read-only; frame kept as a hash only',),
                     'CONFIRMED only when structured read and screenshot agree; disagreement is INCONCLUSIVE', '', R.NONE.value,
                     ('DEVICE_UNAVAILABLE', 'IDENTITY_CHANGED'), 330, 'single-per-device', True),
    ActionDescriptor('tuya_setting', 'Change one allowlisted Tuya vacuum setting (suction or volume) with read-back',
                     {'type': 'object', 'properties': {'setting': _s('string', enum=['suction', 'volume']), 'value': _s('string', maxLength=16)},
                      'required': ['setting', 'value'], 'additionalProperties': False},
                     ('owner consent', 'owner-linked Tuya key'), ('robot idle or docked', 'value in the setting allowlist'),
                     ('setting equals the requested value',), 'independent status read equals target', 'tuya_undo', R.EXACT.value,
                     ('NOT_LINKED', 'BLOCKED', 'READBACK_MISMATCH'), 30, 'single-per-device', True),
    ActionDescriptor('tuya_undo', 'Restore the Tuya setting value recorded before the change',
                     {'type': 'object', 'properties': {'setting': _s('string', enum=['suction', 'volume'])}, 'required': ['setting'], 'additionalProperties': False},
                     ('owner consent',), ('a change was recorded',), ('setting equals the recorded before value',),
                     'independent status read equals before value', '', R.EXACT.value, ('NOTHING_TO_UNDO', 'RESTORE_NOT_EXACT'), 30, 'single-per-device', True),
    ActionDescriptor('tuya_command', 'Send one typed command to the Tuya robot (start, pause, dock, mode, move, seek, empty dust, resets, water, work mode)',
                     {'type': 'object', 'properties': {'command': _s('string', enum=['start', 'pause', 'mode', 'dock', 'move', 'seek', 'empty_dust',
                                                                                        'reset_side_brush', 'reset_main_brush', 'reset_filter', 'water_level', 'work_mode']),
                                                       'value': _s('string', maxLength=16), 'move_s': _s('number')},
                      'required': ['command'], 'additionalProperties': False},
                     ('owner consent for this command',), ('owner-linked Tuya key', 'value in the command allowlist', 'manual moves end with stop after <= 3 s'),
                     ('device acted on the command',), 'status read after the command; momentary commands report verified=null', '',
                     R.IRREVERSIBLE.value, ('NOT_LINKED', 'BLOCKED'), 30, 'single-per-device', True),
    ActionDescriptor('pc_job', 'Run one owner-typed command on a client PC through its BridgeWindows agent',
                     {'type': 'object', 'properties': {'command': _s('string', maxLength=2000), 'shell': _s('string', enum=['cmd', 'powershell']),
                                                       'timeout_s': _s('integer', minimum=1, maximum=600)},
                      'required': ['command'], 'additionalProperties': False},
                     ('owner consent for this exact command',), ('agent connected', 'identity re-verified'),
                     ('the command ran once on that PC',), 'exit code and captured output returned; nothing is retried', '',
                     R.IRREVERSIBLE.value, ('DEVICE_UNAVAILABLE', 'IDENTITY_CHANGED', 'FAILED'), 630, 'single-per-device', True),
    ActionDescriptor('watch_stop', 'Stop a watch',
                     {'type': 'object', 'properties': {'watch_id': _s('string', maxLength=32)}, 'required': ['watch_id'], 'additionalProperties': False},
                     (), ('watch exists',), ('no further reads',), 'watch state STOPPED', '', R.NONE.value, ('UNKNOWN_WATCH',), 10, 'single-global', False),
)}

GLOBAL_KEY = 'fabric'


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def validate(schema, value, path='params'):
    """Small strict JSON-schema subset: object/array/string/integer/boolean, enum, bounds, required, no extras."""
    t = schema.get('type')
    ok = {'object': lambda v: isinstance(v, dict), 'array': lambda v: isinstance(v, list),
          'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e12,
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
            ev = dict(seq=self._seq, at=_now(), kind=kind, **data)
            self.events.append(ev)
        try:
            self.timeline().ingest_event(ev, self._category(ev.get('device_key', '')))
        except Exception:
            pass

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
        known = {i.value for i in dev['identifiers'] if i.strong}
        handle = next((h for h in dev.get('handles', {}).values() if h in live), None)
        if handle is None and known:
            # Re-attach by strong identity only (ADB issues a new handle after a reconnect).
            for h in sorted(live):
                if self.ctx.android.stable_identifier(h, self.ctx.fabric_salt) in known:
                    handle = h
                    transport = next((t for t, x in dev.get('handles', {}).items()), 'ADB')
                    dev.setdefault('handles', {})[transport] = h
                    self.emit('reattached', device_key=key)
                    break
        if handle is None:
            raise PrimitiveError('DEVICE_UNAVAILABLE', 'No live ADB link to this device')
        ident = self.ctx.android.stable_identifier(handle, self.ctx.fabric_salt)
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
        if dev['category'] == 'router' and dev.get('igd_location') and not any(via == 'FREEBOX_API' for _, via in dev['capabilities']):
            from src.adapters import upnp_igd
            from src.fabric.mdns import default_scope
            try:
                status = (getattr(self.ctx, 'igd_read', None) or upnp_igd.read)(dev['igd_location'], default_scope())
            except (upnp_igd.IGDBlocked, OSError, ValueError, SyntaxError) as e:
                raise PrimitiveError('NOT_READABLE', f'IGD not readable: {type(e).__name__}') from None
            facts = diagnostics.igd(status)
        elif dev['category'] == 'router' and any(n == 'lan_inventory' and via == 'FREEBOX_API' for n, via in dev['capabilities']):
            session = (self.ctx.fabric_adapters(('freebox',)).get('freebox') or {}).get('session')
            if session is None or session.state() != 'AUTHORIZED':
                raise PrimitiveError('NOT_READABLE', 'Freebox app not authorized (read-only authorization required)')
            facts = diagnostics.freebox(session)
        elif dev['category'] == 'vacuum':
            facts = [diagnostics.finding(f['name'], f['value'], f['unit'], 'Tuya local protocol') for f in self._tuya().facts()]
        elif any(n == 'windows_diagnostics' for n, _ in dev['capabilities']):
            bridge = (self.ctx.fabric_adapters(('windows',)) or {}).get('windows')
            if bridge is None or not bridge.connected():
                raise PrimitiveError('DEVICE_UNAVAILABLE', 'Windows agent not connected')
            known = {i.value for i in dev['identifiers'] if i.strong}
            try:
                ident = bridge.identity(self.ctx.fabric_salt)
            except ValueError as e:
                raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:80]) from None
            if ident not in known:
                raise PrimitiveError('IDENTITY_CHANGED', 'A different Windows PC is now connected; re-run discovery')
            facts = diagnostics.windows(bridge.call)
        elif dev['category'] in ('phone', 'tv', 'android', 'watch'):
            handle = self._adb_handle(key)
            serial = next(s for s, h in self.ctx.android._handles.items() if h == handle)
            def read(*a):
                if a not in diagnostics.ANDROID_READS:
                    raise ValueError('not in read allowlist')
                big = a in diagnostics.LARGE_READS     # verbose system dumps, still allowlisted and capped
                return self.ctx.android._run(['-s', serial, 'shell', *a], **({'max_bytes': 2097152} if big else {}))
            failures = []
            def counted(*a):
                try:
                    return read(*a)
                except (ValueError, OSError) as e:
                    failures.append(str(e)[:80]); raise
            facts = diagnostics.android(counted)
            manifest = None
            if dev['category'] == 'watch':
                from src.fabric import wear_manifest
                try:
                    pm = counted('pm', 'list', 'features')
                except (ValueError, OSError):
                    pm = ''
                manifest = wear_manifest.build(pm, facts)
            # Link check after the reads: a read set cut short by a lost link is PARTIAL, never VERIFIED.
            try:
                self.ctx.android.discover()
                still = self.ctx.android.stable_identifier(handle, self.ctx.fabric_salt) is not None
            except (ValueError, OSError):
                still = False
            if not still:
                return 'PARTIAL', None, None, False, {'facts': facts, 'lost_link': True, 'failed_reads': len(failures)}
            if manifest is not None:
                return 'VERIFIED', None, None, True, {'facts': facts, 'wear_manifest': manifest}
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
            providers = tuple(params.get('providers') or ('mdns', 'ssdp', 'android', 'freebox', 'tuya'))
            snap, reg = discovery.run(self.ctx.fabric_adapters(providers), self.ctx.fabric_salt, providers=providers)
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

    def watchers(self):
        from src.runtime.watchers import Watchers
        with self._guard:
            if getattr(self, '_watchers', None) is None:
                self._watchers = Watchers(self)
            return self._watchers

    def _watch_start(self, key, params):
        from src.runtime.watchers import WatchError
        self._device(key)
        if ('threshold_number' in params) == ('threshold_text' in params):
            raise PrimitiveError('INVALID_WATCH', 'exactly one of threshold_number / threshold_text')
        thr = params.get('threshold_number', params.get('threshold_text'))
        try:
            w = self.watchers().start(key, params['finding'], params['op'], thr, params['interval_s'], params.get('lifetime_s', 3600))
        except WatchError as e:
            raise PrimitiveError('INVALID_WATCH', str(e)) from None
        return 'VERIFIED', None, 'RUNNING', True, {'watch_id': w['watch_id']}

    def _watch_stop(self, key, params):
        from src.runtime.watchers import WatchError
        try:
            w = self.watchers().stop(params['watch_id'])
        except WatchError as e:
            raise PrimitiveError('UNKNOWN_WATCH', str(e)) from None
        return 'VERIFIED', 'RUNNING', w['state'], w['state'] == 'STOPPED', {}

    def _report(self, key, params):
        from src.runtime import report
        if self.ctx.fabric_registry is None:
            raise PrimitiveError('DEVICE_UNKNOWN', 'No graph yet; run discovery first')
        rep = report.build(self, params.get('redact', True))
        return 'VERIFIED', None, rep['summary'], True, {'report': rep, 'markdown': report.markdown(rep)}

    def timeline(self):
        from src.runtime.timeline import Timeline
        with self._guard:
            if getattr(self, '_timeline', None) is None:
                self._timeline = Timeline()
            return self._timeline

    def _category(self, key):
        reg = self.ctx.fabric_registry
        return (reg.devices.get(key) or {}).get('category', '') if reg else ''

    def _probe(self, key, params):
        import time as _t
        from src.runtime import hypotheses
        keys = params['device_keys'] or [key]
        for k in keys:
            self._device(k)
        samples, interval = params.get('samples', 3), params.get('interval_s', 10)
        if samples * interval > 120:
            raise PrimitiveError('INVALID_PARAMS', 'samples x interval must stay under 120 s')
        window = params.get('window_s', hypotheses.DEFAULT_WINDOW_S)
        tl = self.timeline()
        target = keys[0]
        before = hypotheses.analyze(tl.rows(), target, window)
        reads = []
        for i in range(samples):
            for k in keys:
                r = self._read_once(k)
                reads.append({'device_key': k, 'sample': i + 1, 'state': r['state'], 'verified': r['verified']})
            if i + 1 < samples:
                (getattr(self, '_sleep', None) or _t.sleep)(interval)
        after = hypotheses.analyze(tl.rows(), target, window)
        conf = lambda a: {h['id']: h['confidence'] for h in a['hypotheses']}
        delta = {h: {'before': conf(before).get(h), 'after': c} for h, c in conf(after).items() if conf(before).get(h) != c}
        ok = all(r['verified'] for r in reads)
        return ('VERIFIED' if ok else 'PARTIAL'), before['verdict'], after['verdict'], ok, \
            {'reads': reads, 'before': before, 'after': after, 'confidence_changes': delta}

    def _read_once(self, k):
        """Inner read used by the probe (already under the global lock): same runner, same timeline feed."""
        started = _now()
        try:
            state, _, _, verified, result = self._read_facts(k, {})
            r = {'state': state, 'verified': verified, 'errors': [], 'result': result}
        except PrimitiveError as e:
            r = {'state': 'BLOCKED', 'verified': False, 'errors': [f'{e.code}: {e}'], 'result': {}}
        except Exception as e:
            r = {'state': 'FAILED', 'verified': False, 'errors': [f'{type(e).__name__}'], 'result': {}}
        self.timeline().ingest_receipt(k, self._category(k), r)
        return r

    def _visual(self, key, params):
        from src.ai import visual_readback
        handle = self._adb_handle(key)
        serial = next(s for s, h in self.ctx.android._handles.items() if h == handle)
        allowed = (('dumpsys', 'power'), ('dumpsys', 'window'))
        def read(*a):
            if a not in allowed:
                raise ValueError('not in read allowlist')
            return self.ctx.android._run(['-s', serial, 'shell', *a], max_bytes=2097152)
        broker = getattr(self.ctx, 'vision_broker', None)
        if broker is None:
            from src.ai.glimmer import GlimmerBroker
            broker = GlimmerBroker()
        r = visual_readback.readback(lambda: self.ctx.android.screencap(serial), read, broker)
        state = 'VERIFIED' if r['verdict'] == 'CONFIRMED' else 'PARTIAL'
        return state, None, r['verdict'], r['verdict'] == 'CONFIRMED', r

    def _tuya(self):
        v = (self.ctx.fabric_adapters(('tuya',)) or {}).get('tuya')
        if v is None:
            raise PrimitiveError('NOT_LINKED', 'Tuya vacuum not linked (python -m dev.tuya_link)')
        return v

    def _tuya_setting(self, key, params):
        from src.adapters.tuya_local import TuyaBlocked
        if self._device(key)['category'] != 'vacuum':
            raise PrimitiveError('BLOCKED', 'not a Tuya vacuum')
        try:
            r = self._tuya().set_reversible(params['setting'], params['value'])
        except TuyaBlocked as e:
            raise PrimitiveError('BLOCKED', str(e)) from None
        return ('VERIFIED' if r['verified'] else 'FAILED'), r['before'], r['after'], r['verified'], r

    def _tuya_undo(self, key, params):
        from src.adapters.tuya_local import TuyaBlocked
        try:
            r = self._tuya().undo(params['setting'])
        except TuyaBlocked as e:
            raise PrimitiveError('NOTHING_TO_UNDO', str(e)) from None
        return 'REVERTED', None, r['restored'], r['exact'], r

    def _pc_job(self, key, params):
        import base64, hashlib, time as _t
        from src.adapters.windows_bridge import BridgeUnavailable
        dev = self._device(key)
        bridge = (self.ctx.fabric_adapters(('windows',)) or {}).get('windows')
        if bridge is None or not bridge.connected():
            raise PrimitiveError('DEVICE_UNAVAILABLE', 'Windows agent not connected')
        known = {i.value for i in dev['identifiers'] if i.strong}
        try:
            if bridge.identity(self.ctx.fabric_salt) not in known:
                raise PrimitiveError('IDENTITY_CHANGED', 'A different Windows PC is now connected; re-run discovery')
            t0 = _t.monotonic()
            r = bridge.run_job(params['command'], params.get('shell', 'powershell'), params.get('timeout_s', 120))
        except BridgeUnavailable as e:
            raise PrimitiveError('FAILED', str(e)[:120]) from None
        dec = lambda k: base64.b64decode(r.get(k) or b'').decode('utf-8', 'replace')[-8000:]
        out = {'command_sha256': hashlib.sha256(params['command'].encode()).hexdigest(), 'exit_code': r.get('exit_code'),
               'timed_out': bool(r.get('timed_out')), 'stdout': dec('stdout_b64'), 'stderr': dec('stderr_b64'),
               'duration_s': round(_t.monotonic() - t0, 1)}
        ok = out['exit_code'] == 0 and not out['timed_out']
        return ('VERIFIED' if ok else 'FAILED'), None, out['exit_code'], ok, out

    def _tuya_command(self, key, params):
        from src.adapters.tuya_local import TuyaBlocked, command
        if self._device(key)['category'] != 'vacuum':
            raise PrimitiveError('BLOCKED', 'not a Tuya vacuum')
        try:
            r = command(self._tuya(), params['command'], params.get('value'), params.get('move_s', 1.0))
        except TuyaBlocked as e:
            raise PrimitiveError('BLOCKED', str(e)) from None
        state = 'FAILED' if r['verified'] is False else 'VERIFIED' if r['verified'] else 'EXECUTED_UNVERIFIED'
        return state, r['status_before'], r['status_after'], bool(r['verified']), r

    RUNNERS = {'tuya_command': _tuya_command, 'pc_job': _pc_job, 'tuya_setting': _tuya_setting, 'tuya_undo': _tuya_undo, 'visual_readback': _visual, 'diagnostic_probe': _probe, 'diagnostic_report': _report, 'watch_start': _watch_start, 'watch_stop': _watch_stop,'read_facts': _read_facts, 'bounded_discovery': _bounded_discovery, 'relay_ble_scan': _relay_ble_scan,
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
            out = receipt(box['e'][0], errors=(box['e'][1],))
            if primitive_id == 'read_facts':
                self.timeline().ingest_receipt(device_key, self._category(device_key), out)
            return out
        state, before, after, verified, result = box['r']
        out = receipt(state, before, after, verified, result=result)
        if primitive_id == 'read_facts':
            self.timeline().ingest_receipt(device_key, self._category(device_key), out)
        return out

    def recovery(self):
        pending = tuple(t for t, r in self.receipts.items() if r.state in ('UNKNOWN_TIMEOUT', 'FAILED', 'PARTIAL')
                        and PRIMITIVES[r.primitive_id].reversibility != 'NONE')   # read-only results change nothing
        open_changes = tuple(c['id'] for c in self.ctx.session_journal.open_changes())
        return RecoveryState(pending, open_changes, '' if not pending else 'some transactions ended without verification')
