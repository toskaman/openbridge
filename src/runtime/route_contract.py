"""B2 route-truth contract tooling (rev 2): schema validation, cross-field rules, stable IDs and invocation dedup.

Shared by the backend implementation and by contract tests; the UI tests load the same fixtures
(tests/contracts/b2/*.json). Dependency-free: a strict JSON Schema subset is enough for this schema
(type incl. null, enum, const, pattern, bounds, required, additionalProperties: false, items, $ref to $defs).
"""
import hashlib
import json
import re
import threading
import time
from pathlib import Path

SCHEMA_VERSION = 'b2.2'
SCHEMA = json.loads((Path(__file__).with_name('b2_skill_routes.schema.json')).read_text(encoding='utf-8'))
_TYPES = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'null': type(None)}


def _is(t, v):
    if t == 'integer':
        return isinstance(v, int) and not isinstance(v, bool)
    if t == 'number':
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def schema_errors(value, schema=None, path='$', root=None):
    """Return a list of 'path: problem' strings (empty when valid)."""
    root = root or SCHEMA
    schema = SCHEMA if schema is None else schema
    if '$ref' in schema:
        ref = schema['$ref']
        if not ref.startswith('#/$defs/'):
            return [f'{path}: unsupported $ref {ref}']
        return schema_errors(value, root['$defs'][ref[8:]], path, root)
    errs = []
    if 'const' in schema and value != schema['const']:
        return [f'{path}: must be {schema["const"]!r}']
    if 'enum' in schema and value not in schema['enum']:
        return [f'{path}: {value!r} not in enum']
    types = schema.get('type')
    if types is not None:
        types = [types] if isinstance(types, str) else types
        if not any(_is(t, value) for t in types):
            return [f'{path}: must be {"/".join(types)}']
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', 10_000):
            errs.append(f'{path}: length out of bounds')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errs.append(f'{path}: does not match {schema["pattern"]}')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get('minimum', value) or value > schema.get('maximum', value):
            errs.append(f'{path}: out of range')
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', 10_000):
            errs.append(f'{path}: item count out of bounds')
        for i, item in enumerate(value):
            if 'items' in schema:
                errs += schema_errors(item, schema['items'], f'{path}[{i}]', root)
    if isinstance(value, dict):
        props = schema.get('properties', {})
        for k in schema.get('required', ()):
            if k not in value:
                errs.append(f'{path}.{k}: required')
        if schema.get('additionalProperties') is False:
            errs += [f'{path}.{k}: unexpected field' for k in value if k not in props]
        for k, v in value.items():
            if k in props:
                errs += schema_errors(v, props[k], f'{path}.{k}', root)
    return errs


def semantic_errors(doc):
    """Cross-field rules a JSON Schema cannot express cleanly. Run after schema_errors() is empty."""
    errs = []
    routes = doc['routes']
    by_id = {r['route_id']: r for r in routes}
    if len(by_id) != len(routes):
        errs.append('route_id values must be unique')
    skill, policy, inv = doc['skill'], doc['policy'], doc['invocation']
    for r in routes:
        rid = r['route_id']
        if (r['state'] == 'UNAVAILABLE') != (r['reason'] is not None):
            errs.append(f'{rid}: UNAVAILABLE <=> exactly one reason')
        if r['reason_detail'] is not None and r['reason'] not in ('grant_insufficient', 'dependency_unready'):
            errs.append(f'{rid}: reason_detail only for grant_insufficient / dependency_unready')
        if r['reason'] == 'grant_insufficient':
            d = r['reason_detail'] or {}
            hi = d.get('hop_index')
            if d.get('missing_grant') is None or hi is None or hi >= len(r['hops']):
                errs.append(f'{rid}: grant_insufficient must name missing_grant and a valid hop_index')
        if r['freshness']['expires_at'] < r['freshness']['observed_at']:
            errs.append(f'{rid}: expires_at before observed_at')
        if r['last_receipt'] is not None and r['last_receipt']['evidence'] != r['evidence']:
            errs.append(f'{rid}: evidence must come from the last receipt')
        if skill['reversibility'] == 'EXACT' and r['state'] != 'UNAVAILABLE' and r['exactness'] is None:
            errs.append(f'{rid}: an EXACT skill route needs a measured range, before snapshot, independent read-back and exact restore')
        if r['exactness'] is not None and r['exactness']['range'][0] > r['exactness']['range'][1]:
            errs.append(f'{rid}: exactness range inverted')
        if skill['consent'] == 'none' and r['consent'] != 'none':
            errs.append(f'{rid}: consent must be none for a consent-free skill')
        if skill['consent'] == 'per_invocation' and r['consent'] == 'none':
            errs.append(f'{rid}: consent cannot be none for a per-invocation skill')
        if r['consent'] == 'armed' and not (inv['status'] in ('armed', 'executing') and inv['route_id'] == rid):
            errs.append(f'{rid}: consent armed only on the route of the armed/executing invocation')
    sel = doc['selected_route_id']
    if sel is not None:
        if sel not in by_id or by_id[sel]['state'] != 'READY':
            errs.append('selected_route_id must be a READY route')
        if doc['selection']['rule'] == 'none_eligible':
            errs.append('selection.rule none_eligible requires selected_route_id null')
    elif doc['selection']['rule'] != 'none_eligible':
        errs.append('no selected route requires selection.rule none_eligible')
    if policy['mode'] == 'PINNED':
        if policy['pinned_route_id'] is None:
            errs.append('PINNED needs pinned_route_id')
        elif sel not in (None, policy['pinned_route_id']):
            errs.append('PINNED: only the pinned route can be selected (no fallback)')
    elif policy['pinned_route_id'] is not None:
        errs.append('pinned_route_id only with PINNED')
    if policy['failover'] == 'idempotent_read_retry' and not (skill['idempotent'] and skill['reversibility'] == 'NONE'):
        errs.append('failover retry is only allowed for idempotent read-only skills')
    idle = inv['status'] == 'idle'
    fields = [inv[k] for k in ('invocation_id', 'route_id', 'lease_id', 'lease_expires_at', 'lease_expires_in_s')]
    if idle and any(f is not None for f in fields):
        errs.append('idle invocation carries no id, route or lease')
    if not idle:
        if any(f is None for f in fields):
            errs.append('armed/executing invocation needs id, route and lease')
        elif inv['route_id'] != sel:
            errs.append('armed/executing invocation must be on the selected route (a change voids it)')
    if sum(1 for r in routes if r['consent'] == 'armed') > 1:
        errs.append('at most one armed route')
    return errs


def validate_doc(doc):
    errs = schema_errors(doc)
    return errs or semantic_errors(doc)


# ---------- stable identifiers ----------
def _h(*parts, n=16):
    return hashlib.sha256('\x1f'.join(str(p) for p in parts).encode()).hexdigest()[:n]


def provider_id(device_key, transport, primitive_id, operation):
    return 'pv-' + _h('provider', device_key, transport, primitive_id, operation)


def route_id(skill_id, hops, operation):
    """Stable across polls for the same skill + hop chain + operation; changes when the path changes."""
    return 'rt-' + _h('route', skill_id, operation, *[f"{h['device_key']}|{h['transport']}|{h['primitive_id']}" for h in hops])


def binding_hash(actor, req, target_identity, authority_rev):
    """Everything an invocation lease and its consent are bound to. A route_id alone never survives a change of
    authority (grants), physical target identity, graph revision, lease or exact params."""
    canon = json.dumps({'actor': actor, 'skill': req['skill_id'], 'route': req['route_id'], 'lease': req['lease_id'],
                        'graph': req['graph_revision'], 'target': target_identity, 'authority_rev': authority_rev,
                        'params': req['params']}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode()).hexdigest()


class InvocationIdReused(Exception):
    """Same invocation_id with a different binding: rejected, never dispatched."""


class InvocationLedger:
    """Dedup by explicit logical invocation id, never by identical params within a time window.

    A retry reuses the invocation_id with the identical binding and gets the original result without a second
    dispatch. A new intent (e.g. a second volume-up press) carries a new id and is dispatched even if its params are
    identical. A reused id with a different binding raises InvocationIdReused. Entries are kept for `ttl_s`.
    """
    def __init__(self, ttl_s=600, max_entries=4096, clock=time.monotonic):
        self.ttl_s, self.max_entries, self.clock = ttl_s, max_entries, clock
        self._entries = {}          # (actor, invocation_id) -> (binding, result_or_event, created)
        self._lock = threading.Lock()

    def run(self, actor, invocation_id, binding, dispatch):
        key = (actor, invocation_id)
        with self._lock:
            now = self.clock()
            for k in [k for k, e in self._entries.items() if now - e[2] > self.ttl_s]:
                del self._entries[k]
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self.max_entries:
                    raise RuntimeError('invocation ledger full; retry later')   # refuse, never forget a live id
                done = threading.Event()
                self._entries[key] = (binding, done, now)
                owner = True
            else:
                if entry[0] != binding:
                    raise InvocationIdReused('invocation_id reused with a different skill, route, target, lease or params')
                owner = False
        if not owner:                    # retry of an in-flight or finished invocation: wait for the one dispatch
            ev = entry[1]
            if isinstance(ev, threading.Event):
                ev.wait()
                with self._lock:
                    return self._entries[key][1]
            return ev
        try:
            result = dispatch()
        except Exception as e:           # an exception is the outcome too: a retry must not re-dispatch
            result = {'state': 'FAILED', 'errors': [f'{type(e).__name__}: {str(e)[:160]}']}
        with self._lock:
            done = self._entries[key][1]
            self._entries[key] = (binding, result, self._entries[key][2])
        done.set()
        return result
