"""Model tiers with auditable AUTO routing.

Tiers: LOCAL-FAST (Llama 3.2 3B), LOCAL-QUALITY (Muse Glimmer 30B), CUSTOM (a model or API the
owner connected by hand, see src/ai/custom_provider.py), AUTO (auditable, privacy-gated).
No paid model is built in. An explicit tier never reroutes: missing availability raises instead
of silently switching. A CUSTOM provider that is not on this PC needs explicit consent
(``needs_cloud_consent``: the request would leave the PC). Reasons never carry user text.
"""
from src.ai.local_meta import MODEL_ID as LLAMA_ID
from src.ai.glimmer import GLIMMER_ID

TIERS = ('LOCAL-FAST', 'LOCAL-QUALITY', 'CUSTOM', 'AUTO')
TIER_MODELS = {'LOCAL-FAST': LLAMA_ID, 'LOCAL-QUALITY': GLIMMER_ID}
COMPLEX_TASKS = {'orchestration', 'synthesis', 'diagnosis', 'planning'}


class RoutingError(ValueError):
    pass


def _reasons(tier, task, availability, privacy):
    return ['task_class=%s' % ('complex' if task in COMPLEX_TASKS else 'simple'),
            'tier=%s' % tier, 'privacy=%s' % privacy,
            'local_fast=%s' % bool(availability.get('local_fast')),
            'local_quality=%s' % bool(availability.get('local_quality')),
            'custom=%s' % bool(availability.get('custom'))]


def _decision(tier, task, availability, privacy):
    if tier == 'CUSTOM':
        model = availability.get('custom_model')
        remote = availability.get('custom_execution', 'remote') != 'local'
    else:
        model, remote = TIER_MODELS[tier], False
    return {'tier': tier, 'model_id': model, 'needs_cloud_consent': remote,
            'reasons': _reasons(tier, task, availability, privacy)}


def route(tier, task, availability, privacy='local-only', user_text=''):
    if tier not in TIERS:
        raise RoutingError('Unknown tier: %r' % (tier,))
    if tier == 'AUTO':
        return _auto(task, availability, privacy)
    key = {'LOCAL-FAST': 'local_fast', 'LOCAL-QUALITY': 'local_quality', 'CUSTOM': 'custom'}[tier]
    if not availability.get(key):
        code = 'CUSTOM_PROVIDER_MISSING' if tier == 'CUSTOM' else 'MODEL_NOT_FOUND'
        raise RoutingError('%s: no model available for explicit tier %s' % (code, tier))
    return _decision(tier, task, availability, privacy)


def _custom_allowed(availability, privacy):
    if not availability.get('custom'):
        return False
    return availability.get('custom_execution') == 'local' or privacy == 'allow-cloud'


def _auto(task, availability, privacy):
    if task in COMPLEX_TASKS and availability.get('local_quality'):
        tier = 'LOCAL-QUALITY'
    elif task in COMPLEX_TASKS and _custom_allowed(availability, privacy):
        tier = 'CUSTOM'
    elif availability.get('local_fast'):
        tier = 'LOCAL-FAST'
    elif availability.get('local_quality'):
        tier = 'LOCAL-QUALITY'
    elif _custom_allowed(availability, privacy):
        tier = 'CUSTOM'
    else:
        raise RoutingError('MODEL_NOT_FOUND: no tier available under privacy=%s' % privacy)
    return _decision(tier, task, availability, privacy)
