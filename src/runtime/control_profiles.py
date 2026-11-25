"""Custom control profiles: owner-made button sets for each Companion screen.

A profile is a named list of buttons the owner builds by hand (or copies from
what an AI proposal installed) for one paired Companion screen: a TV, a watch
or a phone. Each screen can keep several profiles ("Movie night", "Cleaning")
and switch between them.

What a profile stores, per button: the text shown on the screen, the typed
skill it runs, the device it acts on and scalar params. Devices are stored by
their label (stable across discoveries) with the last known key as a hint;
keys rotate every discovery, so the live key is resolved when the profile is
sent to the screen.

Trust model: saving a profile installs nothing. Sending it to a screen goes
through RemoteControls.set_controls with consent: true, the same owner path as
every other install (skill catalog, label limits, params schema, grant
generation, relay-key binding). ``pc_run`` is never bindable to a button.
Profiles live in runtime-state.json under ``control_profiles``.
"""
import copy
import hashlib
import json
import secrets
import time

from src.fabric import relay as fabric_relay

MAX_PROFILES = 16            # per screen
MAX_SCREENS = 64
MAX_NAME = 40
MAX_LABEL = 40
NEVER_BIND = frozenset({'pc_run'})
_SCALAR = (str, int, float, bool)


class ProfileError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _clean_text(value, what, limit):
    if not isinstance(value, str):
        raise ProfileError(f'{what} must be text')
    value = ' '.join(value.split())
    if not 0 < len(value) <= limit:
        raise ProfileError(f'{what} must be 1-{limit} characters')
    if any(ord(ch) < 32 or ord(ch) == 0x7f for ch in value):
        raise ProfileError(f'{what} must not contain control characters')
    return value


def _relay_id(value):
    if not isinstance(value, str) or not 0 < len(value) <= 96:
        raise ProfileError('relay_id is required')
    return value


def digest(buttons):
    """Fingerprint of what a profile puts on a screen (order matters)."""
    rows = [[b['label'], b['skill_id'], b.get('device'), b.get('params') or {}] for b in buttons]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]


def check_buttons(server, buttons):
    """Validate and normalize a button list. Returns the clean list."""
    from src.runtime.api_v2 import router
    from src.runtime.routing import SKILLS, RouteError
    if not isinstance(buttons, list):
        raise ProfileError('buttons must be a list')
    if len(buttons) > fabric_relay.MAX_CONTROLS:
        raise ProfileError(f'A screen shows at most {fabric_relay.MAX_CONTROLS} buttons')
    out, seen = [], set()
    for i, b in enumerate(buttons, 1):
        if not isinstance(b, dict) or set(b) - {'label', 'skill_id', 'device', 'device_key', 'params'}:
            raise ProfileError(f'Button {i}: expected {{label, skill_id, device, device_key, params}}')
        label = _clean_text(b.get('label'), f'Button {i} text', MAX_LABEL)
        if label.casefold() in seen:
            raise ProfileError(f'Two buttons are called "{label}"; give each button its own text')
        seen.add(label.casefold())
        skill = b.get('skill_id')
        if skill not in SKILLS or skill in NEVER_BIND:
            raise ProfileError(f'"{label}": this action cannot be put on a button')
        params = b.get('params') or {}
        if not isinstance(params, dict) or any(not isinstance(v, _SCALAR) for v in params.values()):
            raise ProfileError(f'"{label}": options must be simple values')
        try:
            router(server)._validate_input(skill, params)
        except RouteError as e:
            raise ProfileError(f'"{label}": {e}') from None
        device = b.get('device')
        key = b.get('device_key')
        if SKILLS[skill]['targeted']:
            device = _clean_text(device, f'"{label}": device', 80) if device is not None else None
            if key is not None and (not isinstance(key, str) or not 0 < len(key) <= 96):
                raise ProfileError(f'"{label}": bad device reference')
            if device is None and key is None:
                raise ProfileError(f'"{label}": choose the device this button controls')
        else:
            device, key = None, None
        out.append({'label': label, 'skill_id': skill, 'device': device, 'device_key': key,
                    'params': copy.deepcopy(params)})
    return out


class ProfileStore:
    """Profiles persisted in the runtime state file, grouped by relay (screen)."""

    def __init__(self, state_store, clock=time.time):
        self._s, self.clock = state_store, clock

    def _all(self):
        try:
            d = self._s.load()
        except Exception:  # noqa: BLE001 - an unreadable store reads as empty, writes still fail loudly
            return {}
        data = d.get('control_profiles')
        return copy.deepcopy(data) if isinstance(data, dict) else {}

    def all(self):
        return self._all()

    def screen(self, relay_id):
        s = self._all().get(relay_id) or {}
        return {'active': s.get('active'), 'applied': s.get('applied'), 'profiles': list(s.get('profiles') or [])}

    def get(self, relay_id, pid):
        for p in self.screen(relay_id)['profiles']:
            if p['id'] == pid:
                return p
        raise ProfileError('Unknown profile', 404)

    def _mutate(self, fn):
        def change(d):
            data = d.setdefault('control_profiles', {})
            if not isinstance(data, dict):
                data = d['control_profiles'] = {}
            return fn(data)
        box = {}

        def wrapped(d):
            try:
                box['r'] = change(d)
            except ProfileError as e:      # aborts the write; the store would rewrap it as a state error
                box['err'] = e
                raise
        try:
            self._s._mutate(wrapped)
        except Exception as e:  # noqa: BLE001 - store errors surface as profile errors
            if 'err' in box:
                raise box['err'] from None
            raise ProfileError(f'Could not save: {e}', 409) from None
        return box.get('r')

    def save(self, relay_id, name, buttons, pid=None):
        """Create (no pid) or update a profile. buttons must come from check_buttons."""
        relay_id = _relay_id(relay_id)
        name = _clean_text(name, 'Profile name', MAX_NAME)
        now = int(self.clock())

        def fn(data):
            if relay_id not in data and len(data) >= MAX_SCREENS:
                raise ProfileError(f'At most {MAX_SCREENS} screens keep profiles')
            s = data.setdefault(relay_id, {'active': None, 'applied': None, 'profiles': []})
            profiles = s.setdefault('profiles', [])
            if any(p['name'].casefold() == name.casefold() and p['id'] != pid for p in profiles):
                raise ProfileError(f'A profile called "{name}" already exists on this screen')
            if pid is None:
                if len(profiles) >= MAX_PROFILES:
                    raise ProfileError(f'At most {MAX_PROFILES} profiles per screen')
                rec = {'id': 'p-' + secrets.token_hex(4), 'name': name, 'buttons': buttons,
                       'created_at': now, 'updated_at': now}
                profiles.append(rec)
                return copy.deepcopy(rec)
            for p in profiles:
                if p['id'] == pid:
                    p.update(name=name, buttons=buttons, updated_at=now)
                    return copy.deepcopy(p)
            raise ProfileError('Unknown profile', 404)
        return self._mutate(fn)

    def delete(self, relay_id, pid):
        relay_id = _relay_id(relay_id)

        def fn(data):
            s = data.get(relay_id) or {}
            profiles = s.get('profiles') or []
            if not any(p['id'] == pid for p in profiles):
                raise ProfileError('Unknown profile', 404)
            s['profiles'] = [p for p in profiles if p['id'] != pid]
            if s.get('active') == pid:
                s['active'] = None
            if not s['profiles'] and not s.get('active'):
                data.pop(relay_id, None)
            return True
        return self._mutate(fn)

    def mark_applied(self, relay_id, pid, dig):
        def fn(data):
            s = data.setdefault(relay_id, {'active': None, 'applied': None, 'profiles': []})
            s['active'] = pid
            s['applied'] = {'profile_id': pid, 'digest': dig, 'at': int(self.clock())} if pid else None
            return True
        return self._mutate(fn)

    def pending(self):
        """Relay ids with an active profile (fresh-boot restore candidates)."""
        return sorted(rid for rid, s in self._all().items() if isinstance(s, dict) and s.get('active'))


def _store(server):
    from src.runtime.state_store import StateStore
    st = StateStore.for_server(server)
    if st is None:
        raise ProfileError('No state store on this server', 409)
    return ProfileStore(st)


def _snapshot_devices(server):
    snap = getattr(server, 'fabric_snapshot', None)
    return snap.get('devices', []) if isinstance(snap, dict) else []


def _resolve(server, b):
    """Live device key for a saved button, or a ProfileError naming the device."""
    from src.runtime.api_v2 import router
    from src.runtime.routing import RouteError
    keys = {d.get('key') for d in _snapshot_devices(server)}
    for ref in (b.get('device'), b.get('device_key')):
        if not ref:
            continue
        if ref in keys:
            return ref
        try:
            return router(server).resolve_target(ref)
        except RouteError:
            continue
    raise ProfileError(f'"{b["label"]}": {b.get("device") or "its device"} is not found right now. '
                       'Run Discover on the Devices page, then send again.', 409)


def to_controls(server, buttons):
    from src.runtime.routing import SKILLS
    out = []
    for b in buttons:
        c = {'label': b['label'], 'skill_id': b['skill_id'], 'params': copy.deepcopy(b['params'])}
        if SKILLS[b['skill_id']]['targeted']:
            c['target'] = _resolve(server, b)
        out.append(c)
    return out


def _forget_dashboard(server, relay_id):
    """The owner's latest choice wins on reconnect: stop restoring an older dashboard on this screen."""
    from src.runtime.state_store import StateStore
    st = StateStore.for_server(server)
    if st is None:
        return

    def change(d):
        last = (d.get('dashboards') or {}).get('last')
        if isinstance(last, dict):
            last.pop(relay_id, None)
    try:
        st._mutate(change)
    except Exception:  # noqa: BLE001 - best effort; the profile is already on the screen
        pass


def live_buttons(server, rc, relay_id):
    """What the screen shows now, as editable buttons when they are plain typed controls."""
    names = {d.get('key'): d.get('label') for d in _snapshot_devices(server)}
    rows = []
    for cid, c in (rc.grants.get(relay_id) or {}).items():
        editable = c.get('kind') not in ('manifest', 'skill')
        row = {'control_id': cid, 'label': c['label'], 'skill_id': c.get('skill_id'), 'editable': editable,
               'source': c.get('kind') or 'button'}
        if editable:
            key = c.get('target')
            row.update(device=names.get(key) or key, device_key=key, params=copy.deepcopy(c.get('params') or {}))
        rows.append(row)
    return rows


# ---------- API ----------

def state(server):
    from src.runtime.api_v2 import remote_controls
    from src.runtime.routing import SKILLS
    store = _store(server)
    rc = remote_controls(server)
    screens = {}
    for rid, s in store.all().items():
        if isinstance(s, dict):
            screens[rid] = {'active': s.get('active'), 'applied': s.get('applied'), 'profiles': s.get('profiles') or []}
    for rid in set(rc.grants) | set(screens):
        screens.setdefault(rid, {'active': None, 'applied': None, 'profiles': []})
    out = {}
    for rid, s in screens.items():
        live = live_buttons(server, rc, rid)
        for p in s['profiles']:
            p['digest'] = digest(p['buttons'])
        out[rid] = dict(s, live=live)
    bindable = sorted(k for k in SKILLS if k not in NEVER_BIND)
    return {'screens': out, 'max_buttons': fabric_relay.MAX_CONTROLS, 'max_profiles': MAX_PROFILES,
            'bindable_skills': bindable}


def save(server, body):
    if not isinstance(body, dict) or set(body) - {'relay_id', 'profile_id', 'name', 'buttons'}:
        raise ProfileError('Expected {relay_id, profile_id?, name, buttons}')
    buttons = check_buttons(server, body.get('buttons') or [])
    pid = body.get('profile_id')
    if pid is not None and not isinstance(pid, str):
        raise ProfileError('profile_id must be text')
    prof = _store(server).save(body.get('relay_id'), body.get('name'), buttons, pid)
    prof['digest'] = digest(prof['buttons'])
    return {'profile': prof}


def delete(server, body):
    if not isinstance(body, dict):
        raise ProfileError('Expected {relay_id, profile_id}')
    _store(server).delete(body.get('relay_id'), body.get('profile_id'))
    return {'deleted': body.get('profile_id')}


def apply(server, body):
    """Send a saved profile to its screen (owner consent required)."""
    from src.runtime.api_v2 import remote_controls
    if not isinstance(body, dict) or body.get('consent') is not True:
        raise ProfileError('consent: true is required')
    rid = _relay_id(body.get('relay_id'))
    store = _store(server)
    prof = store.get(rid, body.get('profile_id'))
    buttons = check_buttons(server, prof['buttons'])     # the catalog may have changed since saving
    controls = to_controls(server, buttons)
    result = remote_controls(server).set_controls({'relay_id': rid, 'controls': controls, 'consent': True})
    store.mark_applied(rid, prof['id'], digest(buttons))
    _forget_dashboard(server, rid)
    return {'applied': prof['id'], 'name': prof['name'], 'buttons': len(controls), 'state': result}


def capture(server, body):
    """Copy what the screen shows now (for example controls an AI proposal installed) into a new profile."""
    from src.runtime.api_v2 import remote_controls
    if not isinstance(body, dict):
        raise ProfileError('Expected {relay_id, name}')
    rid = _relay_id(body.get('relay_id'))
    live = live_buttons(server, remote_controls(server), rid)
    if not live:
        raise ProfileError('This screen shows no buttons right now')
    plain = [b for b in live if b['editable']]
    if not plain:
        raise ProfileError('The buttons on this screen come from an approved plan or a saved skill and cannot be copied; '
                           'build a profile with the same actions instead')
    buttons = check_buttons(server, [{k: b[k] for k in ('label', 'skill_id', 'device', 'device_key', 'params')}
                                     for b in plain])
    prof = _store(server).save(rid, body.get('name') or 'On screen now', buttons)
    prof['digest'] = digest(prof['buttons'])
    return {'profile': prof, 'skipped': len(live) - len(plain)}


def clear(server, body):
    """Remove every button from a screen. Saved profiles stay."""
    from src.runtime.api_v2 import remote_controls
    if not isinstance(body, dict) or body.get('consent') is not True:
        raise ProfileError('consent: true is required')
    rid = _relay_id(body.get('relay_id'))
    result = remote_controls(server).set_controls({'relay_id': rid, 'controls': [], 'consent': True})
    try:
        _store(server).mark_applied(rid, None, None)
    except ProfileError:
        pass
    _forget_dashboard(server, rid)
    return {'cleared': rid, 'state': result}


def restore_active(server, rc, relay_id):
    """Reconnect hook: a screen with no buttons gets its active profile back. Never raises."""
    try:
        if rc.grants.get(relay_id):
            return None
        store = _store(server)
        s = store.screen(relay_id)
        if not s['active']:
            return None
        prof = store.get(relay_id, s['active'])
        controls = to_controls(server, check_buttons(server, prof['buttons']))
        rc.set_controls({'relay_id': relay_id, 'controls': controls, 'consent': True})
        return prof['id']
    except Exception:  # noqa: BLE001 - a failed restore leaves the screen empty, the owner re-sends
        return None


def pending(server):
    try:
        return _store(server).pending()
    except Exception:  # noqa: BLE001
        return []
