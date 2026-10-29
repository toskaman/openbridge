"""NATIVE_PRIMITIVE_REGISTRY: prebuilt, typed platform primitives the Meta agent tier may compose (V4).

Every entry is `source: prebuilt`. Composing them into a device-specific capability is the Meta tier's job
(CandidateManifest, origin=meta_generated). A primitive is generic (e.g. "press one registered key"), never a user
workflow (e.g. "open YouTube on the living-room TV").

`status` is evidence, not intent:
- REAL_HARDWARE_VERIFIED: exercised on owned hardware with receipts (see EVIDENCE_LEDGER / B2 / B3 runs).
- SIMULATED_VERIFIED: tested against fixtures only.
- HYPOTHESIS: platform API identified, not implemented; manifests using it are rejected with an EngineeringPrimitiveRequest.
- BLOCKED: deliberately unavailable (policy or missing step-up authorization).
`manifest_allowed: false` keeps owner-only or dangerous primitives (shell jobs, revocation, cleanup) out of reach of models.
"""
import copy

from src.fabric.android_actions import KEYS, SETTINGS

ANDROID = ('phone', 'tv', 'watch', 'android', 'tablet')
_KEYS = sorted(KEYS)
_EMPTY = {'type': 'object', 'properties': {}, 'additionalProperties': False}
_PKG = {'type': 'string', 'maxLength': 120}
_UNIT = {'type': 'number', 'minimum': 0, 'maximum': 1}


def _d(pid, platform, resource, inp, out, perms, effect, idem, secs, status, oracle, constraints=(), errors=(), allowed=True, version=1):
    return {'id': pid, 'version': version, 'platform': platform, 'resource_type': resource, 'input_schema': inp, 'output_schema': out,
            'required_permissions': list(perms), 'side_effect_class': effect, 'idempotency': idem,
            'costs': {'max_seconds': secs, 'cloud_spend': False}, 'constraints': list(constraints), 'source': 'prebuilt',
            'status': status, 'manifest_allowed': allowed, 'test_oracle': oracle, 'error_codes': list(errors) or ['BLOCKED', 'DEVICE_UNAVAILABLE']}


def _obj(props, required=()):
    return {'type': 'object', 'properties': props, 'required': list(required), 'additionalProperties': False}


REAL, SIM, HYP, BLK = 'REAL_HARDWARE_VERIFIED', 'SIMULATED_VERIFIED', 'HYPOTHESIS', 'BLOCKED'

# descriptor, backend: (executor primitive, params builder, allowed device categories)
_ENTRIES = [
    (_d('device.read_descriptor', 'any', 'device', _EMPTY, {'type': 'object'}, ['read'], 'READ', 'IDEMPOTENT', 60, REAL,
        'facts returned match the registry snapshot for the same fingerprint'),
     ('read_facts', lambda a: {}, None)),
    (_d('device.probe_actions', 'android', 'device', _EMPTY, {'type': 'object'}, ['read'], 'READ', 'IDEMPOTENT', 60, REAL,
        'probe lists actions the device answered read-only; ranges are measured, not assumed'),
     ('device_capabilities', lambda a: {}, ANDROID)),
    (_d('state.read_setting', 'android', 'setting', _obj({'setting': {'type': 'string', 'enum': list(SETTINGS)}}, ['setting']),
        {'type': 'object'}, ['read'], 'READ', 'IDEMPOTENT', 60, REAL, 'value equals an independent adb read of the same setting'),
     ('device_action', lambda a: {'action': 'get', 'args': {'setting': a['setting']}}, ANDROID)),
    (_d('state.screen', 'android', 'display', _EMPTY, {'type': 'object'}, ['read'], 'READ', 'IDEMPOTENT', 60, REAL,
        'power state and focused app match dumpsys power/window'),
     ('device_action', lambda a: {'action': 'screen_state'}, ANDROID)),
    (_d('state.audio', 'android', 'audio', _EMPTY, {'type': 'object'}, ['read'], 'READ', 'IDEMPOTENT', 60, REAL,
        'muted flag and volume index equal an independent dumpsys audio read of STREAM_MUSIC',
        ['muted is null when the device does not report it; HDMI-CEC/AVR volume is not visible here']),
     ('device_action', lambda a: {'action': 'audio_state'}, ANDROID)),
    (_d('app.list', 'android', 'app', _EMPTY, {'type': 'object'}, ['read'], 'READ', 'IDEMPOTENT', 60, REAL,
        'packages equal the launcher activities reported by the package manager'),
     ('device_action', lambda a: {'action': 'list_apps'}, ANDROID)),
    (_d('input.key', 'android', 'input', _obj({'key': {'type': 'string', 'enum': _KEYS}}, ['key']), {'type': 'object'}, ['control'],
        'IRREVERSIBLE', 'NON_IDEMPOTENT', 60, REAL, 'observable state change read back by the next read primitive',
        ['TV-only keys are refused on phones and watches by the device adapter']),
     ('device_action', lambda a: {'action': 'key', 'args': {'key': a['key']}}, ANDROID)),
    (_d('app.launch', 'android', 'app', _obj({'package': _PKG}, ['package']), {'type': 'object'}, ['control'], 'IRREVERSIBLE', 'NON_IDEMPOTENT',
        60, REAL, 'focused app after launch equals the requested package (state.screen)', ['package must be launchable on the device']),
     ('device_action', lambda a: {'action': 'launch_app', 'args': {'package': a['package']}}, ANDROID)),
    (_d('url.open', 'android', 'app', _obj({'url': {'type': 'string', 'maxLength': 300}}, ['url']), {'type': 'object'}, ['control'],
        'IRREVERSIBLE', 'NON_IDEMPOTENT', 60, REAL, 'focused app changes to the URL handler', ['http(s) only; no intent URIs']),
     ('device_action', lambda a: {'action': 'open_url', 'args': {'url': a['url']}}, ANDROID)),
    (_d('input.text', 'android', 'input', _obj({'text': {'type': 'string', 'maxLength': 100}}, ['text']), {'type': 'object'}, ['control'],
        'IRREVERSIBLE', 'NON_IDEMPOTENT', 60, REAL, 'text appears in the focused field (owner-checked)'),
     ('device_action', lambda a: {'action': 'text', 'args': {'text': a['text']}}, ANDROID)),
    (_d('input.tap', 'android', 'input', _obj({'x': _UNIT, 'y': _UNIT}, ['x', 'y']), {'type': 'object'}, ['control'],
        'IRREVERSIBLE', 'NON_IDEMPOTENT', 60, REAL, 'owner-checked; coordinates are fractions of the screen',
        ['blocked on some vendors (MIUI) without the security option']),
     ('device_action', lambda a: {'action': 'tap', 'args': {'x': a['x'], 'y': a['y']}}, ANDROID)),
    (_d('setting.set_exact', 'android', 'setting', _obj({'setting': {'type': 'string', 'enum': list(SETTINGS)},
                                                          'value': {'type': 'integer', 'minimum': 0, 'maximum': 1800000}}, ['setting', 'value']),
        {'type': 'object'}, ['control'], 'REVERSIBLE_EXACT', 'IDEMPOTENT', 60, REAL,
        'independent read-back equals the value; before snapshot kept for setting.restore', ['range measured on the device; out-of-range refused']),
     ('device_action', lambda a: {'action': 'set', 'args': {'setting': a['setting'], 'value': a['value']}}, ANDROID)),
    (_d('setting.restore', 'android', 'setting', _obj({'setting': {'type': 'string', 'enum': list(SETTINGS)}}, ['setting']),
        {'type': 'object'}, ['control'], 'REVERSIBLE_EXACT', 'IDEMPOTENT', 60, REAL, 'read-back equals the snapshot taken by setting.set_exact'),
     ('device_action', lambda a: {'action': 'restore', 'args': {'setting': a['setting']}}, ANDROID)),
    (_d('ble.scan_via_relay', 'ble_relay', 'radio', _obj({'relay_id': {'type': 'string', 'maxLength': 64},
                                                           'seconds': {'type': 'integer', 'minimum': 1, 'maximum': 15}}, ['relay_id']),
        {'type': 'object'}, ['control'], 'SESSION_CLEANUP', 'IDEMPOTENT', 25, REAL,
        'signed relay reply; advertisers appear as observe-only graph children', ['scan only: no GATT, pairing, audio or file transfer']),
     ('relay_ble_scan', lambda a: {'relay_id': a['relay_id'], 'seconds': a.get('seconds', 8)}, ANDROID)),
    (_d('vendor.tuya.command', 'tuya', 'vendor_action', copy.deepcopy(_obj({'command': {'type': 'string', 'enum': ['start', 'pause', 'dock']}}, ['command'])),
        {'type': 'object'}, ['control'], 'IRREVERSIBLE', 'NON_IDEMPOTENT', 30, REAL,
        'device status DP read back after the command', ['only commands the linked Tuya product declares; physical motion cannot be undone']),
     ('tuya_command', lambda a: {'command': a['command']}, ('vacuum',))),
    (_d('vendor.tuya.setting_exact', 'tuya', 'setting', _obj({'setting': {'type': 'string', 'enum': ['suction', 'volume']},
                                                              'value': {'type': 'string', 'maxLength': 16}}, ['setting', 'value']),
        {'type': 'object'}, ['control'], 'REVERSIBLE_EXACT', 'IDEMPOTENT', 30, REAL, 'status DP equals the value; exact undo available'),
     ('tuya_setting', lambda a: {'setting': a['setting'], 'value': a['value']}, ('vacuum',))),
    # Owner-only: never composable by a model.
    (_d('pc.job', 'windows', 'process', {'type': 'object'}, {'type': 'object'}, ['control'], 'IRREVERSIBLE', 'NON_IDEMPOTENT', 630, REAL,
        'owner-typed command with exact consent', ['no generic command shell for models (V4 security invariant)'], allowed=False), None),
    # Not implemented yet: manifests referencing these get an EngineeringPrimitiveRequest.
    (_d('files.open_user_granted_uri', 'android', 'file', _obj({'uri': {'type': 'string', 'maxLength': 300}}, ['uri']), {'type': 'object'}, ['read'],
        'READ', 'IDEMPOTENT', 60, HYP, 'SAF document URI granted by the owner on the device', ['needs Companion SAF picker + scoped grant']), None),
    (_d('files.transfer_chunks', 'any', 'file', _obj({'transfer_id': {'type': 'string', 'maxLength': 64}}, ['transfer_id']), {'type': 'object'},
        ['control'], 'SESSION_CLEANUP', 'IDEMPOTENT', 600, HYP, 'SHA-256 end to end; resume; temp cleanup', ['AEAD per chunk; no excluded-relay fallback']), None),
    (_d('screen.capture_session_approved', 'android', 'display', _EMPTY, {'type': 'object'}, ['read'], 'READ', 'IDEMPOTENT', 60, HYP,
        'MediaProjection consent shown by Android', ['adb screencap is not an OS-approved capture session; whole-watch capture conditional']), None),
    (_d('screen.present_image', 'android', 'display', _obj({'image_id': {'type': 'string', 'maxLength': 64}}, ['image_id']), {'type': 'object'},
        ['control'], 'SESSION_CLEANUP', 'IDEMPOTENT', 60, HYP, 'Companion ACK with the image hash'), None),
    (_d('calls.request_contact_lookup', 'android', 'contact', _obj({'query': {'type': 'string', 'maxLength': 40}}, ['query']), {'type': 'object'},
        ['read'], 'READ', 'IDEMPOTENT', 30, HYP, 'single contact preview; no contact dump', ['READ_CONTACTS runtime permission, narrow scope']), None),
    (_d('calls.place_call_with_confirmation', 'android', 'telephony', _obj({'contact_ref': {'type': 'string', 'maxLength': 64}}, ['contact_ref']),
        {'type': 'object'}, ['control'], 'IRREVERSIBLE', 'NON_IDEMPOTENT', 60, HYP,
        'ACTION_DIAL shown to the owner; the phone dials, not OpenBridge', ['no claim of TV/remote-mic call audio without a probe']), None),
    (_d('remote.request_shutdown', 'windows', 'power', _EMPTY, {'type': 'object'}, ['control'], 'IRREVERSIBLE', 'NON_IDEMPOTENT', 60, BLK,
        'separate step-up voice + local approval', ['blocked until step-up authorization exists'], allowed=False), None),
]

NATIVE_PRIMITIVE_REGISTRY = {d['id']: d for d, _ in _ENTRIES}
BACKEND = {d['id']: b for d, b in _ENTRIES if b is not None}


def catalog():
    return [copy.deepcopy(d) for d in NATIVE_PRIMITIVE_REGISTRY.values()]
