"""§8 relay dashboards: generate, patch, save and restore Companion control sets.

A dashboard is a named list of control definitions installed on one relay
through RemoteControls.set_controls (labels reach the device; skills, targets
and params stay on the PC). Definitions persist in the state file under
'dashboards' so a server reboot or a Companion restart restores the same
approved controls instead of an empty screen.
"""
import copy
import re

_NAME = re.compile(r'[A-Za-z0-9_-]{1,32}')
MAX_SAVED = 32

# Exec-class skills are never one-tap panel buttons: they need the
# interactive approval path every time. Generated panels bind typed
# skills only; the forge validator + set_controls schema checks still apply.
NEVER_BIND = frozenset({'pc_run'})


def _bindable():
    from src.runtime.routing import SKILLS
    return tuple(s for s in SKILLS if s not in NEVER_BIND)


BINDABLE_PATCH_SKILLS = _bindable()


class DashboardError(ValueError):
    pass


def install_patch(controls, relay_id, patch, target, bindable_skills,
                  consent=True, resolve_target=None):
    """Install a model-generated UI patch as the relay's control set.

    patch must already have passed v4_ui.validate_patch (the CLI enforces
    it); this layer re-checks the install-relevant subset: buttons only,
    bindings in the offered allowlist AND the bindable set, labels within
    Companion limits, scalar params. skill params are schema-checked again
    by set_controls. target is resolved to the live device key when a
    resolver is given (keys rotate every discovery).
    """
    if consent is not True:
        raise DashboardError('consent: true is required')
    widgets = patch.get('widgets') if isinstance(patch, dict) else None
    if not isinstance(widgets, list) or not widgets:
        raise DashboardError('patch carries no widgets')
    if not isinstance(target, str) or not target:
        raise DashboardError('a target device label or key is required')
    allowed = set(bindable_skills or ()) - set(NEVER_BIND)
    defs = []
    for w in widgets:
        if not isinstance(w, dict):
            raise DashboardError('bad widget (not an object)')
        if w.get('kind') != 'button':
            raise DashboardError(
                'only button widgets install on the skill-bound path: %r' % (w.get('widget_id'),))
        binding = w.get('binding_primitive')
        if binding not in allowed:
            raise DashboardError('binding %r is not an offered bindable skill' % (binding,))
        label = w.get('label')
        if not isinstance(label, str) or not 0 < len(label) <= 40:
            raise DashboardError('label must be 1-40 characters: %r' % (w.get('widget_id'),))
        if any(ord(ch) < 32 or ord(ch) == 0x7f for ch in label):
            raise DashboardError('label must not contain control characters: %r'
                                 % (w.get('widget_id'),))
        params = w.get('params')
        if not isinstance(params, dict) or \
                any(not isinstance(v, (str, int, float, bool)) for v in params.values()):
            raise DashboardError('params must be scalar-only: %r' % (w.get('widget_id'),))
        defs.append({'label': label, 'skill_id': binding, 'target': target,
                     'params': dict(params)})
    if callable(resolve_target):
        live = resolve_target(target)
        for c in defs:
            c['target'] = live
    return controls.set_controls({'relay_id': relay_id, 'controls': defs, 'consent': True})


def _vacuum(target):
    return [{'label': 'Vacuum start', 'skill_id': 'vacuum_command', 'target': target,
             'params': {'command': 'start'}},
            {'label': 'Vacuum pause', 'skill_id': 'vacuum_command', 'target': target,
             'params': {'command': 'pause'}},
            {'label': 'Return to dock', 'skill_id': 'vacuum_command', 'target': target,
             'params': {'command': 'dock'}},
            {'label': 'Find me', 'skill_id': 'vacuum_command', 'target': target,
             'params': {'command': 'seek'}}]


def _tv(target):
    return [{'label': 'Volume +', 'skill_id': 'tv_volume_step', 'target': target,
             'params': {'direction': 'up'}},
            {'label': 'Volume -', 'skill_id': 'tv_volume_step', 'target': target,
             'params': {'direction': 'down'}},
            {'label': 'YouTube', 'skill_id': 'app_launch', 'target': target,
             'params': {'package': 'com.google.android.youtube.tv'}}]


AREAS = {'vacuum': _vacuum, 'tv': _tv}


def defs(controls, relay_id):
    """Current control definitions installed on a relay (labels, skills, targets, params)."""
    return [{'label': c['label'], 'skill_id': c['skill_id'], 'target': c.get('target'),
             'params': copy.deepcopy(c.get('params') or {})}
            for c in (controls.grants.get(relay_id) or {}).values()]


def create(controls, relay_id, area, target, consent=True):
    """Install a generated capability area as the relay's control set."""
    if area not in AREAS:
        raise DashboardError(f'unknown area {area!r} (known: {sorted(AREAS)})')
    if not isinstance(target, str) or not target:
        raise DashboardError('a target device key is required')
    if consent is not True:
        raise DashboardError('consent: true is required')
    return controls.set_controls({'relay_id': relay_id, 'controls': AREAS[area](target), 'consent': True})


def patch(controls, relay_id, add=(), remove=(), consent=True):
    """Add/remove controls by label. Unknown labels fail loudly, never silently."""
    if consent is not True:
        raise DashboardError('consent: true is required')
    current = defs(controls, relay_id)
    have = {c['label'] for c in current}
    missing = [l for l in remove if l not in have]
    if missing:
        raise DashboardError(f'unknown control label(s): {missing}')
    kept = [c for c in current if c['label'] not in set(remove)]
    return controls.set_controls({'relay_id': relay_id, 'controls': kept + list(add), 'consent': True})


class DashStore:
    """Named dashboards persisted in the state file."""

    def __init__(self, state_store):
        self._s = state_store

    def _all(self):
        try:
            d = self._s.load()
        except Exception:
            return {}
        return copy.deepcopy(d.get('dashboards') or {})

    def save(self, relay_id, name, controls):
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise DashboardError('bad dashboard name (1..32 of A-Za-z0-9_-)')
        if not isinstance(controls, list) or not controls:
            raise DashboardError('cannot save an empty dashboard')
        for c in controls:
            if not isinstance(c, dict) or not c.get('label') or not c.get('skill_id') \
                    or not isinstance(c.get('params'), dict):
                raise DashboardError(f'bad control definition {c!r}'[:200])

        def change(d):
            alld = d.setdefault('dashboards', {})
            names = alld.setdefault('names', {})
            if len(names) >= MAX_SAVED and name not in names:
                raise DashboardError(f'at most {MAX_SAVED} saved dashboards')
            names[name] = {'relay_id': relay_id, 'controls': copy.deepcopy(controls)}
            alld.setdefault('last', {})[relay_id] = name

        try:
            self._s._mutate(change)
        except DashboardError:
            raise
        except Exception as e:  # noqa: BLE001 - store errors surface as dashboard errors
            raise DashboardError(f'store failed: {e}') from None

    def list(self):
        return sorted(self._all().get('names', {}))

    def get(self, name):
        rec = self._all().get('names', {}).get(name)
        if rec is None:
            raise DashboardError(f'unknown dashboard {name!r}')
        return rec

    def delete(self, name):
        if name not in self._all().get('names', {}):
            raise DashboardError(f'unknown dashboard {name!r}')

        def change(d):
            alld = d.setdefault('dashboards', {})
            alld.setdefault('names', {}).pop(name, None)
            for rid, last in list(alld.setdefault('last', {}).items()):
                if last == name:
                    del alld['last'][rid]

        self._s._mutate(change)

    def last(self, relay_id):
        return self._all().get('last', {}).get(relay_id)


def load(store, controls, name, relay_id=None, consent=True):
    """Install a saved dashboard on its relay (or an explicit other relay)."""
    if consent is not True:
        raise DashboardError('consent: true is required')
    rec = store.get(name)
    return controls.set_controls({'relay_id': relay_id or rec['relay_id'],
                                  'controls': rec['controls'], 'consent': True})


def restore_on_reconnect(controls, store, relay_id):
    """Reinstall the relay's last dashboard when it holds no grants (fresh boot
    or revoked-then-repaired relay). Returns the dashboard name, or None when
    there is nothing to restore. Called from the reconnect path."""
    if (controls.grants.get(relay_id) or {}):
        return None
    name = store.last(relay_id)
    if name is None:
        return None
    try:
        store.get(name)
    except DashboardError:
        return None
    load(store, controls, name, relay_id, consent=True)
    return name


def repush_current(controls, relay_id):
    """Re-send the current grants after a reconnect: the Companion may have
    restarted and forgotten its UI while the server still holds the grants.
    Same ids (no generation bump), so queued presses still validate.
    Returns True when pushed."""
    return bool(controls.repush(relay_id))


def pending(store):
    """Relay ids with a saved last dashboard (fresh-boot restore candidates)."""
    try:
        return sorted(store._all().get('last', {}))
    except Exception:
        return []


def ensure_controls(controls, store, relay_id):
    """Reconnect hook: re-push live grants, else restore the last dashboard.
    Returns 'repush', 'restore:<name>' or None. Never raises."""
    try:
        if (controls.grants.get(relay_id) or {}):
            return 'repush' if repush_current(controls, relay_id) else None
        name = restore_on_reconnect(controls, store, relay_id)
        return f'restore:{name}' if name else None
    except Exception:
        return None
