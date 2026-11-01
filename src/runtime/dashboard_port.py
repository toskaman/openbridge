"""Campaign Two §4.9: portable Companion interfaces (dashboard bundles).

A bundle moves an owner-approved dashboard between PCs, relays, or family
members without rebuilding it by hand. It is deliberately NOT a backup of
grants: it carries labels, skill ids and scalar params plus *target hints*,
and no grant generations, relay keys, or approvals. Import always mints a
fresh grant through the trusted ``set_controls`` path.

Trust model (fail-closed at every step):
- Integrity: the bundle embeds a sha256 digest over its canonical payload; any
  edit without re-export is refused before anything else is read.
- Skills: every skill must exist in the routing table and must not be in
  ``NEVER_BIND`` (``pc_run`` stays on the interactive approval path only).
  Params must be scalar-only; ``set_controls`` schema-checks them again.
- Targets: device keys rotate every discovery, so a stored key is meaningless
  on another PC (or a later boot). Export keeps the old target only as an
  opaque ``target_hint``. Import requires the owner to map EVERY hint to a
  live target explicitly (``--target`` for one, ``--target-map`` for many);
  an unmapped hint refuses the whole import and names the missing hints.
- Consent: import needs ``consent is True`` exactly like every install path;
  ``dry_run`` verifies + resolves and installs nothing.

Determinism: export emits no timestamps and the digest covers the canonical
JSON (sorted keys, compact separators, UTF-8), so re-exporting the same
dashboard yields identical bytes. The oracle pins this digest.
"""
import copy
import hashlib
import json

from src.runtime import dashboards as D

FORMAT = 'openbridge-dashboard-bundle'
VERSION = 1

_BUNDLE_KEYS = frozenset({'format', 'version', 'name', 'controls', 'integrity'})
_CONTROL_KEYS = frozenset({'label', 'skill_id', 'target_hint', 'params'})
_SCALAR = (str, int, float, bool)


class PortError(ValueError):
    pass


def _skills():
    from src.runtime.routing import SKILLS
    return SKILLS


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def _digest(payload):
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _payload_of(bundle):
    return {k: bundle[k] for k in ('format', 'version', 'name', 'controls')}


def _check_name(name):
    if not isinstance(name, str) or not D._NAME.fullmatch(name):
        raise PortError('bad dashboard name (1..32 of A-Za-z0-9_-)')


def _check_control_shape(c, skills):
    if not isinstance(c, dict) or set(c) - _CONTROL_KEYS:
        raise PortError('bad control: only {label, skill_id, target_hint, params} allowed')
    label, skill = c.get('label'), c.get('skill_id')
    if not isinstance(label, str) or not 0 < len(label) <= 40:
        raise PortError('label must be 1-40 characters: %r' % (label,))
    if skill not in skills:
        raise PortError('unknown skill %r: refusing bundle' % (skill,))
    if skill in D.NEVER_BIND:
        raise PortError('skill %r is never a one-tap panel button: refusing bundle' % (skill,))
    params = c.get('params')
    if not isinstance(params, dict) or \
            any(not isinstance(v, _SCALAR) for v in params.values()):
        raise PortError('params must be scalar-only: %r' % (label,))
    hint = c.get('target_hint')
    if skills[skill]['targeted']:
        if not isinstance(hint, str) or not hint:
            raise PortError('targeted skill %r needs a target_hint: %r' % (skill, label))
    elif hint is not None:
        raise PortError('untargeted skill %r must not carry a target_hint: %r' % (skill, label))


def _defs_from_store(store, name):
    _check_name(name)
    try:
        rec = store.get(name)
    except D.DashboardError as e:
        raise PortError(str(e)) from None
    return name, rec['controls']


def export_bundle(store=None, name=None, controls=None, relay_id=None):
    """Build a sealed bundle from a saved dashboard (store+name) or from live
    relay definitions (dashboards.defs). Exactly one source is required."""
    from src.fabric import relay as R
    if store is not None and name is not None and controls is None and relay_id is None:
        bundle_name, defs = _defs_from_store(store, name)
    elif store is None and controls is not None and name is not None and relay_id is None:
        _check_name(name)
        bundle_name, defs = name, controls
    else:
        raise PortError('export needs (store + name) or (name + live controls from dashboards.defs)')
    if not isinstance(defs, list) or not defs:
        raise PortError('cannot export an empty dashboard')
    if len(defs) > R.MAX_CONTROLS:
        raise PortError('at most %d controls per bundle' % R.MAX_CONTROLS)
    skills = _skills()
    out = []
    for c in defs:
        if not isinstance(c, dict):
            raise PortError('bad control definition')
        skill = c.get('skill_id')
        if skill not in skills:
            raise PortError('unknown skill %r: refusing export' % (skill,))
        if skill in D.NEVER_BIND:
            raise PortError('skill %r is never portable: refusing export' % (skill,))
        params = c.get('params') or {}
        if not isinstance(params, dict) or \
                any(not isinstance(v, _SCALAR) for v in params.values()):
            raise PortError('params must be scalar-only: %r' % (c.get('label'),))
        label = c.get('label')
        if not isinstance(label, str) or not 0 < len(label) <= 40:
            raise PortError('label must be 1-40 characters: %r' % (label,))
        item = {'label': label, 'skill_id': skill, 'params': copy.deepcopy(params),
                'target_hint': c.get('target') if skills[skill]['targeted'] else None}
        if skills[skill]['targeted'] and not isinstance(item['target_hint'], str):
            raise PortError('targeted skill %r is missing its target: %r' % (skill, label))
        out.append(item)
    payload = {'format': FORMAT, 'version': VERSION, 'name': bundle_name, 'controls': out}
    return dict(payload, integrity={'algo': 'sha256', 'digest': _digest(payload)})


def bundle_digest(bundle):
    return _digest(_payload_of(bundle))


def verify_bundle(bundle):
    """Fail-closed structural + integrity check. Returns the canonical payload
    digest on success; raises PortError naming the first defect otherwise."""
    from src.fabric import relay as R
    if not isinstance(bundle, dict) or set(bundle) - _BUNDLE_KEYS:
        raise PortError('not a dashboard bundle object')
    if bundle.get('format') != FORMAT:
        raise PortError('unknown bundle format %r' % (bundle.get('format'),))
    if bundle.get('version') != VERSION:
        raise PortError('unsupported bundle version %r (this PC reads v%d)'
                        % (bundle.get('version'), VERSION))
    _check_name(bundle.get('name'))
    controls = bundle.get('controls')
    if not isinstance(controls, list) or not controls:
        raise PortError('bundle carries no controls')
    if len(controls) > R.MAX_CONTROLS:
        raise PortError('at most %d controls per bundle' % R.MAX_CONTROLS)
    integ = bundle.get('integrity')
    if not isinstance(integ, dict) or integ.get('algo') != 'sha256' \
            or not isinstance(integ.get('digest'), str):
        raise PortError('bundle has no sha256 integrity seal')
    payload = _payload_of(bundle)
    if _digest(payload) != integ['digest']:
        raise PortError('integrity mismatch: bundle was edited or corrupted after export')
    skills = _skills()
    for c in controls:
        _check_control_shape(c, skills)
    return integ['digest']


def _resolve_targets(bundle, target=None, target_map=None):
    hints = sorted({c['target_hint'] for c in bundle['controls']
                    if c['target_hint'] is not None})
    mapping = dict(target_map or {})
    if target is not None:
        if not isinstance(target, str) or not target:
            raise PortError('target must be a non-empty live device key')
        for h in hints:
            mapping.setdefault(h, target)
    missing = [h for h in hints if h not in mapping or not isinstance(mapping[h], str)
               or not mapping[h]]
    if missing:
        raise PortError('target remap missing for hint(s) %s: pass --target or --target-map'
                        % (missing,))
    return {h: mapping[h] for h in hints}


def plan_import(bundle, target=None, target_map=None, resolve_target=None):
    """Verify + resolve every control to an installable definition without
    installing anything. Returns {'digest', 'name', 'controls', 'targets'}."""
    digest = verify_bundle(bundle)
    targets = _resolve_targets(bundle, target, target_map)
    defs = []
    for c in bundle['controls']:
        live = targets.get(c['target_hint']) if c['target_hint'] is not None else None
        if live is not None and callable(resolve_target):
            live = resolve_target(live)
        item = {'label': c['label'], 'skill_id': c['skill_id'],
                'params': copy.deepcopy(c['params'])}
        if c['target_hint'] is not None:
            item['target'] = live
        defs.append(item)
    return {'digest': digest, 'name': bundle['name'], 'controls': defs, 'targets': targets}


def import_bundle(controls_api, relay_id, bundle, target=None, target_map=None,
                  consent=False, resolve_target=None, store=None, save_as=None):
    """Install a bundle on a relay (fresh grant, owner consent required).

    When ``store`` + ``save_as`` are given the installed definitions are also
    persisted as a named dashboard for later restore-on-reconnect."""
    if consent is not True:
        raise PortError('consent: true is required')
    if not isinstance(relay_id, str) or not relay_id:
        raise PortError('a relay id is required')
    plan = plan_import(bundle, target=target, target_map=target_map,
                       resolve_target=resolve_target)
    state = controls_api.set_controls({'relay_id': relay_id, 'controls': plan['controls'],
                                       'consent': True})
    saved = None
    if store is not None or save_as is not None:
        if store is None or save_as is None:
            raise PortError('store and save_as are required together')
        store.save(relay_id, save_as, plan['controls'])
        saved = save_as
    return {'name': plan['name'], 'relay_id': relay_id,
            'installed': len(plan['controls']), 'targets': plan['targets'],
            'bundle_digest': plan['digest'], 'saved_as': saved, 'state': state}


def dry_run(bundle, target=None, target_map=None, resolve_target=None):
    """Verify + resolve only. Same checks as import, installs nothing."""
    plan = plan_import(bundle, target=target, target_map=target_map,
                       resolve_target=resolve_target)
    return {'name': plan['name'], 'controls': plan['controls'],
            'targets': plan['targets'], 'bundle_digest': plan['digest'],
            'installed': 0}
