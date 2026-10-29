"""V4 typed schemas: strict shapes, canonical digests, opaque identifiers."""
import hashlib
import json
import re

SCHEMA_VERSION = 1
# Declared per-primitive input schemas, mirrored in the synth prompt (v4-synth-4) so the
# model sees the exact contract the validator enforces. INPUT_KEY_NAMES is pinned here
# and drift-tested against android_actions.KEYS (the runtime truth); INPUT_SCHEMAS keys
# and INPUT_REQUIRED are drift-tested against the kernel registry input schemas.
INPUT_KEY_NAMES = ('app_switch', 'back', 'captions', 'channel_down', 'channel_up', 'delete',
                   'digit_0', 'digit_1', 'digit_2', 'digit_3', 'digit_4', 'digit_5', 'digit_6',
                   'digit_7', 'digit_8', 'digit_9', 'down', 'enter', 'fast_forward', 'guide',
                   'home', 'info', 'last_channel', 'left', 'menu', 'mute', 'next',
                   'notifications', 'ok', 'play_pause', 'power', 'previous', 'rewind', 'right',
                   'search', 'settings', 'sleep', 'stop', 'tv_input', 'up', 'volume_down',
                   'volume_up', 'wakeup')
INPUT_SCHEMAS = {'input.key': {'key': 'string, one of: ' + ', '.join(INPUT_KEY_NAMES)},
                 'setting.set_exact': {'setting': 'string, one of: media_volume, screen_brightness, screen_timeout_ms',
                                       'value': 'integer (kernel range per setting; screen_timeout_ms 10000..1800000)'},
                 'state.read_setting': {'setting': 'string, one of: media_volume, screen_brightness, screen_timeout_ms'}}
INPUT_REQUIRED = {'input.key': ('key',),
                  'setting.set_exact': ('setting', 'value'),
                  'state.read_setting': ('setting',)}
ID = re.compile(r'[a-zA-Z][a-zA-Z0-9_.:-]{0,63}\Z')
BUNDLE_KEYS = {'schema_version', 'bundle_id', 'observed_at', 'devices', 'relays', 'primitives', 'registry_digest'}
SUSPICIOUS = re.compile(r'ignore\b|disregard|system prompt|shutdown|eval\(|;|\bexec\b', re.IGNORECASE)


class V4Error(ValueError):
    pass


def opaque(kind, value):
    h = hashlib.sha256(('%s\x00%s' % (kind, value)).encode()).hexdigest()[:16]
    return 'opaque:%s:%s' % (kind, h)


def canonical(value):
    # Byte-identical to the substrate kernel canonical form (incl. ensure_ascii):
    # one canonicalization across the V4 interface so hashes bind both sides.
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _is_id(v):
    return isinstance(v, str) and bool(ID.fullmatch(v))


def validate_bundle(value):
    if not isinstance(value, dict) or set(value) != BUNDLE_KEYS:
        raise V4Error('BUNDLE_SHAPE')
    if value['schema_version'] != SCHEMA_VERSION:
        raise V4Error('BUNDLE_VERSION')
    if not _is_id(value['bundle_id']):
        raise V4Error('BUNDLE_ID')
    if not isinstance(value['observed_at'], (int, float)):
        raise V4Error('BUNDLE_TIME')
    for d in value['devices']:
        if set(d) != {'opaque_id', 'category', 'permission_scope', 'facts'}:
            raise V4Error('DEVICE_SHAPE')
        for f in d['facts']:
            if set(f) != {'fact_id', 'kind', 'value_class', 'source', 'observed_at', 'evidence_ref'}:
                raise V4Error('FACT_SHAPE')
    if not isinstance(value['relays'], list) or not isinstance(value['primitives'], list):
        raise V4Error('BUNDLE_LISTS')
    return value
