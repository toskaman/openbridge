"""Command Center P0: approve/execute service over resolved intents.

approve() previews without dispatching (B2: read-only skill_routes; direct
primitives: contract + target validation only). execute() requires fresh
consent, re-resolves targets (a revocation between approve and execute blocks),
and dispatches exactly once through the existing Router/Executor. P0 handles
one device per command; groups arrive later.
"""
import threading

from src.runtime import intent as I
from src.runtime import skills as S


class CommandError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _actionable(d):
    return bool(d.get('handles') or d.get('endpoints'))


def _via(d):
    return sorted((d.get('handles') or {})) + sorted((d.get('endpoints') or {}))


def _weak_ips(d):
    return sorted(v for k, v in (d.get('weak') or set()) if k == 'ip')


def _id_kinds(d):
    kinds = []
    for i in (d.get('identifiers') or set()):
        kinds.append(getattr(i, 'kind', None) or (i.get('kind') if isinstance(i, dict) else None))
    return sorted(k for k in kinds if k)


def resolve_targets_ex(targets, devices):
    """Resolve like resolve_targets but also explain duplicate views.

    Returns (keys, trace); trace records every candidate row, which rule
    selected the winner, and why (mega §5: duplicate device cards must
    have a traceable identity explanation)."""
    keys, trace = [], []
    for t in targets or []:
        ref = (t.get('ref') or '').strip().lower()
        if not ref:
            raise CommandError(400, 'empty target ref')
        hits = set()
        for k, d in devices.items():
            if ref == k.lower() or ref == (d.get('label') or '').strip().lower():
                hits.add(k)
            elif ref == (d.get('category') or '').strip().lower():
                hits.add(k)
        if not hits:
            raise CommandError(404, f'no authorized device matches {t.get("ref")!r}')
        rule = 'unique'
        seen = set(hits)
        if len(hits) > 1:
            action = {k for k in hits if _actionable(devices[k])}
            if len(action) == 1:
                hits = action  # duplicate protocol views; only one can dispatch
                rule = 'actionable-tiebreak'
            else:
                raise CommandError(409, f'ambiguous target {t.get("ref")!r}: {len(hits)} devices match')
        keys.append(next(iter(hits)))
        trace.append({'ref': t.get('ref'), 'rule': rule, 'winner': keys[-1],
                      'candidates': [{'key': k, 'label': devices[k].get('label'),
                                      'category': devices[k].get('category'),
                                      'actionable': _actionable(devices[k]),
                                      'via': _via(devices[k]),
                                      'weak_ips': _weak_ips(devices[k]),
                                      'id_kinds': _id_kinds(devices[k])} for k in sorted(seen)]})
    return keys, trace


def resolve_targets(targets, devices):
    keys, _ = resolve_targets_ex(targets, devices)
    return keys


def _devices(server):
    reg = getattr(server, 'fabric_registry', None)
    devs = getattr(reg, 'devices', None)
    if not isinstance(devs, dict):
        raise CommandError(503, 'device registry unavailable (run discovery first)')
    return devs


def _low(server):
    """OpenBridge's own command model, with the pinned general Llama 3.2 3B as fallback."""
    t = getattr(server, 'command_low', None)
    if t is None:
        from src.ai import own_model
        from src.ai.local_meta import MODEL_DIGEST
        from src.runtime.nl_router import OllamaIntentTransport, PreferredTransport, TIERS
        model, endpoint = TIERS['low']
        t = server.command_low = PreferredTransport(
            OllamaIntentTransport(own_model.MODEL_ID, own_model.ENDPOINT, digest=own_model.MODEL_DIGEST),
            OllamaIntentTransport(model, endpoint, digest=MODEL_DIGEST))
    return t


def _medium(server):
    t = getattr(server, 'command_medium', None)
    if t is None:
        from src.ai.glimmer import GLIMMER_DIGEST
        from src.runtime.nl_router import OllamaIntentTransport, TIERS
        model, endpoint = TIERS['medium']
        t = server.command_medium = OllamaIntentTransport(model, endpoint, digest=GLIMMER_DIGEST)
    return t


def _provider():
    """The owner's active connected AI (src/ai/custom_provider.py), or None."""
    from src.ai import custom_provider
    return custom_provider.active()


def _cloud(server):
    """Transport for the High tier = the owner's connected provider. Rebuilt when it changes.

    A transport injected on the server without an ``entry`` (tests, embedding) is used as-is
    and treated as remote (explicit consent required)."""
    t = getattr(server, 'command_cloud', None)
    if t is not None and getattr(t, 'entry', None) is None:
        return t
    entry = _provider()
    if entry is None:
        server.command_cloud = None
        return None
    t = getattr(server, 'command_cloud', None)
    if t is None or getattr(t, 'entry', None) != entry:
        from src.runtime.nl_router import CustomIntentTransport
        t = server.command_cloud = CustomIntentTransport(entry)
    return t


def _require_consent(consent, enabled, transport):
    """A connected provider that is not on this PC needs explicit consent per request."""
    if not enabled:
        raise CommandError(409, 'the connected AI is disabled by the kill switch')
    if transport is None:
        raise CommandError(409, 'no AI is connected: add one with `openbridge ai add` or in Settings')
    if getattr(transport, 'execution', 'remote') != 'local' and consent is not True:
        raise CommandError(409, 'the connected AI runs outside this PC: explicit consent is required')


def tiers(server):
    from src.ai import custom_provider
    from src.runtime.nl_router import TIERS
    out = {}
    for quality, get in (('low', _low), ('medium', _medium)):
        model, endpoint = TIERS[quality]
        try:
            t = get(server)
            ready = bool(t.ready())
            last = getattr(t, 'last_ok', None)
        except Exception:
            t, ready, last = None, False, None
        out[quality] = {'model': model, 'endpoint': endpoint, 'ready': ready,
                        'last_inference': 'ok' if last is True else ('failed' if last is False else 'unknown'),
                        'estimate_usd': 0.0}
        pref = getattr(t, 'preferred', None)
        if pref is not None:      # the Low tier: OpenBridge's own model first, the general model as fallback
            try:
                own_ready = bool(pref.ready())
            except Exception:
                own_ready = False
            out[quality].update(model=pref.model_id, endpoint=pref.endpoint, official=True, official_ready=own_ready,
                                fallback={'model': model, 'endpoint': endpoint})
    entry = _provider()
    out['high'] = {'model': entry['model'] if entry else None,
                   'endpoint': custom_provider.endpoint(entry) if entry else None,
                   'provider': entry['name'] if entry else None,
                   'kind': entry['kind'] if entry else None,
                   'execution': custom_provider.execution(entry) if entry else None,
                   'configured': entry is not None,
                   'enabled': getattr(server, 'command_cloud_enabled', True) is True,
                   # OpenBridge bills nothing; a hosted provider is paid by its owner directly.
                   'estimate_usd': None}
    return out


def parse_request(server, body):
    from src.runtime import nl_router as N
    if not isinstance(body, dict):
        raise CommandError(400, 'request body must be an object')
    text = body.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise CommandError(400, 'text must be 1..2000 characters')
    lang = body.get('lang', 'en')
    quality = body.get('quality', 'auto')
    consent = body.get('cloud_consent', False)
    if lang not in I.LANGS:
        raise CommandError(400, f'lang must be one of {I.LANGS}')
    if quality not in ('low', 'medium', 'high', 'auto'):
        raise CommandError(400, 'quality must be low|medium|high|auto')
    enabled = getattr(server, 'command_cloud_enabled', True) is True
    cloud = _cloud(server)
    if quality == 'high':
        _require_consent(consent, enabled, cloud)
    local_provider = cloud is not None and getattr(cloud, 'execution', 'remote') == 'local'
    allowed = enabled and cloud is not None and (consent is True or local_provider)

    def gate():
        try:
            _require_consent(consent, enabled, cloud)
        except CommandError as e:
            raise ValueError(str(e)) from None

    prior = body.get('prior')
    if prior is None:
        doc = N.parse(text.strip(), lang, quality, _low(server), cloud, _medium(server),
                      cloud_allowed=allowed,
                      before_cloud=gate if quality in ('high', 'auto') else None)
    else:
        # Follow-up turn: deterministic context resolution first, existing router
        # untouched on miss (parse_with_context delegates with identical args).
        if not isinstance(prior, dict) or I.validate_intent(prior) \
                or prior.get('status') not in ('resolved', 'approved', 'executed'):
            raise CommandError(400, 'prior must be a valid resolved intent')
        from src.runtime import nl_followup as F
        try:
            devices = _devices(server)
        except CommandError:
            devices = None
        doc = F.parse_with_context(text.strip(), lang, quality, _low(server), prior,
                                   cloud_transport=cloud,
                                   medium_transport=_medium(server),
                                   cloud_allowed=allowed,
                                   before_cloud=gate if quality in ('high', 'auto') else None,
                                   devices=devices)
    used = doc['provenance']['parser'] == 'cloud'
    out = {'intent': doc, 'cloud_used': used,
           'provider': (getattr(cloud, 'entry', None) or {}).get('name') if used else None,
           'estimate_usd': None if used else 0.0}
    if used and getattr(cloud, 'last_usage', None):
        out['usage'] = cloud.last_usage
    return out


def _fingerprint(skill_id, primitive_id, params, approved_targets, route_id):
    import hashlib, json
    canon = json.dumps({'skill': skill_id, 'primitive': primitive_id, 'params': params,
                        'targets': approved_targets, 'route': route_id},
                       sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode()).hexdigest()


def _b2_invocation_id(intent_id, fingerprint):
    """Deterministic journal identity for one approved b2 command, or None for a random id.

    Two processes executing the same (intent, approved binding) must arm the
    same invocation id, or the per-process random id lets both journal claims
    land and both dispatch (N-03). Falls back to None (random id at arm) when
    the intent carries no usable id; the in-process execution cache still
    dedups those. Lease ids stay random per arm: same-process leases never
    collide, and cross-process losers are refused by the journal claim."""
    if not isinstance(intent_id, str) or not intent_id or len(intent_id) > 96:
        return None
    import hashlib
    return 'inv-' + hashlib.sha256(('command-b2-v1\x1f%s\x1f%s' % (intent_id, fingerprint)).encode()).hexdigest()[:32]


def approve(server, doc):
    from src.runtime.api_v2 import router
    if I.validate_intent(doc) or doc.get('status') != 'resolved':
        raise CommandError(400, 'only a valid resolved intent can be approved')
    try:
        solved = S.resolve(doc['skill_id'], doc.get('params') or {})
    except S.SkillError as e:
        raise CommandError(400, str(e)) from None
    devs = _devices(server)
    target_trace = []
    if S.get(doc['skill_id'])['targets'] == ['fabric']:
        keys = []   # fabric-scoped reads address the registry itself, not a device
    else:
        keys, target_trace = resolve_targets_ex(doc.get('targets'), devs)
        if len(keys) != 1:
            raise CommandError(409, 'P0 executes one device per command')
    approved_targets = [{'key': k, 'label': devs[k].get('label'),
                         'category': devs[k].get('category')} for k in keys]
    prev = {'skill_id': doc['skill_id'], 'primitive_id': solved['primitive_id'],
            'params': solved['params'], 'device_keys': keys,
            'approved_targets': approved_targets,
            'target_trace': target_trace,
            'risk_level': solved['risk_level'],
            'verification': solved['verification'],
            'consent_required': True}
    if solved['primitive_id'].startswith('b2:'):
        from src.runtime.routing import RouteError, SKILLS
        skill = doc['skill_id']
        target = keys[0] if SKILLS[skill]['targeted'] else None
        try:
            routes = router(server).skill_routes(skill, target)
        except RouteError as e:
            raise CommandError(e.status, str(e)) from None
        prev['route'] = {'selected_route_id': routes.get('selected_route_id'),
                         'rule': (routes.get('selection') or {}).get('rule'),
                         'states': [(r['route_id'], r['state'], r['reason'])
                                    for r in routes.get('routes', [])]}
        if not routes.get('selected_route_id'):
            raise CommandError(409, 'no READY route for this skill')
    prev['fingerprint'] = _fingerprint(
        prev['skill_id'], prev['primitive_id'], prev['params'],
        prev['approved_targets'],
        (prev.get('route') or {}).get('selected_route_id'))
    return prev


MAX_EXECUTIONS = 512


def _exec_cache(server):
    if getattr(server, 'command_executions', None) is None:
        server.command_executions = {}
        server.command_exec_order = []
    if getattr(server, 'command_inflight', None) is None:
        server.command_inflight = {}
        server.command_exec_lock = threading.Lock()
    return server.command_executions, server.command_exec_order


def _store(server, key, rc):
    cache, order = server.command_executions, server.command_exec_order
    cache[key] = rc
    order.append(key)
    while len(order) > MAX_EXECUTIONS:
        cache.pop(order.pop(0), None)


def execute(server, doc, consent=False, preview=None):
    if consent is not True:
        raise CommandError(400, 'fresh consent is required to execute')
    if not isinstance(preview, dict) or preview.get('skill_id') != (doc or {}).get('skill_id') \
            or not isinstance(preview.get('fingerprint'), str):
        raise CommandError(400, 'execute needs the preview returned by approve for this intent')
    key = ((doc or {}).get('intent_id'), preview['fingerprint'])
    cache, _ = _exec_cache(server)
    lock, inflight = server.command_exec_lock, server.command_inflight
    # Atomic per-intent claim (V4-S1): one owner dispatches; concurrent retries of the
    # same (intent, approved binding) wait and get the same outcome. No global lock
    # is held across the dispatch, so unrelated intents run independently.
    while True:
        with lock:
            if key in cache:
                return cache[key]   # idempotent retry: same receipt, no second dispatch
            ev = inflight.get(key)
            if ev is None:
                ev = inflight[key] = threading.Event()
                break
        ev.wait(timeout=660)
        with lock:
            if key in cache:
                return cache[key]
            if inflight.get(key) is ev:
                raise CommandError(409, 'the same intent is still executing; retry later')
        # the owner failed before dispatching: loop and try to claim it ourselves
    dispatched = [False]
    try:
        rc = _execute_claimed(server, doc, preview, dispatched)
        with lock:
            _store(server, key, rc)
        return rc
    except CommandError:
        if dispatched[0]:
            with lock:
                _store(server, key, {'state': 'INCONCLUSIVE', 'transaction_id': None,
                                     'error': 'dispatch outcome unknown; not retried'})
        raise
    except Exception:
        if dispatched[0]:   # outcome unknown: never re-dispatch on retry
            with lock:
                _store(server, key, {'state': 'INCONCLUSIVE', 'transaction_id': None,
                                     'error': 'dispatch outcome unknown; not retried'})
        raise
    finally:
        with lock:
            inflight.pop(key, None)
        ev.set()


def _execute_claimed(server, doc, preview, dispatched):
    from src.runtime.api_v2 import router, executor
    prev = approve(server, doc)   # re-resolves everything; revocations block here
    if prev['fingerprint'] != preview['fingerprint']:
        raise CommandError(409, 'target, params or route changed since approval; review again')
    if prev['primitive_id'] == 'fabric_status':
        from src.runtime.fabric_status import summarize
        relays = getattr(getattr(server, 'relays', None), 'relays', None) or {}
        return {'state': 'READ', 'transaction_id': None,
                'summary': summarize(_devices(server), relays)}
    if prev['primitive_id'].startswith('b2:'):
        from src.runtime.routing import RouteError, SKILLS
        r = router(server)
        skill = doc['skill_id']
        target = prev['device_keys'][0] if SKILLS[skill]['targeted'] else None
        arm_id = _b2_invocation_id((doc or {}).get('intent_id'), preview['fingerprint'])
        try:
            lease = r.arm({'skill_id': skill, 'target': target,
                           'route_id': prev['route']['selected_route_id'],
                           'params': prev['params'], 'consent': True},
                          invocation_id=arm_id)
            body = {k: lease[k] for k in ('invocation_id', 'route_id', 'lease_id', 'graph_revision')}
            body.update(skill_id=skill, params=prev['params'], consent=True)
            if target is not None:
                body['target'] = target
            dispatched[0] = True
            return r.invoke(body)
        except RouteError as e:
            dispatched[0] = False   # RouteError is a refusal before dispatch
            raise CommandError(e.status, str(e)) from None
    iid = doc.get('intent_id')
    store = None
    if isinstance(iid, str) and iid and len(iid) <= 96:
        from src.runtime.state_store import StateStore, StateError
        import time as _t
        store = StateStore.for_server(server)
        if store is not None:
            try:
                claimed, row = store.claim_invocation('intent', iid, _t.time())
            except StateError as e:
                raise CommandError(503, '%s: %s' % (e.code, e)) from None
            if not claimed:
                if row['state'] == 'DONE':
                    raise CommandError(409, 'DUPLICATE_REQUEST: this intent was already handled')
                raise CommandError(409, 'UNCERTAIN_OUTCOME: this intent is already running elsewhere or was interrupted; start a fresh intent')
    dispatched[0] = True
    try:
        rc = executor(server).execute(prev['primitive_id'], prev['device_keys'][0],
                                      prev['params'], True)
    except Exception:
        if store is not None:
            try:
                store.finish_invocation('intent', iid, preview['fingerprint'], _t.time())
            except StateError:
                pass   # leftover EXECUTING fails closed: never re-dispatch an uncertain intent
        raise
    if store is not None:
        try:
            store.finish_invocation('intent', iid, preview['fingerprint'], _t.time())
        except StateError:
            pass
    return rc
