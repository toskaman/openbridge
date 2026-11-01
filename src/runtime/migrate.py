"""Campaign Two §4.2: dynamic control-surface migration.

Owner request (Watch7 voice evidence): "Remove the volume controls from my
watch and put them on my TV."

A migration moves skill-bound remote controls between paired Companion
interfaces (relays with the `remote_controls` capability):

- propose(): understand which controls are referenced, their bindings, the
  source and destination interfaces, whether the destination can host those
  bindings, which (if any) new permissions that needs, what happens to the
  old grants, and how to roll the interface change back. Ambiguous input
  yields `needs_clarification`, impossible input yields `refusal`; only a
  fully resolved request yields a `proposal`.
- apply(): install the moved controls on the destination FIRST, then remove
  them from the source (a crash between the two leaves a harmless
  duplication, never a loss). Source removal is a re-grant: the generation
  bump gives every remaining control a new id, so a stale device UI that
  missed the update presses dead ids and the server answers REVOKED.
- rollback(): re-install the moved controls on the source and prune them
  from the destination. Interface-only, non-clobbering (owner changes made
  after the migration are kept) and idempotent.

Removing a control NEVER revokes device or relay permissions: migration
touches only RemoteControls grants. apply()/rollback() snapshot every
relay's permissions and every link's grants and refuse to finish if they
changed (an internal guard; the paths below cannot change them).

Simulated Companions only for acceptance (see tests/runtime/test_migrate.py).
"""
import copy
import json
import re
import secrets
import threading

from src.fabric.relay import MAX_CONTROLS
from src.runtime.routing import SKILLS

SCHEMA_VERSION = 1
OUTCOMES = ('proposal', 'needs_clarification', 'refusal')

# Spanning lock: one migration's check+install+remove (or restore+prune) runs
# atomically with respect to other migrations. api_v2 serializes HTTP calls
# elsewhere; this guards the module entry points (threads, tests, drains).
_LOCK = threading.Lock()

_FILLER = {'the', 'a', 'an', 'my', 'controls', 'control', 'buttons', 'button', 'panel', 'all'}

_PATTERNS = (
    # (regex, has_match, has_source, has_dest)
    (re.compile(r'remove (.+?) from (?:my |the )?(.+?) and put them on (?:my |the )?(.+)'), True, True, True),
    (re.compile(r'move (.+?) from (?:my |the )?(.+?) to (?:my |the )?(.+)'), True, True, True),
    (re.compile(r'migrate (.+?) from (?:my |the )?(.+?) to (?:my |the )?(.+)'), True, True, True),
    (re.compile(r'put (.+?) on (?:my |the )?(.+)'), True, False, True),
    (re.compile(r'remove (.+?) from (?:my |the )?(.+)'), True, True, False),
    (re.compile(r'move (.+?) to (?:my |the )?(.+)'), True, False, True),
)


class MigrationError(ValueError):
    """Deterministic migration failure with an HTTP-style status and an
    optional receipt (a partially applied migration the owner can roll back)."""

    def __init__(self, status, message, receipt=None):
        super().__init__(message)
        self.status = status
        self.receipt = receipt


def _rc(server):
    from src.runtime.api_v2 import remote_controls
    return remote_controls(server)


def _router(server):
    from src.runtime.api_v2 import router
    return router(server)


def _snapshot(server):
    snap = getattr(server, 'fabric_snapshot', None)
    if not isinstance(snap, dict):
        return {'devices': [], 'links': []}
    return snap


def parse_request(text):
    """Split owner text into {match, source, dest}. Unknown shapes keep every
    field None (the caller asks for clarification, never guesses)."""
    out = {'match': None, 'source': None, 'dest': None, 'unparsed': False}
    t = (text or '').strip().lower().rstrip('.').strip()
    if not t:
        out['unparsed'] = True
        return out
    for rx, has_m, has_s, has_d in _PATTERNS:
        m = rx.fullmatch(t)
        if not m:
            continue
        groups = [g.strip().strip('"\'') for g in m.groups()]
        i = 0
        if has_m:
            out['match'], i = groups[i] or None, i + 1
        if has_s:
            out['source'], i = groups[i] or None, i + 1
        if has_d:
            out['dest'], i = groups[i] or None, i + 1
        return out
    out['unparsed'] = True
    return out


def relay_device(server, relay_id):
    """(device_key|None, label, category) for a relay via its handle mapping."""
    relays = getattr(getattr(server, 'relays', None), 'relays', {}) or {}
    r = relays.get(relay_id) or {}
    handle = r.get('device_key')
    reg = getattr(server, 'fabric_registry', None)
    devs = getattr(reg, 'devices', {}) or {} if reg is not None else {}
    key = next((k for k, d in devs.items() if handle in (d.get('handles') or {}).values()), None)
    for d in _snapshot(server).get('devices', []):
        if d.get('key') == key:
            return key, d.get('label', key), d.get('category', '')
    if key is not None:
        d = devs.get(key) or {}
        return key, d.get('label', key), d.get('category', '')
    return None, relay_id, ''


def _offered(server):
    relays = getattr(getattr(server, 'relays', None), 'relays', {}) or {}
    out = []
    for rid in sorted(relays):
        key, label, category = relay_device(server, rid)
        out.append({'relay_id': rid, 'device_key': key, 'label': label, 'category': category,
                    'has_controls': bool((_rc(server).grants.get(rid) or {}))})
    return out


def resolve_interface(server, text, role):
    """Resolve `text` to one relay id. Returns (relay_id|None, outcome|None):
    exactly one of them is set. `role` is 'source' or 'destination'."""
    offered = _offered(server)
    if not offered:
        return None, {'outcome': 'refusal', 'reason': 'No paired Companion interfaces; pair one first.'}
    if not (text or '').strip():
        return None, {'outcome': 'needs_clarification',
                      'clarifying_question': 'Which %s interface do you mean? Paired: %s.' % (
                          role, ', '.join('%s (%s)' % (o['label'], o['relay_id']) for o in offered)),
                      'candidates': offered}
    t = text.strip().lower()
    scored = []
    for o in offered:
        label, cat, rid = (o['label'] or '').lower(), (o['category'] or '').lower(), o['relay_id'].lower()
        if t == rid:
            scored.append((0, o))
        elif t == label:
            scored.append((1, o))
        elif t == cat:
            scored.append((2, o))
        elif t in label or label in t:
            scored.append((3, o))
        elif t in rid or rid in t:
            scored.append((4, o))
    if not scored:
        return None, {'outcome': 'refusal',
                      'reason': 'Unknown %s interface %r; paired: %s.' % (
                          role, text, ', '.join('%s (%s)' % (o['label'], o['relay_id']) for o in offered))}
    best = min(s for s, _ in scored)
    hits = [o for s, o in scored if s == best]
    if len(hits) == 1:
        return hits[0]['relay_id'], None
    return None, {'outcome': 'needs_clarification',
                  'clarifying_question': 'Which %s interface do you mean: %s?' % (
                      role, ', '.join('%s (%s)' % (o['label'], o['relay_id']) for o in hits)),
                  'candidates': hits}


def _tokens(match):
    return [w for w in re.findall(r'[a-z0-9]+', (match or '').lower()) if w not in _FILLER]


def match_controls(grants, match):
    """Controls whose label/skill/params contain every match token. Returns
    ([(control_id, grant)...] sorted by id, tokens). Manifest-bound hits are
    included; propose() refuses them (migration is skill-bound only)."""
    tokens = _tokens(match)
    if not tokens:
        return [], tokens
    hits = []
    for cid in sorted(grants or {}):
        g = grants[cid]
        hay = ' '.join([str(g.get('label', '')), str(g.get('skill_id', '')),
                        json.dumps(g.get('params') or {}, sort_keys=True)]).lower()
        if all(t in hay for t in tokens):
            hits.append((cid, g))
    return hits, tokens


def _def_of(cid, grant):
    return {'control_id': cid, 'label': grant.get('label'), 'skill_id': grant.get('skill_id'),
            'target': grant.get('target'), 'params': copy.deepcopy(grant.get('params') or {})}


def _def_key(defn):
    return (defn.get('label'), defn.get('skill_id'), defn.get('target'),
            json.dumps(defn.get('params') or {}, sort_keys=True))


def check_support(server, dest_rid, defs):
    """Can the destination host these bindings? {supported, reason, per_control}.
    Route readiness is advisory (links flap); unknown skills, unresolvable
    targets, a missing Companion capability and a full control set refuse."""
    from src.runtime.routing import RouteError
    relays = getattr(getattr(server, 'relays', None), 'relays', {}) or {}
    if dest_rid not in relays:
        return {'supported': False, 'reason': 'Destination relay is no longer paired.',
                'per_control': []}
    if 'remote_controls' not in (relays[dest_rid].get('capabilities') or ()):
        return {'supported': False,
                'reason': 'This destination Companion has no remote controls; install the current Companion.',
                'per_control': []}
    current = len(_rc(server).grants.get(dest_rid) or {})
    if current + len(defs) > MAX_CONTROLS:
        return {'supported': False,
                'reason': 'Destination holds %d control(s); %d more would exceed the %d limit.' % (
                    current, len(defs), MAX_CONTROLS),
                'per_control': []}
    rt = _router(server)
    per, bad = [], None
    for d in defs:
        row = {'label': d.get('label'), 'skill_id': d.get('skill_id'), 'supported': True, 'reason': '',
               'route': {'selected_route_id': None, 'state': 'UNKNOWN', 'reason': None}}
        if d.get('skill_id') not in SKILLS:
            row.update(supported=False, reason='Unknown skill %r.' % (d.get('skill_id'),))
            bad = bad or row['reason']
        elif SKILLS[d['skill_id']]['targeted']:
            try:
                live = rt.resolve_target(d.get('target'))
            except RouteError:
                row.update(supported=False,
                           reason='Target %r no longer resolves to a live device.' % (d.get('target'),))
                bad = bad or row['reason']
            else:
                try:
                    doc = rt.skill_routes(d['skill_id'], live)
                except RouteError as e:
                    row.update(supported=False, reason=str(e))
                    bad = bad or row['reason']
                else:
                    sel = next((r for r in doc['routes'] if r['route_id'] == doc['selected_route_id']), None)
                    row['route'] = {'selected_route_id': doc['selected_route_id'],
                                    'state': 'READY' if sel else 'UNAVAILABLE',
                                    'reason': None if sel else (doc['routes'][0]['reason'] if doc['routes'] else 'no route')}
        else:
            try:
                doc = rt.skill_routes(d['skill_id'], None)
            except RouteError as e:
                row.update(supported=False, reason=str(e))
                bad = bad or row['reason']
            else:
                row['route'] = {'selected_route_id': doc['selected_route_id'],
                                'state': 'READY' if doc['selected_route_id'] else 'UNAVAILABLE', 'reason': None}
        per.append(row)
    if bad:
        return {'supported': False, 'reason': bad, 'per_control': per}
    return {'supported': True, 'reason': '', 'per_control': per}


def permission_delta(server, defs):
    """Which grants would a migrated binding still be missing? Informational:
    missing grants never block the proposal (the owner grants them separately;
    presses report Unavailable until then)."""
    from src.runtime.routing import RouteError
    rt = _router(server)
    missing, unavailable, seen = [], [], set()
    for d in defs:
        skill = d.get('skill_id')
        if skill not in SKILLS:
            continue
        try:
            live = rt.resolve_target(d.get('target')) if SKILLS[skill]['targeted'] else None
            doc = rt.skill_routes(skill, live)
        except RouteError as e:
            unavailable.append({'skill_id': skill, 'target': d.get('target'), 'error': e.code})
            continue
        if doc['selected_route_id']:
            continue
        for r in doc['routes']:
            if r['reason'] == 'grant_insufficient' and isinstance(r.get('reason_detail'), dict):
                det = r['reason_detail']
                key = (det.get('missing_grant'), det.get('blocking_device_key'), d.get('target'))
                if key not in seen:
                    seen.add(key)
                    missing.append({'skill_id': skill, 'target': d.get('target'),
                                    'missing_grant': det.get('missing_grant'),
                                    'hop_index': det.get('hop_index'),
                                    'blocking_device_key': det.get('blocking_device_key')})
    return {'new_permissions_required': bool(missing), 'missing': missing,
            'unavailable': unavailable, 'checked': len(defs)}


def _iface(server, rid):
    key, label, category = relay_device(server, rid)
    return {'relay_id': rid, 'device_key': key, 'label': label, 'category': category}


def propose(server, text=None, source=None, target=None, match=None):
    """Discriminated migration proposal: {'outcome': proposal |
    needs_clarification | refusal, ...}. Explicit kwargs override parsed text."""
    parsed = parse_request(text) if text is not None else {'match': None, 'source': None, 'dest': None}
    want_match = match if match is not None else parsed.get('match')
    want_source = source if source is not None else parsed.get('source')
    want_dest = target if target is not None else parsed.get('dest')
    if text is not None and parsed.get('unparsed') and match is None and source is None and target is None:
        return {'outcome': 'needs_clarification',
                'clarifying_question': ('I could not tell which controls to move, or from where to where. '
                                        'For example: "Remove the volume controls from my watch and put them on my TV."'),
                'candidates': _offered(server)}
    missing = [name for name, v in (('controls', want_match), ('source interface', want_source),
                                    ('destination interface', want_dest)) if not (v or '').strip()]
    if missing:
        return {'outcome': 'needs_clarification',
                'clarifying_question': 'Which %s? For example: "Remove the volume controls from my watch and put them on my TV."' % (
                    ' and '.join(missing),),
                'candidates': _offered(server)}
    src_rid, outcome = resolve_interface(server, want_source, 'source')
    if outcome is not None:
        return outcome
    dst_rid, outcome = resolve_interface(server, want_dest, 'destination')
    if outcome is not None:
        return outcome
    if src_rid == dst_rid:
        return {'outcome': 'refusal',
                'reason': 'Source and destination are the same interface; nothing to migrate.'}
    rc = _rc(server)
    grants = rc.grants.get(src_rid) or {}
    if not grants:
        return {'outcome': 'refusal',
                'reason': 'The source interface holds no controls; nothing to migrate.'}
    hits, tokens = match_controls(grants, want_match)
    if not tokens:
        return {'outcome': 'needs_clarification',
                'clarifying_question': 'Which controls on %s should I move? It has: %s.' % (
                    _iface(server, src_rid)['label'], ', '.join(sorted({g.get('label', '?') for g in grants.values()}))),
                'candidates': _offered(server)}
    if not hits:
        return {'outcome': 'refusal',
                'reason': 'No controls matching %r on %s; it has: %s.' % (
                    want_match, _iface(server, src_rid)['label'],
                    ', '.join(sorted({g.get('label', '?') for g in grants.values()})))}
    manifest_hits = [cid for cid, g in hits if g.get('kind') == 'manifest']
    if manifest_hits:
        return {'outcome': 'refusal',
                'reason': 'Manifest-bound controls cannot migrate on the skill path; re-issue them on the destination instead.'}
    defs = [_def_of(cid, g) for cid, g in hits]
    support = check_support(server, dst_rid, defs)
    if not support['supported']:
        return {'outcome': 'refusal', 'reason': support['reason'], 'target_support': support}
    delta = permission_delta(server, defs)
    src, dst = _iface(server, src_rid), _iface(server, dst_rid)
    return {'outcome': 'proposal',
            'proposal': {
                'schema_version': SCHEMA_VERSION,
                'source': src, 'destination': dst, 'controls': defs,
                'target_support': support, 'permission_delta': delta,
                'old_grant_disposition': {
                    'action': 'revoke_source_controls',
                    'revoked_control_ids': [d['control_id'] for d in defs],
                    'source_generation_before': rc._grant_versions.get(src_rid, 0),
                    'device_permissions_untouched': True,
                    'relay_permissions_untouched': True,
                    'note': ('The source grant is replaced (generation bump): the listed ids stop '
                             'dispatching and answer REVOKED. No device or relay permission is revoked.')},
                'rollback': {
                    'eligible': True,
                    'plan': ['Re-install %d control(s) on %s' % (len(defs), src['label']),
                             'Remove them from %s' % (dst['label'],)],
                    'note': 'Interface-only change; rollback re-installs and prunes controls without touching permissions.'},
                'consent_required': True}}


def validate_proposal(value):
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA_VERSION:
        raise MigrationError(400, 'Proposal schema_version %d is required.' % SCHEMA_VERSION)
    for k in ('source', 'destination', 'controls', 'old_grant_disposition'):
        if k not in value:
            raise MigrationError(400, 'Proposal misses %r.' % k)
    for k in ('source', 'destination'):
        if not isinstance(value[k], dict) or not isinstance(value[k].get('relay_id'), str):
            raise MigrationError(400, 'Proposal %s.relay_id must be a string.' % k)
    if value['source']['relay_id'] == value['destination']['relay_id']:
        raise MigrationError(400, 'Source and destination must differ.')
    if not isinstance(value['controls'], list) or not value['controls']:
        raise MigrationError(400, 'Proposal carries no controls.')
    for d in value['controls']:
        if not isinstance(d, dict) or not isinstance(d.get('control_id'), str) \
                or not isinstance(d.get('label'), str) or d.get('skill_id') not in SKILLS \
                or not isinstance(d.get('params'), dict):
            raise MigrationError(400, 'Proposal carries a malformed control.')
    disp = value['old_grant_disposition']
    if not isinstance(disp, dict) or disp.get('action') != 'revoke_source_controls' \
            or not isinstance(disp.get('revoked_control_ids'), list):
        raise MigrationError(400, 'Proposal old_grant_disposition is malformed.')
    return value


def _permission_snapshot(server):
    relays = getattr(getattr(server, 'relays', None), 'relays', {}) or {}
    perms = {rid: copy.deepcopy(r.get('permissions') or {}) for rid, r in relays.items()}
    grants = [(l.get('parent'), l.get('child'), l.get('transport'), tuple(sorted(l.get('grants') or ())))
              for l in _snapshot(server).get('links', [])]
    return perms, sorted(grants)


def _permission_guard(server, before):
    if _permission_snapshot(server) != before:
        raise MigrationError(500, 'Internal error: permissions changed during migration; refusing to finish.')


def _strip_ids(defs):
    return [{'label': d['label'], 'skill_id': d['skill_id'], 'target': d.get('target'),
             'params': copy.deepcopy(d.get('params') or {})} for d in defs]


def apply(server, proposal, consent):
    """Execute a proposal: install on the destination first, then remove from
    the source. Returns a client-held receipt for rollback()."""
    from src.fabric.relay import RelayError
    from src.runtime.remote_controls import RemoteControlError
    if consent is not True:
        raise MigrationError(400, 'consent: true is required.')
    proposal = validate_proposal(copy.deepcopy(proposal))
    with _LOCK:
        return _apply_locked(server, proposal, RelayError, RemoteControlError)


def _apply_locked(server, proposal, RelayError, RemoteControlError):
    src_rid, dst_rid = proposal['source']['relay_id'], proposal['destination']['relay_id']
    rc = _rc(server)
    live_src = rc.grants.get(src_rid) or {}
    if any(cid not in live_src for cid in proposal['old_grant_disposition']['revoked_control_ids']):
        raise MigrationError(409, 'Source controls changed since the proposal; re-propose.')
    migrated = proposal['controls']
    support = check_support(server, dst_rid, migrated)
    if not support['supported']:
        raise MigrationError(409, support['reason'])
    before = _permission_snapshot(server)
    gen_src_before = rc._grant_versions.get(src_rid, 0)
    gen_dst_before = rc._grant_versions.get(dst_rid, 0)
    dest_defs = [{'label': g['label'], 'skill_id': g['skill_id'], 'target': g.get('target'),
                  'params': copy.deepcopy(g.get('params') or {})}
                 for _, g in sorted((rc.grants.get(dst_rid) or {}).items())]
    try:
        rc.set_controls({'relay_id': dst_rid, 'controls': dest_defs + _strip_ids(migrated), 'consent': True})
    except (RemoteControlError, RelayError) as e:
        _permission_guard(server, before)
        raise MigrationError(getattr(e, 'status', 409), 'Destination install failed: %s' % e) from None
    doomed = set(proposal['old_grant_disposition']['revoked_control_ids'])
    receipt = {'schema_version': SCHEMA_VERSION, 'migration_id': 'mig-' + secrets.token_hex(6),
               'source': proposal['source'], 'destination': proposal['destination'],
               'migrated': migrated, 'revoked_control_ids': sorted(doomed),
               'source_generation_before': gen_src_before, 'destination_generation_before': gen_dst_before,
               'source_generation_after': rc._grant_versions.get(src_rid, 0),
               'destination_generation_after': rc._grant_versions.get(dst_rid, 0),
               'permission_delta': proposal.get('permission_delta', {})}
    # Re-check the source under the spanning lock: an owner edit landing
    # between the pre-check and now must 409 with a receipt, never silently
    # change what is removed.
    fresh_src = rc.grants.get(src_rid) or {}
    if any(cid not in fresh_src for cid in proposal['old_grant_disposition']['revoked_control_ids']):
        raise MigrationError(409, 'Source controls changed during migration; '
                                  'the destination holds a copy, roll back with the receipt.',
                             receipt=receipt)
    kept = [{'label': g['label'], 'skill_id': g['skill_id'], 'target': g.get('target'),
             'params': copy.deepcopy(g.get('params') or {})}
            for cid, g in sorted(fresh_src.items()) if cid not in doomed]
    try:
        rc.set_controls({'relay_id': src_rid, 'controls': kept, 'consent': True})
    except (RemoteControlError, RelayError) as e:
        _permission_guard(server, before)
        raise MigrationError(getattr(e, 'status', 409),
                             'Destination installed but source removal failed: %s; roll back with the receipt.' % e,
                             receipt=receipt) from None
    receipt['source_generation_after'] = rc._grant_versions.get(src_rid, 0)
    _permission_guard(server, before)
    return receipt


def validate_receipt(value):
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA_VERSION:
        raise MigrationError(400, 'Receipt schema_version %d is required.' % SCHEMA_VERSION)
    for k in ('migration_id', 'source', 'destination', 'migrated'):
        if k not in value:
            raise MigrationError(400, 'Receipt misses %r.' % k)
    for k in ('source', 'destination'):
        if not isinstance(value[k], dict) or not isinstance(value[k].get('relay_id'), str):
            raise MigrationError(400, 'Receipt %s.relay_id must be a string.' % k)
    if not isinstance(value['migrated'], list) or not value['migrated']:
        raise MigrationError(400, 'Receipt carries no migrated controls.')
    for d in value['migrated']:
        if not isinstance(d, dict) or not isinstance(d.get('label'), str) or d.get('skill_id') not in SKILLS \
                or not isinstance(d.get('params'), dict):
            raise MigrationError(400, 'Receipt carries a malformed control.')
    return value


def rollback(server, receipt, consent):
    """Undo a migration without clobbering later owner changes: re-add the
    migrated controls to the source (skipping ones already there) and prune
    exactly those from the destination. Idempotent."""
    from src.fabric.relay import RelayError
    from src.runtime.remote_controls import RemoteControlError
    if consent is not True:
        raise MigrationError(400, 'consent: true is required.')
    receipt = validate_receipt(copy.deepcopy(receipt))
    with _LOCK:
        return _rollback_locked(server, receipt, RelayError, RemoteControlError)


def _rollback_locked(server, receipt, RelayError, RemoteControlError):
    src_rid, dst_rid = receipt['source']['relay_id'], receipt['destination']['relay_id']
    rc = _rc(server)
    relays = getattr(getattr(server, 'relays', None), 'relays', {}) or {}
    if src_rid not in relays:
        raise MigrationError(409, 'Source relay is no longer paired; cannot restore.')
    before = _permission_snapshot(server)
    migrated = receipt['migrated']
    keys = {_def_key(d) for d in migrated}
    # Generation comparison: the receipt recorded both sides' post-migration
    # generations. An exact match proves no intervening writes, so def_key
    # matching is unambiguous. Drift (owner edits, a prior rollback) is
    # tolerated per the non-clobbering contract — but identical-looking new
    # controls on the destination are then ambiguous ownership: pruning by
    # def_key would delete the owner's new control, so that 409s instead.
    src_after = receipt.get('source_generation_after')
    dst_after = receipt.get('destination_generation_after')
    drifted = []
    if src_after is not None and rc._grant_versions.get(src_rid, 0) != src_after:
        drifted.append('source')
    if dst_after is not None and dst_rid in relays \
            and rc._grant_versions.get(dst_rid, 0) != dst_after:
        drifted.append('destination')
    if dst_rid in relays and (drifted or src_after is None or dst_after is None):
        want, have_dst = {}, {}
        for d in migrated:
            want[_def_key(d)] = want.get(_def_key(d), 0) + 1
        for _, g in (rc.grants.get(dst_rid) or {}).items():
            k = _def_key({'label': g.get('label'), 'skill_id': g.get('skill_id'),
                          'target': g.get('target'), 'params': g.get('params') or {}})
            have_dst[k] = have_dst.get(k, 0) + 1
        collisions = sorted({d.get('label', '?') for d in migrated
                             if have_dst.get(_def_key(d), 0) > want.get(_def_key(d), 0)})
        if collisions:
            raise MigrationError(409, 'Destination holds new identical control(s) %s created '
                                      'after the migration%s; remove or rename them, then roll back.'
                                 % (', '.join(repr(c) for c in collisions),
                                    ' (%s changed)' % ' and '.join(drifted) if drifted else ''))
    notes = []
    current_src = [{'label': g['label'], 'skill_id': g['skill_id'], 'target': g.get('target'),
                    'params': copy.deepcopy(g.get('params') or {})}
                   for _, g in sorted((rc.grants.get(src_rid) or {}).items())]
    have = {_def_key(d) for d in current_src}
    missing = [d for d in _strip_ids(migrated) if _def_key(d) not in have]
    try:
        rc.set_controls({'relay_id': src_rid, 'controls': current_src + missing, 'consent': True})
    except (RemoteControlError, RelayError) as e:
        _permission_guard(server, before)
        raise MigrationError(getattr(e, 'status', 409), 'Source restore failed: %s' % e) from None
    notes.append('restored %d control(s) on %s' % (len(missing), receipt['source'].get('label', src_rid)))
    if dst_rid not in relays:
        notes.append('destination relay is gone; its migrated controls died with it')
    else:
        current_dst = [{'label': g['label'], 'skill_id': g['skill_id'], 'target': g.get('target'),
                        'params': copy.deepcopy(g.get('params') or {})}
                       for _, g in sorted((rc.grants.get(dst_rid) or {}).items())]
        pruned = [d for d in current_dst if _def_key(d) not in keys]
        try:
            rc.set_controls({'relay_id': dst_rid, 'controls': pruned, 'consent': True})
        except (RemoteControlError, RelayError) as e:
            _permission_guard(server, before)
            raise MigrationError(getattr(e, 'status', 409), 'Destination prune failed: %s' % e) from None
        notes.append('removed %d migrated control(s) from %s' % (
            len(current_dst) - len(pruned), receipt['destination'].get('label', dst_rid)))
    _permission_guard(server, before)
    return {'migration_id': receipt['migration_id'], 'rolled_back': True, 'notes': notes}
