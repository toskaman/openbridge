"""§6 Universal Capability Explorer: live per-capability statuses, rules-drafted
layouts, deterministic follow-ups, revocation-aware rendering.

Honesty rules: READY only for probed-supported actions (Android probe),
model-table commands (vacuum) or read-only probes with a live link. Anything
unprobed is DISCOVERABLE, never READY. Saved widgets re-resolve against the
LIVE graph at render: a revoked grant or vanished device disables the button,
never executes from stale state.
"""
import hashlib
import re

from src.fabric.android_actions import ACTIONS as ANDROID_ACTIONS
from src.fabric.android_actions import KEYS, SETTINGS, TV_ONLY
from src.adapters import tuya_local as tuya

STATUSES = ('READY', 'REQUIRES_PERMISSION', 'DISCOVERABLE', 'UNSUPPORTED', 'OFFLINE', 'ERROR')
ANDROID = ('phone', 'tv', 'watch', 'android', 'tablet')
READ_ACTIONS = {'get', 'audio_state', 'screen_state', 'list_apps'}
ORIGINS = ('rules', 'meta', 'user')
WIDGET_KINDS = ('button', 'slider', 'status', 'card', 'text')
LAYOUT_VERSION = 1

_VACUUM_LABELS = {'dock': 'Return to Dock', 'empty_dust': 'Empty dustbin',
                  'reset_side_brush': 'Reset side brush', 'seek': 'Find robot'}


class ExplorerError(ValueError):
    pass


def _pretty(name):
    return ' '.join(str(name).split('_')).capitalize()


def _wid(capability_id):
    return 'w-' + hashlib.sha256(capability_id.encode()).hexdigest()[:12]


def _cid(fp, primitive, action, detail=''):
    return '%s:%s:%s:%s' % (fp or 'unbound', primitive, action, detail)


def _grants_for(links, key):
    return {g for l in (links or []) if l.get('child') == key for g in (l.get('grants') or [])}


def _support(probe, action_key):
    if not isinstance(probe, dict):
        return None
    return (probe.get('actions') or {}).get(action_key)


def _status(grants, need, probe, action_key, blocked_write, effect):
    if not grants:
        return 'OFFLINE', [], 'no live link'
    if blocked_write and effect:
        return 'ERROR', [], blocked_write
    if probe is not None and action_key is not None:
        sup = _support(probe, action_key)
        if sup is False:
            return 'UNSUPPORTED', [], 'probe reports unsupported'
        if sup is None:
            return 'DISCOVERABLE', [], 'not measured by the probe'
    elif probe is None and action_key is not None:
        return 'DISCOVERABLE', [], 'device not probed yet'
    missing = [g for g in need if g not in grants]
    if missing:
        return 'REQUIRES_PERMISSION', missing, 'missing grant: %s' % ','.join(missing)
    return 'READY', [], ''


def _cap(fp, category, primitive, action, args, label, widget, status, requires, reason,
         evidence, extra=None, effect=False):
    detail = args.get('key') or args.get('setting') or args.get('command') or ''
    c = {'capability_id': _cid(fp, primitive, action, detail), 'device_fingerprint': fp,
         'category': category, 'label': label, 'primitive_id': primitive, 'action': action,
         'args': dict(args), 'widget': widget, 'status': status, 'requires': list(requires),
         'reason': reason, 'evidence': evidence, 'effect': bool(effect)}
    if extra:
        c.update(extra)
    return c


def _android_caps(device, grants, probe, fp, blocked_write):
    out = []
    st, req, reason = _status(grants, ['read'], {}, None, False, False)
    out.append(_cap(fp, device['category'], 'device_capabilities', 'probe', {},
                    'Measure support', 'button', st, req, reason, 'builtin'))
    keys = _support(probe, 'key')
    if keys is None:
        keys = [k for k in KEYS if device['category'] == 'tv' or k not in TV_ONLY]
    online = bool(grants)
    for k in keys:
        if device['category'] != 'tv' and k in TV_ONLY:
            st = 'UNSUPPORTED' if online else 'OFFLINE'
            out.append(_cap(fp, device['category'], 'device_action', 'key', {'key': k},
                             _pretty(k), 'button', st, [],
                             'TV-only key' if online else 'no live link', 'catalog', effect=True))
            continue
        st, req, reason = _status(grants, ['control'], probe, 'key', blocked_write, True)
        out.append(_cap(fp, device['category'], 'device_action', 'key', {'key': k},
                         _pretty(k), 'button', st, req, reason, 'probe' if probe else 'catalog',
                         effect=True))
    if device['category'] != 'tv':
        for k in sorted(TV_ONLY):
            if k not in (keys or ()):
                st = 'UNSUPPORTED' if online else 'OFFLINE'
                out.append(_cap(fp, device['category'], 'device_action', 'key', {'key': k},
                                 _pretty(k), 'button', st, [],
                                 'TV-only key' if online else 'no live link', 'catalog', effect=True))
    for name, (_get, _set, span) in SETTINGS.items():
        lo, hi = span
        if probe and name in (probe.get('ranges') or {}):
            lo, hi = (probe['ranges'] or {})[name]
        step = max(1, (hi - lo) // 20)
        st, req, reason = _status(grants, ['control'], probe, 'set:%s' % name, blocked_write, True)
        out.append(_cap(fp, device['category'], 'device_action', 'set', {'setting': name},
                         _pretty(name), 'slider', st, req, reason,
                         'probe' if probe else 'catalog',
                         {'range': [lo, hi], 'step': step}, effect=True))
        st, req, reason = _status(grants, ['read'], probe, 'set:%s' % name, False, False)
        out.append(_cap(fp, device['category'], 'device_action', 'get', {'setting': name},
                         _pretty(name) + ' (read)', 'status', st, req, reason,
                         'probe' if probe else 'catalog'))
    for action in ('audio_state', 'screen_state', 'list_apps'):
        if action not in ANDROID_ACTIONS:
            continue
        st, req, reason = _status(grants, ['read'], probe, action, False, False)
        kind = 'status' if action != 'list_apps' else 'button'
        out.append(_cap(fp, device['category'], 'device_action', action, {},
                         _pretty(action), kind, st, req, reason,
                         'probe' if probe else 'catalog'))
    prompts = {'launch_app': {'type': 'text', 'name': 'package', 'label': 'Package'},
               'open_url': {'type': 'text', 'name': 'url', 'label': 'URL'},
               'text': {'type': 'text', 'name': 'text', 'label': 'Text'},
               'tap': {'type': 'text', 'name': 'xy', 'label': 'x,y'},
               'swipe': {'type': 'text', 'name': 'coords', 'label': 'x1,y1,x2,y2'},
               'long_press': {'type': 'text', 'name': 'key', 'label': 'Key'}}
    for action, prompt in prompts.items():
        if action not in ANDROID_ACTIONS:
            continue
        st, req, reason = _status(grants, ['control'], probe, action, blocked_write, True)
        out.append(_cap(fp, device['category'], 'device_action', action, {},
                         _pretty(action), 'button', st, req, reason,
                         'probe' if probe else 'catalog', {'prompt': prompt}, effect=True))
    return out


def _vacuum_caps(device, grants, fp):
    out = []
    for cmd in tuya.COMMANDS:
        st, req, reason = _status(grants, ['control'], {}, None, False, True)
        extra = {}
        if cmd == 'mode':
            extra = {'prompt': {'type': 'text', 'name': 'value', 'label': 'Mode'}}
        elif cmd == 'move':
            extra = {'prompt': {'type': 'number', 'name': 'move_s', 'label': 'Seconds'}}
        out.append(_cap(fp, device['category'], 'tuya_command', 'command', {'command': cmd},
                         _VACUUM_LABELS.get(cmd, _pretty(cmd)), 'button', st, req, reason,
                         'model-table', extra, effect=True))
    for name, (_dp, values) in tuya.WRITABLE.items():
        st, req, reason = _status(grants, ['control'], {}, None, False, True)
        out.append(_cap(fp, device['category'], 'tuya_setting', 'setting', {'setting': name},
                         _pretty(name), 'button', st, req, reason, 'model-table',
                         {'prompt': {'type': 'enum', 'name': 'value', 'label': _pretty(name),
                                     'options': list(values)}}, effect=True))
    st, req, reason = _status(grants, ['control'], {}, None, False, True)
    out.append(_cap(fp, device['category'], 'tuya_undo', 'undo', {}, 'Undo last change',
                     'button', st, req, reason, 'model-table', effect=True))
    return out


def explore(devices, links, catalog, probes=None, fingerprints=None, registry=(), blocked=None):
    """Live per-capability statuses. `catalog` is the substrate manifest catalog
    (reserved for manifest-bound widgets; executor expansion uses the typed
    action catalogs). `blocked` maps device_key -> [limitation...] for
    write-blocked devices."""
    del catalog
    probes, fingerprints, blocked = probes or {}, fingerprints or {}, blocked or {}
    out = []
    live = {d['key']: d for d in (devices or [])}
    for key, d in live.items():
        grants = _grants_for(links, key)
        fp = fingerprints.get(key)
        probe = probes.get(key)
        bl = blocked.get(key) or []
        if d.get('category') in ANDROID:
            caps = _android_caps(d, grants, probe, fp, '; '.join(bl))
        elif d.get('category') == 'vacuum':
            caps = _vacuum_caps(d, grants, fp)
        else:
            caps = []  # pc/relay/room: no safely tappable executor primitive in v1 (§7/§10)
        out.append({'key': key, 'category': d.get('category'), 'label': d.get('label', key),
                    'online': bool(grants), 'capabilities': caps})
    seen = set(live)
    for d in (registry or []):
        if d.get('key') in seen:
            continue
        fp = None
        if d.get('category') in ANDROID:
            caps = _android_caps(d, set(), None, fp, '')
        elif d.get('category') == 'vacuum':
            caps = _vacuum_caps(d, set(), fp)
        else:
            caps = []
        out.append({'key': d.get('key'), 'category': d.get('category'),
                    'label': d.get('label', d.get('key')), 'online': False, 'capabilities': caps})
    return {'devices': out}


def validate_layout(value):
    if not isinstance(value, dict):
        raise ExplorerError('LAYOUT_MUST_BE_OBJECT')
    if set(value) - {'schema_version', 'layout_id', 'name', 'version', 'origin', 'widgets'}:
        raise ExplorerError('LAYOUT_KEYS')
    if value.get('schema_version') != LAYOUT_VERSION:
        raise ExplorerError('LAYOUT_VERSION')
    if not isinstance(value.get('name'), str) or not value['name'].strip() or len(value['name']) > 80:
        raise ExplorerError('LAYOUT_NAME')
    if not isinstance(value.get('version'), int) or isinstance(value['version'], bool) or value['version'] < 1:
        raise ExplorerError('LAYOUT_VERSION_NUMBER')
    if value.get('origin') not in ORIGINS:
        raise ExplorerError('LAYOUT_ORIGIN')
    if not isinstance(value.get('widgets'), list):
        raise ExplorerError('LAYOUT_WIDGETS')
    for w in value['widgets']:
        _validate_widget(w)
    return value


def _validate_widget(w):
    if not isinstance(w, dict) or w.get('kind') not in WIDGET_KINDS:
        raise ExplorerError('WIDGET_KIND')
    if not isinstance(w.get('label'), str) or not w['label'].strip() or len(w['label']) > 80:
        raise ExplorerError('WIDGET_LABEL')
    if not isinstance(w.get('widget_id'), str) or not w['widget_id']:
        raise ExplorerError('WIDGET_ID')
    if w['kind'] in ('card', 'text'):
        return
    for k in ('capability_id', 'primitive_id', 'action'):
        if not isinstance(w.get(k), str) or not w[k]:
            raise ExplorerError('WIDGET_BINDING: %s' % k)
    if w.get('device_fingerprint') is not None and not isinstance(w['device_fingerprint'], str):
        raise ExplorerError('WIDGET_BINDING: device_fingerprint')
    if not isinstance(w.get('args'), dict) or any(not isinstance(v, (str, int, float, bool, type(None)))
                                                  for v in w['args'].values()):
        raise ExplorerError('WIDGET_ARGS')
    if w['kind'] == 'slider':
        r = w.get('range')
        if not isinstance(r, list) or len(r) != 2 or not all(isinstance(v, int) and not isinstance(v, bool) for v in r):
            raise ExplorerError('WIDGET_RANGE')
    p = w.get('prompt')
    if p is not None:
        if not isinstance(p, dict) or p.get('type') not in ('text', 'number', 'enum'):
            raise ExplorerError('WIDGET_PROMPT')
        if p['type'] == 'enum' and (not isinstance(p.get('options'), list) or not p['options']):
            raise ExplorerError('WIDGET_PROMPT_ENUM')


def _widget_from_cap(c):
    w = {'widget_id': _wid(c['capability_id']), 'kind': c['widget'], 'label': c['label'],
         'capability_id': c['capability_id'], 'device_fingerprint': c['device_fingerprint'],
         'primitive_id': c['primitive_id'], 'action': c['action'], 'args': dict(c['args'])}
    if 'range' in c:
        w['range'] = list(c['range'])
        w['step'] = c.get('step', 1)
    if 'prompt' in c:
        w['prompt'] = dict(c['prompt'])
    w['effect'] = bool(c.get('effect', False))
    return w


def draft_layout(explored, name='All controls'):
    widgets = []
    for d in (explored or {}).get('devices', []):
        if not d.get('online'):
            continue
        usable = [c for c in d.get('capabilities', []) if c['status'] in ('READY', 'REQUIRES_PERMISSION')]
        if not usable:
            continue
        widgets.append({'widget_id': _wid('card:' + d['key']), 'kind': 'card',
                        'label': d.get('label', d['key'])})
        widgets.extend(_widget_from_cap(c) for c in usable)
    return validate_layout({'schema_version': LAYOUT_VERSION, 'name': name, 'version': 1,
                            'origin': 'rules', 'widgets': widgets})


def followup(layout, op, args, expected_version, explored=None):
    layout = validate_layout(dict(layout))
    if layout['version'] != expected_version:
        raise ExplorerError('VERSION_CONFLICT')
    args = args or {}
    widgets = list(layout['widgets'])
    if op == 'clear':
        widgets = [w for w in widgets if w['kind'] == 'card']
    elif op == 'remove_widget':
        wid = args.get('widget_id')
        widgets = [w for w in widgets if w['widget_id'] != wid]
    elif op == 'remove_match':
        m = (args.get('match') or '').lower()
        widgets = [w for w in widgets if w['kind'] == 'card' or m not in w['label'].lower()]
    elif op == 'keep_only':
        m = (args.get('match') or '').lower()
        widgets = [w for w in widgets if w['kind'] == 'card' or m in w['label'].lower()]
    elif op == 'add_capability':
        if explored is None:
            raise ExplorerError('ADD_NEEDS_EXPLORED')
        m = (args.get('match') or '').lower()
        found = None
        for d in explored.get('devices', []):
            for c in d.get('capabilities', []):
                if m in ('%s %s' % (d.get('label', ''), c['label'])).lower():
                    found = c
                    break
            if found:
                break
        if found is None:
            raise ExplorerError('ADD_NO_MATCH')
        w = _widget_from_cap(found)
        if any(x['widget_id'] == w['widget_id'] for x in widgets):
            raise ExplorerError('ADD_ALREADY_PRESENT')
        widgets.append(w)
    else:
        raise ExplorerError('UNKNOWN_OP')
    return validate_layout({**layout, 'widgets': widgets, 'version': layout['version'] + 1})


def parse_followup(text):
    t = (text or '').lower().strip().rstrip('.')
    m = re.fullmatch(r'remove everything except (.+)', t)
    if m:
        return 'keep_only', {'match': m[1].strip()}
    if re.fullmatch(r'(clear|remove all|remove everything)', t):
        return 'clear', {}
    m = re.fullmatch(r'remove the (.+?) button', t)
    if m:
        return 'remove_match', {'match': m[1].strip()}
    m = re.fullmatch(r'remove (.+)', t)
    if m:
        return 'remove_match', {'match': m[1].strip()}
    m = re.fullmatch(r'add (.+)', t)
    if m:
        return 'add_capability', {'match': m[1].strip()}
    raise ExplorerError('FOLLOWUP_UNPARSABLE')


def render_layout(layout, explored):
    layout = validate_layout(dict(layout))
    index = {}
    for d in (explored or {}).get('devices', []):
        for c in d.get('capabilities', []):
            index[(c['device_fingerprint'], c['capability_id'])] = (d['key'], c)
    widgets = []
    for w in layout['widgets']:
        if w['kind'] in ('card', 'text'):
            widgets.append({**w, 'enabled': False})
            continue
        hit = index.get((w.get('device_fingerprint'), w.get('capability_id')))
        if hit is None:
            widgets.append({**w, 'status': 'OFFLINE', 'enabled': False,
                            'requires': [], 'reason': 'stale binding (device not in live graph)',
                            'stale': True})
        else:
            key, c = hit
            widgets.append({**w, 'device_key': key, 'status': c['status'],
                            'effect': c.get('effect', False),
                            'enabled': c['status'] == 'READY',
                            'requires': list(c['requires']), 'reason': c['reason'], 'stale': False})
    out = {'name': layout['name'], 'version': layout['version'], 'widgets': widgets}
    if 'layout_id' in layout:
        out['layout_id'] = layout['layout_id']
    return out
