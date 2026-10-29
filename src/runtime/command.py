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


def resolve_targets(targets, devices):
    keys = []
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
        if len(hits) > 1:
            raise CommandError(409, f'ambiguous target {t.get("ref")!r}: {len(hits)} devices match')
        keys.append(next(iter(hits)))
    return keys


def _devices(server):
    reg = getattr(server, 'fabric_registry', None)
    devs = getattr(reg, 'devices', None)
    if not isinstance(devs, dict):
        raise CommandError(503, 'device registry unavailable (run discovery first)')
    return devs


def _low(server):
    t = getattr(server, 'command_low', None)
    if t is None:
        from src.ai.local_meta import MODEL_DIGEST
        from src.runtime.nl_router import OllamaIntentTransport, TIERS
        model, endpoint = TIERS['low']
        t = server.command_low = OllamaIntentTransport(model, endpoint, digest=MODEL_DIGEST)
    return t


def _medium(server):
    t = getattr(server, 'command_medium', None)
    if t is None:
        from src.ai.glimmer import GLIMMER_DIGEST
        from src.runtime.nl_router import OllamaIntentTransport, TIERS
        model, endpoint = TIERS['medium']
        t = server.command_medium = OllamaIntentTransport(model, endpoint, digest=GLIMMER_DIGEST)
    return t


def _broker(server):
    b = getattr(server, 'model_broker', None)
    if b is None or not callable(getattr(b, 'transport', None)):
        return None
    if not hasattr(b, 'permit') or not hasattr(b, 'budget_path'):
        return None
    return b


def _cloud(server):
    t = getattr(server, 'command_cloud', None)
    if t is None:
        b = _broker(server)
        if b is None:
            return None
        from src.runtime.nl_router import CloudIntentTransport, TIERS
        model, endpoint = TIERS['high']
        t = server.command_cloud = CloudIntentTransport(model, endpoint, b.transport)
    return t


def tiers(server):
    from src.runtime.nl_router import TIERS
    from src.runtime.cost_guard import estimate_usd
    out = {}
    for quality, get in (('low', _low), ('medium', _medium)):
        model, endpoint = TIERS[quality]
        try:
            t = get(server)
            ready = bool(t.ready())
            last = getattr(t, 'last_ok', None)
        except Exception:
            ready, last = False, None
        out[quality] = {'model': model, 'endpoint': endpoint, 'ready': ready,
                        'last_inference': 'ok' if last is True else ('failed' if last is False else 'unknown'),
                        'estimate_usd': estimate_usd(quality)}
    model, endpoint = TIERS['high']
    out['high'] = {'model': model, 'endpoint': endpoint,
                   'configured': _broker(server) is not None,
                   'enabled': getattr(server, 'command_cloud_enabled', True) is True,
                   'estimate_usd': estimate_usd('high')}
    return out


def parse_request(server, body):
    from src.runtime import cost_guard as C
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
    if quality == 'high':
        try:
            C.require_cloud(consent, enabled)
        except C.CostBlocked as e:
            raise CommandError(409, str(e)) from None
        if _broker(server) is None:
            raise CommandError(409, 'cloud is not configured on this server')
    cloud = _cloud(server)

    def gate():
        C.require_cloud(consent, enabled)
        b = _broker(server)
        if b is None:
            raise C.CostBlocked('cloud is not configured on this server')
        from src.ai.broker import ModelBlocked
        try:
            b._reserve()   # shared guard: freshness, finite balances, allowance, atomic insert
        except ModelBlocked as e:
            raise C.CostBlocked(str(e)) from None

    doc = N.parse(text.strip(), lang, quality, _low(server), cloud, _medium(server),
                  cloud_allowed=consent is True and enabled and cloud is not None,
                  before_cloud=gate if quality in ('high', 'auto') else None)
    out = {'intent': doc, 'cloud_used': doc['provenance']['parser'] == 'cloud',
           'estimate_usd': C.estimate_usd(quality) if quality != 'auto'
           else (C.estimate_usd('high') if doc['provenance']['parser'] == 'cloud' else 0.0)}
    if out['cloud_used'] and getattr(cloud, 'last_usage', None):
        out['usage'] = cloud.last_usage
    return out


def _fingerprint(skill_id, primitive_id, params, approved_targets, route_id):
    import hashlib, json
    canon = json.dumps({'skill': skill_id, 'primitive': primitive_id, 'params': params,
                        'targets': approved_targets, 'route': route_id},
                       sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canon.encode()).hexdigest()


def approve(server, doc):
    from src.runtime.api_v2 import router
    if I.validate_intent(doc) or doc.get('status') != 'resolved':
        raise CommandError(400, 'only a valid resolved intent can be approved')
    try:
        solved = S.resolve(doc['skill_id'], doc.get('params') or {})
    except S.SkillError as e:
        raise CommandError(400, str(e)) from None
    devs = _devices(server)
    if S.get(doc['skill_id'])['targets'] == ['fabric']:
        keys = []   # fabric-scoped reads address the registry itself, not a device
    else:
        keys = resolve_targets(doc.get('targets'), devs)
        if len(keys) != 1:
            raise CommandError(409, 'P0 executes one device per command')
    approved_targets = [{'key': k, 'label': devs[k].get('label'),
                         'category': devs[k].get('category')} for k in keys]
    prev = {'skill_id': doc['skill_id'], 'primitive_id': solved['primitive_id'],
            'params': solved['params'], 'device_keys': keys,
            'approved_targets': approved_targets,
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
        try:
            lease = r.arm({'skill_id': skill, 'target': target,
                           'route_id': prev['route']['selected_route_id'],
                           'params': prev['params'], 'consent': True})
            body = {k: lease[k] for k in ('invocation_id', 'route_id', 'lease_id', 'graph_revision')}
            body.update(skill_id=skill, params=prev['params'], consent=True)
            if target is not None:
                body['target'] = target
            dispatched[0] = True
            return r.invoke(body)
        except RouteError as e:
            dispatched[0] = False   # RouteError is a refusal before dispatch
            raise CommandError(e.status, str(e)) from None
    dispatched[0] = True
    return executor(server).execute(prev['primitive_id'], prev['device_keys'][0],
                                    prev['params'], True)
