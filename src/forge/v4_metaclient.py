"""V4 MetaClient: tiered Meta-only generation with honest unavailability. No fallback impersonation."""
import time


class TransportFailed(Exception):
    pass


class MetaClient:
    def __init__(self, transports):
        self.transports = dict(transports)

    def generate(self, tier, prompt, budget):
        fn = self.transports.get(tier)
        if fn is None:
            return (False, {'status': 'MODEL_UNAVAILABLE', 'failure_class': 'UNKNOWN_TIER'})
        start = time.monotonic()
        try:
            ok, body = fn(prompt, budget)
        except TransportFailed as e:
            return (False, {'status': 'MODEL_UNAVAILABLE', 'failure_class': str(e)[:64]})
        except Exception as e:  # noqa: BLE001 - transport contract: any error is unavailability
            return (False, {'status': 'MODEL_UNAVAILABLE', 'failure_class': type(e).__name__})
        if not ok:
            return (False, body)
        body = dict(body)
        body['latency_ms'] = round((time.monotonic() - start) * 1000)
        return (True, body)


def ollama_transport(endpoint, model, json_mode=True, urlopen=None):
    """Bind an Ollama /api/chat endpoint as a MetaClient transport (local Meta only).

    The expected model id is pinned: a response echoing a different model is a
    transport failure, never silently accepted. Weight-digest pinning stays at
    broker provisioning time (LocalMetaBroker); pass only broker-verified
    endpoints here.
    """
    import json as _json
    import urllib.request as _url
    if not model or not isinstance(model, str):
        raise ValueError('expected model id is required')
    _open = urlopen or _url.urlopen

    def call(prompt, budget):
        payload = {'model': model, 'stream': False,
                   'messages': [{'role': 'user', 'content': prompt}]}
        if json_mode:
            payload['format'] = 'json'
        req = _url.Request(endpoint.rstrip('/') + '/api/chat', data=_json.dumps(payload).encode(),
                           headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with _open(req, timeout=int(budget.get('max_s', 120))) as resp:
                data = _json.loads(resp.read())
        except TransportFailed:
            raise
        except Exception as e:
            raise TransportFailed(type(e).__name__) from None
        if data.get('model') != model:
            raise TransportFailed('MODEL_IDENTITY_MISMATCH')
        try:
            text = data['message']['content']
        except (KeyError, TypeError):
            raise TransportFailed('BAD_ENVELOPE') from None
        return (True, {'text': text, 'usage': {'prompt_eval': data.get('prompt_eval_count'),
                                              'eval': data.get('eval_count')}})
    return call


class RulesPlanner:
    """Deterministic ablation baseline: same task, no model. Never scored as Meta-created."""

    def __init__(self, primitive_ids):
        self.primitives = tuple(primitive_ids)

    def propose(self, bundle, intent_text):
        return {'status': 'ABSTAIN_UNSUPPORTED',
                'reason': 'rules planner: no prebuilt template for %r' % (intent_text[:80],)}
