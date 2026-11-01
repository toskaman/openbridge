"""Safe primitives registry and executor (contract v1).

Every action a client (UI, Capability Forge, Meta planner) can trigger is one of these primitives. There is no free-form
command: each primitive has a strict input schema, preconditions, a verification step and a declared inverse, and runs
through the existing safety layers (deterministic gate + consent + transaction engine for writes, session journal for
environment changes). The executor enforces schema, consent, identity, concurrency and timeouts, and always returns an
honest TransactionReceipt: a result is `verified` only when an independent read-back confirmed it."""
import re
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timezone

from src.runtime.contract import ActionDescriptor, ReversibilityClass, TransactionReceipt, RecoveryState, to_json
from src.runtime import diagnostics
import hashlib

R = ReversibilityClass


class PrimitiveError(Exception):
    """Refusal before anything was attempted (status: BLOCKED)."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _s(type_, **kw):
    return dict(type=type_, **kw)


def _read_wakefulness(android, handle):
    out = android.shell(handle, ('dumpsys', 'power'))
    m = re.search(r'mWakefulness=(\w+)', out)
    return m.group(1) if m else None


def _focused_package(android, handle):
    out = android.shell(handle, ('dumpsys', 'activity', 'activities'))
    m = re.search(r'mFocusedApp=ActivityRecord\{[^}]* (\S+)/', out)
    return m.group(1) if m else None


ARGS_SCHEMA = {'type': 'object', 'additionalProperties': False, 'properties': {
    'key': {'type': 'string', 'maxLength': 24}, 'text': {'type': 'string', 'maxLength': 100}, 'package': {'type': 'string', 'maxLength': 120},
    'url': {'type': 'string', 'maxLength': 300}, 'setting': {'type': 'string', 'maxLength': 32}, 'value': {'type': 'integer', 'minimum': 0, 'maximum': 1800000},
    'x': {'type': 'number'}, 'y': {'type': 'number'}, 'x1': {'type': 'number'}, 'y1': {'type': 'number'}, 'x2': {'type': 'number'}, 'y2': {'type': 'number'},
    'ms': {'type': 'integer', 'minimum': 0, 'maximum': 10000}}}

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
    ActionDescriptor('device_capabilities', 'Measure which typed actions an Android phone, TV or watch supports (read-only probe)',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('read grant on a current ADB link',), ('identity re-verified',), ('none: read-only',),
                     'each entry measured on the device now', '', R.NONE.value, ('DEVICE_UNAVAILABLE',), 60, 'single-per-device', False),
    ActionDescriptor('device_action', 'Run one typed action on an Android phone, TV or watch (remote keys, mouse, text, apps, URL, settings)',
                     {'type': 'object', 'properties': {'action': _s('string', enum=sorted(['key', 'text', 'tap', 'swipe', 'long_press', 'launch_app', 'open_url', 'set', 'get', 'restore', 'list_apps', 'screen_state', 'audio_state'])),
                                                       'args': ARGS_SCHEMA}, 'required': ['action'], 'additionalProperties': False},
                     ('owner consent for this action',), ('identity re-verified', 'args valid for the action'),
                     ('device acted; settings read back',), 'settings: independent read-back (undo = device_action with action=restore); other actions report the screen state', '',
                     R.IRREVERSIBLE.value, ('DEVICE_UNAVAILABLE', 'INVALID_ACTION'), 60, 'single-per-device', True),
    ActionDescriptor('device_macro', 'Run a short sequence of typed actions (a new feature built from the catalog) under one consent listing every step',
                     {'type': 'object', 'properties': {'steps': _s('array', maxItems=20, items={'type': 'object', 'properties': {
                         'action': _s('string', enum=sorted(['key', 'text', 'tap', 'swipe', 'long_press', 'launch_app', 'open_url', 'set', 'get', 'restore', 'screen_state', 'audio_state', 'wait'])),
                         'args': ARGS_SCHEMA}, 'required': ['action'], 'additionalProperties': False})},
                      'required': ['steps'], 'additionalProperties': False},
                     ('owner consent for the whole listed sequence',), ('identity re-verified', 'at most 20 steps, waits <= 10 s each'),
                     ('steps ran in order; stops at the first failure',), 'per-step result returned', '', R.IRREVERSIBLE.value,
                     ('DEVICE_UNAVAILABLE', 'INVALID_ACTION'), 300, 'single-per-device', True),
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
    ActionDescriptor('screen_capture', 'Capture one screenshot PNG and store it server-side under a capture id',
                     {'type': 'object', 'properties': {'label': _s('string', maxLength=64)}, 'additionalProperties': False},
                     ('owner consent (screenshots are sensitive)', 'read grant on a current ADB link'),
                     ('identity re-verified',),
                     ('frame stored server-side under a capture id; nothing leaves the PC',),
                     'PNG signature validated; width/height/sha256 read back from stored bytes', '',
                     R.NONE.value, ('DEVICE_UNAVAILABLE', 'IDENTITY_CHANGED', 'CAPTURE_FAILED'), 30, 'single-per-device', True),
    ActionDescriptor('capture_send', 'Push a stored capture PNG to /sdcard/OpenBridge/ on an Android target, hash-verified',
                     {'type': 'object', 'properties': {'capture_id': _s('string', maxLength=32), 'name': _s('string', maxLength=64)},
                      'required': ['capture_id'], 'additionalProperties': False},
                     ('owner consent for this exact transfer',),
                     ('capture id exists in the server store', 'identity re-verified'),
                     ('PNG pushed to /sdcard/OpenBridge/ on the target',),
                     'sha256sum on the device equals the stored hash', '',
                     R.MANUAL.value, ('UNKNOWN_CAPTURE', 'DEVICE_UNAVAILABLE', 'PUSH_FAILED', 'HASH_MISMATCH'), 90, 'single-per-device', True),
    ActionDescriptor('capture_montage', 'Combine stored captures into one PNG (row or grid), server-side, stdlib only',
                     {'type': 'object', 'properties': {'capture_ids': _s('array', maxItems=16, items=_s('string', maxLength=32)),
                                                       'layout': _s('string', enum=['row', 'grid'])},
                      'required': ['capture_ids'], 'additionalProperties': False},
                     (), ('every capture id exists in the server store', 'no new device capture is made'),
                     ('combined PNG stored server-side under a new capture id',),
                     'output PNG decodes; dimensions equal the tile math', '',
                     R.NONE.value, ('UNKNOWN_CAPTURE', 'MONTAGE_FAILED'), 60, 'single-global', False),
    ActionDescriptor('tv_sleep', 'Put an Android TV to sleep (screen off, wakes on remote)',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('owner consent for this physical act', 'control grant on a current ADB link'),
                     ('target is a TV', 'identity re-verified'),
                     ('TV asleep; any remote key or tv_wake restores',),
                     'mWakefulness read back Asleep via dumpsys power', 'tv_wake',
                     R.MANUAL.value, ('DEVICE_UNAVAILABLE', 'SLEEP_FAILED'), 30, 'single-per-device', True),
    ActionDescriptor('tv_wake', 'Wake an Android TV (screen on)',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('owner consent for this physical act', 'control grant on a current ADB link'),
                     ('target is a TV', 'identity re-verified'),
                     ('TV awake',),
                     'mWakefulness read back Awake via dumpsys power', 'tv_sleep',
                     R.MANUAL.value, ('DEVICE_UNAVAILABLE', 'WAKE_FAILED'), 30, 'single-per-device', True),
    ActionDescriptor('companion_foreground', 'Bring the OpenBridge Companion app to the foreground',
                     {'type': 'object', 'properties': {}, 'additionalProperties': False},
                     ('owner consent (interrupts what is on screen)', 'control grant on a current ADB link'),
                     ('screen awake (tv_wake first if asleep)', 'identity re-verified'),
                     ('Companion activity focused; HOME/remote undoes',),
                     'mFocusedApp names fr.openbridge.companion via dumpsys activity', '',
                     R.MANUAL.value, ('DEVICE_UNAVAILABLE', 'DEVICE_ASLEEP', 'FOREGROUND_FAILED'), 30, 'single-per-device', True),
    ActionDescriptor('file_pull', 'Copy one file from under /sdcard/ into the server transfer store',
                     {'type': 'object', 'properties': {'remote': _s('string', maxLength=256)}, 'required': ['remote'], 'additionalProperties': False},
                     ('owner consent (file contents are sensitive)', 'read grant on a current ADB link'),
                     ('remote path stays under /sdcard/',),
                     ('file bytes copied to the server transfer store; device untouched',),
                     'sha256 of the stored bytes reported', '',
                     R.NONE.value, ('DEVICE_UNAVAILABLE', 'PULL_FAILED'), 60, 'single-per-device', True),
    ActionDescriptor('retro_command', 'Send one allowlisted command to the local RetroArch over loopback UDP',
                     {'type': 'object', 'properties': {'command': _s('string', enum=['VERSION', 'GET_STATUS', 'PAUSE_TOGGLE', 'VOLUME_UP', 'VOLUME_DOWN'])},
                      'required': ['command'], 'additionalProperties': False},
                     ('owner consent for this command',),
                     ('local RetroArch running with network_cmd enabled',),
                     ('queries return a reply; actions are delivered without reply',),
                     'queries: reply text read back; actions: EXECUTED_UNVERIFIED (delivery only)', '',
                     R.IRREVERSIBLE.value, ('RETRO_UNAVAILABLE',), 15, 'single-global', True),
    ActionDescriptor('file_push', 'Push stored transfer bytes to /sdcard/OpenBridge/<name>, hash-verified',
                     {'type': 'object', 'properties': {'transfer_id': _s('string', maxLength=32), 'name': _s('string', maxLength=64)},
                      'required': ['transfer_id', 'name'], 'additionalProperties': False},
                     ('owner consent for this exact transfer',),
                     ('transfer id exists in the server store', 'name is a bare file name'),
                     ('bytes pushed to /sdcard/OpenBridge/<name> on the target',),
                     'sha256sum on the device equals the stored hash', '',
                     R.MANUAL.value, ('UNKNOWN_TRANSFER', 'DEVICE_UNAVAILABLE', 'PUSH_FAILED', 'HASH_MISMATCH'), 90, 'single-per-device', True),
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
        self._receipt_order = deque()
        self._acknowledged = set()     # unresolved transactions the owner checked and acknowledged (outcome stays unverified)
        self._admitted = 0             # potentially changing operations admitted but not yet recorded
        from src.runtime.state_store import StateStore
        self._store = StateStore.for_server(ctx)
        self._persist_lock = threading.RLock()
        self._state_error = ''
        self._restore()

    # ---------- durable recovery backlog ----------
    def _restore(self):
        if self._store is None or self._state_error:
            return
        try:
            saved = self._store.load()
        except OSError as error:
            self._state_error = str(error)
            return
        with self._guard:
            self._acknowledged.update(saved.get('acknowledged', []))
            for row in saved.get('unresolved', []):
                r = TransactionReceipt(**{k: row[k] for k in ('transaction_id', 'primitive_id', 'device_key', 'state', 'before', 'after',
                                                             'verified', 'started_at', 'finished_at')}, errors=tuple(row.get('errors') or ()))
                if r.transaction_id not in self.receipts:
                    self.receipts[r.transaction_id] = r
                    self._receipt_order.append(r.transaction_id)

    def _persist(self, acknowledged=()):
        if self._store is None:
            return True
        # Snapshot inside the persistence lock: a slower older snapshot cannot overwrite a newer one.
        with self._persist_lock:
            with self._guard:
                rows = [dict(to_json(self.receipts[t]), errors=list(self.receipts[t].errors)) for t in self.receipts if self._needs_recovery(t)]
                ack = set(self._acknowledged) | set(acknowledged)
            try:
                self._store.save_unresolved(rows, ack)
                return True
            except OSError as error:
                self._state_error = str(error)
                self.emit('state_error', reason=self._state_error)
                return False

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
        store = getattr(self.ctx, 'relay_store', None)
        if store is not None:
            store.remove(rid)                     # a revoked pairing must not come back after a restart
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
        if not r['exact']:
            # The pending restore is kept (adapter pops only on exact), so a
            # retry is possible; the receipt must not claim REVERTED.
            raise PrimitiveError('RESTORE_NOT_EXACT',
                                 'restored %r, expected the recorded before value' % (r['restored'],))
        return 'REVERTED', None, r['restored'], True, r

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

    def _actions(self, key):
        from src.fabric.android_actions import AndroidActions
        dev = self._device(key)
        if dev['category'] not in ('phone', 'tv', 'android', 'watch'):
            raise PrimitiveError('INVALID_ACTION', 'typed actions exist for Android phones, TVs and watches')
        handle = self._adb_handle(key)
        serial = next(s for s, h in self.ctx.android._handles.items() if h == handle)
        cache = self.__dict__.setdefault('_action_sessions', {})
        a = cache.get(key)
        if a is None or a.serial != serial:
            a = AndroidActions(lambda *args: self.ctx.android._run(['-s', serial, 'shell', *args], max_bytes=2097152), dev['category'])
            a.serial = serial
            cache[key] = a
        return a

    def _device_capabilities(self, key, params):
        p = self._actions(key).probe()
        self.__dict__.setdefault('probes', {})[key] = p       # measured ranges feed B2 route exactness
        return 'VERIFIED', None, None, True, p

    def _one(self, a, action, args):
        from src.fabric.android_actions import ActionError
        try:
            return a.run(action, args or {})
        except ActionError as e:
            raise PrimitiveError('INVALID_ACTION', str(e)) from None

    def _device_action(self, key, params):
        a = self._actions(key)
        r = self._one(a, params['action'], params.get('args'))
        ok = r.get('verified', r.get('exact', True)) is not False
        state = 'REVERTED' if params['action'] == 'restore' else 'VERIFIED' if 'verified' in r else 'EXECUTED'
        return (state if ok else 'FAILED'), r.get('before'), r.get('after', r.get('restored')), ok, r

    def _device_macro(self, key, params):
        import time as _t
        a = self._actions(key)
        done = []
        for i, st in enumerate(params['steps']):
            if st['action'] == 'wait':
                ms = (st.get('args') or {}).get('ms', 500)
                (getattr(self, '_sleep', None) or _t.sleep)(min(ms, 10000) / 1000)
                done.append({'step': i + 1, 'action': 'wait', 'ms': ms}); continue
            try:
                r = self._one(a, st['action'], st.get('args'))
            except PrimitiveError as e:
                done.append({'step': i + 1, 'action': st['action'], 'error': str(e)})
                return 'PARTIAL', None, f'stopped at step {i + 1}', False, {'steps': done}
            done.append({'step': i + 1, 'action': st['action'], **r})
        return 'EXECUTED', None, f'{len(done)} steps', True, {'steps': done}

    def _captures(self):
        from pathlib import Path
        from src.runtime.capture_store import CaptureStore
        explicit = getattr(self.ctx, 'captures_dir', None)
        if explicit is not None:
            return CaptureStore(explicit)
        sj = getattr(getattr(self.ctx, 'session_journal', None), 'path', None)
        if sj is None:
            raise PrimitiveError('NO_STORE', 'no server store for captures')
        return CaptureStore(Path(sj).with_name('captures'))

    def _serial(self, handle):
        try:
            return next(s for s, h in self.ctx.android._handles.items() if h == handle)
        except StopIteration:
            raise PrimitiveError('DEVICE_UNAVAILABLE', 'no live ADB link to this device') from None

    def _screen_capture(self, key, params):
        from src.runtime import montage as _m
        handle = self._adb_handle(key)
        png = bytes(self.ctx.android.screencap(self._serial(handle)))
        try:
            w, h = _m.png_size(png)
        except ValueError as e:
            raise ValueError(f'CAPTURE_FAILED: {e}') from None
        store = self._captures()
        cid = store.put(png, kind='cap')
        return 'EXECUTED', None, f'{w}x{h} frame stored', True, \
            {'capture_id': cid, 'sha256': store.sha256(cid), 'bytes': len(png), 'width': w, 'height': h}

    def _capture_send(self, key, params):
        from src.runtime.capture_store import StoreError
        store = self._captures()
        try:
            data = store.get(params['capture_id'])
        except StoreError as e:
            raise PrimitiveError('UNKNOWN_CAPTURE', str(e)[:160]) from None
        handle = self._adb_handle(key)
        name = params.get('name') or (params['capture_id'] + '.png')
        try:
            remote = self.ctx.android.push_file(handle, data, name)
            digest = self.ctx.android.file_sha256(handle, remote)
        except ValueError as e:
            raise PrimitiveError('PUSH_FAILED', str(e)[:160]) from None
        want = hashlib.sha256(data).hexdigest()
        if digest != want:
            raise ValueError(f'HASH_MISMATCH: device has {digest[:16]}.., expected {want[:16]}..')
        return 'EXECUTED', None, remote, True, {'remote': remote, 'sha256': want, 'bytes': len(data)}

    def _capture_montage(self, key, params):
        from src.runtime import montage as _m
        from src.runtime.capture_store import StoreError
        store = self._captures()
        frames = []
        for cid in params['capture_ids']:
            try:
                frames.append(store.get(cid))
            except StoreError as e:
                raise PrimitiveError('UNKNOWN_CAPTURE', str(e)[:160]) from None
        try:
            out = _m.combine(frames, layout=params.get('layout', 'row'))
        except ValueError as e:
            raise ValueError(f'MONTAGE_FAILED: {e}') from None
        w, h = _m.png_size(out)
        cid = store.put(out, kind='cap')
        return 'EXECUTED', None, f'{w}x{h} montage of {len(frames)}', True, \
            {'capture_id': cid, 'sha256': store.sha256(cid), 'width': w, 'height': h, 'inputs': len(frames)}

    def _retro_command(self, key, params):
        from src.adapters.retroarch import RetroArch, RetroArchError, QUERIES
        port = getattr(self.ctx, 'retro_port', 55355)
        try:
            out = RetroArch(port=port).command(params['command'])
        except RetroArchError as e:
            raise ValueError(f'RETRO_UNAVAILABLE: {e}') from None
        if params['command'] in QUERIES:
            return 'EXECUTED', None, out[:120], True, {'reply': out}
        return 'EXECUTED_UNVERIFIED', None, 'delivered, effect unverified', False, {'sent': out}

    def _tv_sleep(self, key, params):
        handle = self._adb_handle(key)
        try:
            self.ctx.android.shell(handle, ('input', 'keyevent', 'KEYCODE_SLEEP'))
            state = _read_wakefulness(self.ctx.android, handle)
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if state != 'Asleep':
            time.sleep(2)
            try:
                state = _read_wakefulness(self.ctx.android, handle)
            except ValueError as e:
                raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if state != 'Asleep':
            raise ValueError('SLEEP_FAILED: wakefulness is %s' % state)
        return 'EXECUTED', None, 'TV asleep (mWakefulness=Asleep)', True, {'wakefulness': 'Asleep'}

    def _tv_wake(self, key, params):
        handle = self._adb_handle(key)
        try:
            self.ctx.android.shell(handle, ('input', 'keyevent', 'KEYCODE_WAKEUP'))
            state = _read_wakefulness(self.ctx.android, handle)
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if state != 'Awake':
            time.sleep(2)
            try:
                state = _read_wakefulness(self.ctx.android, handle)
            except ValueError as e:
                raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if state != 'Awake':
            raise ValueError('WAKE_FAILED: wakefulness is %s' % state)
        return 'EXECUTED', None, 'TV awake (mWakefulness=Awake)', True, {'wakefulness': 'Awake'}

    def _companion_foreground(self, key, params):
        handle = self._adb_handle(key)
        try:
            wake = _read_wakefulness(self.ctx.android, handle)
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if wake != 'Awake':
            raise PrimitiveError('DEVICE_ASLEEP', 'wake the screen first (tv_wake or the remote)')
        try:
            self.ctx.android.shell(handle, ('am', 'start', '-n', 'fr.openbridge.companion/.MainActivity'))
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        time.sleep(2)
        try:
            pkg = _focused_package(self.ctx.android, handle)
        except ValueError as e:
            raise PrimitiveError('DEVICE_UNAVAILABLE', str(e)[:160]) from None
        if pkg != 'fr.openbridge.companion':
            raise ValueError('FOREGROUND_FAILED: focused package is %s' % pkg)
        return 'EXECUTED', None, 'Companion focused', True, {'package': pkg}

    def _file_pull(self, key, params):
        handle = self._adb_handle(key)
        try:
            data = bytes(self.ctx.android.pull_file(handle, params['remote']))
        except ValueError as e:
            raise PrimitiveError('PULL_FAILED', str(e)[:160]) from None
        store = self._captures()
        tid = store.put(data, kind='xfer')
        return 'EXECUTED', None, params['remote'], True, \
            {'transfer_id': tid, 'sha256': store.sha256(tid), 'bytes': len(data), 'remote': params['remote']}

    def _file_push(self, key, params):
        from src.runtime.capture_store import StoreError
        store = self._captures()
        try:
            data = store.get(params['transfer_id'])
        except StoreError as e:
            raise PrimitiveError('UNKNOWN_TRANSFER', str(e)[:160]) from None
        handle = self._adb_handle(key)
        try:
            remote = self.ctx.android.push_file(handle, data, params['name'])
            digest = self.ctx.android.file_sha256(handle, remote)
        except ValueError as e:
            raise PrimitiveError('PUSH_FAILED', str(e)[:160]) from None
        want = hashlib.sha256(data).hexdigest()
        if digest != want:
            raise ValueError(f'HASH_MISMATCH: device has {digest[:16]}.., expected {want[:16]}..')
        return 'EXECUTED', None, remote, True, {'remote': remote, 'sha256': want, 'bytes': len(data)}

    RUNNERS = {'device_capabilities': _device_capabilities, 'device_action': _device_action, 'device_macro': _device_macro, 'tuya_command': _tuya_command, 'pc_job': _pc_job, 'tuya_setting': _tuya_setting, 'tuya_undo': _tuya_undo, 'visual_readback': _visual, 'diagnostic_probe': _probe, 'diagnostic_report': _report, 'watch_start': _watch_start, 'watch_stop': _watch_stop,'read_facts': _read_facts, 'bounded_discovery': _bounded_discovery, 'relay_ble_scan': _relay_ble_scan,
               'relay_revoke': _relay_revoke, 'android_optional_app_state': _app_state, 'undo_transaction': _undo,
               'session_cleanup': _session_cleanup, 'screen_capture': _screen_capture, 'capture_send': _capture_send,
               'capture_montage': _capture_montage, 'file_pull': _file_pull, 'file_push': _file_push,
               'retro_command': _retro_command, 'tv_sleep': _tv_sleep, 'tv_wake': _tv_wake,
               'companion_foreground': _companion_foreground}

    # ---------- recovery backlog ----------
    MAX_RECEIPTS = 512        # resolved receipts beyond this are evicted oldest-first
    MAX_UNRESOLVED = 64       # unresolved, potentially changing outcomes kept until the owner resolves them
    UNRESOLVED = ('UNKNOWN_TIMEOUT', 'FAILED', 'PARTIAL')

    def _needs_recovery(self, tx):
        r = self.receipts.get(tx)
        p = PRIMITIVES.get(r.primitive_id) if r else None
        return bool(r and p and r.state in self.UNRESOLVED and p.reversibility != 'NONE' and tx not in self._acknowledged)

    def _backlog(self):
        return sum(1 for t in self.receipts if self._needs_recovery(t)) + self._admitted

    def acknowledge(self, tx):
        """The owner checked an unresolved outcome on the device. It leaves recovery and frees backlog capacity;
        the receipt keeps its unverified state (acknowledging is not verification)."""
        with self._persist_lock:
            with self._guard:
                if not self._needs_recovery(tx):
                    return False
            if not self._persist(acknowledged=(tx,)):
                return False
            with self._guard:
                self._acknowledged.add(tx)
        self.emit('acknowledged', transaction_id=tx)
        return True

    # ---------- entry point ----------
    def execute(self, primitive_id, device_key, params, consent=False):
        started, tx = _now(), 'tx-' + secrets.token_hex(8)
        p = PRIMITIVES.get(primitive_id)
        admitted = []
        def receipt(state, before=None, after=None, verified=False, errors=(), result=None):
            r = TransactionReceipt(tx, primitive_id, str(device_key)[:64], state, before, after, verified, started, _now(), tuple(errors))
            with self._guard:
                if admitted:
                    self._admitted -= 1
                    admitted.clear()
                self.receipts[tx] = r
                self._receipt_order.append(tx)
                # Bounded: unresolved changing outcomes are capped by admission (MAX_UNRESOLVED) and never evicted;
                # everything else is evicted oldest-first.
                while len(self.receipts) > self.MAX_RECEIPTS:
                    victim = next((t for t in self._receipt_order if t in self.receipts and not self._needs_recovery(t)), None)
                    if victim is None:
                        break
                    self._receipt_order.remove(victim)
                    self.receipts.pop(victim, None)
                    self._acknowledged.discard(victim)
            self.emit('receipt', transaction_id=tx, primitive_id=primitive_id, state=state, verified=verified)
            durable = self._persist() if self._needs_recovery(tx) else True
            out = dict(to_json(r), result=result or {})
            if not durable:
                out['errors'].append(self._state_error)
            return out
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
        if p.reversibility != 'NONE':
            self._restore()
            if self._state_error:
                return receipt('BLOCKED', errors=(self._state_error,))
        if p.reversibility != 'NONE':   # could change something: admit only while the recovery backlog has room
            with self._guard:
                full = self._backlog() >= self.MAX_UNRESOLVED
                if not full:
                    self._admitted += 1
                    admitted.append(True)
            if full:
                return receipt('BLOCKED', errors=(f'RECOVERY_BACKLOG: {self.MAX_UNRESOLVED} operations ended without verification; '
                                                  'check them in Activity & Recovery and acknowledge them before running another change',))
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
        self._restore()
        with self._guard:   # read-only results change nothing; acknowledged outcomes were checked by the owner
            pending = tuple(t for t in list(self.receipts) if self._needs_recovery(t))
        open_changes = tuple(c['id'] for c in self.ctx.session_journal.open_changes())
        return RecoveryState(pending, open_changes, self._state_error or ('' if not pending else 'some transactions ended without verification'))
