"""Meta model tiers with auditable AUTO routing.

Tiers: LOCAL-FAST (Llama 3.2 3B), LOCAL-QUALITY (Glimmer 30B),
CLOUD-HIGH (Spark 1.3), CLOUD-MAX (strongest eligible cloud config),
AUTO (auditable, privacy-gated). An explicit tier never reroutes:
missing availability raises instead of silently switching local<->paid.
Reasons never carry user text.
"""
from src.ai.local_meta import MODEL_ID as LLAMA_ID
from src.ai.glimmer import GLIMMER_ID
from src.ai.broker import MODEL_ID as SPARK_ID

TIERS = ('LOCAL-FAST', 'LOCAL-QUALITY', 'CLOUD-HIGH', 'CLOUD-MAX', 'AUTO')
TIER_MODELS = {'LOCAL-FAST': LLAMA_ID, 'LOCAL-QUALITY': GLIMMER_ID,
               'CLOUD-HIGH': SPARK_ID, 'CLOUD-MAX': SPARK_ID}
COMPLEX_TASKS = {'orchestration', 'synthesis', 'diagnosis', 'planning'}


class RoutingError(ValueError):
    pass


def _reasons(tier, task, availability, privacy):
    return ['task_class=%s' % ('complex' if task in COMPLEX_TASKS else 'simple'),
            'tier=%s' % tier, 'privacy=%s' % privacy,
            'local_fast=%s' % bool(availability.get('local_fast')),
            'local_quality=%s' % bool(availability.get('local_quality')),
            'cloud=%s' % bool(availability.get('cloud'))]


def route(tier, task, availability, privacy='local-only', user_text=''):
    if tier not in TIERS:
        raise RoutingError('Unknown tier: %r' % (tier,))
    if tier == 'AUTO':
        return _auto(task, availability, privacy)
    model = TIER_MODELS[tier]
    needs_cloud = tier.startswith('CLOUD')
    key = {'LOCAL-FAST': 'local_fast', 'LOCAL-QUALITY': 'local_quality'}.get(tier, 'cloud')
    if not availability.get(key):
        code = 'CLOUD_MODEL_UNAVAILABLE' if needs_cloud else 'MODEL_NOT_FOUND'
        raise RoutingError('%s: %s unavailable for explicit tier %s' % (code, model, tier))
    return {'tier': tier, 'model_id': model, 'needs_cloud_consent': needs_cloud,
            'reasons': _reasons(tier, task, availability, privacy)}


def _auto(task, availability, privacy):
    if task in COMPLEX_TASKS and privacy == 'allow-cloud' and availability.get('cloud'):
        tier = 'CLOUD-HIGH'
    elif task in COMPLEX_TASKS and availability.get('local_quality'):
        tier = 'LOCAL-QUALITY'
    elif availability.get('local_fast'):
        tier = 'LOCAL-FAST'
    elif availability.get('local_quality'):
        tier = 'LOCAL-QUALITY'
    elif availability.get('cloud') and privacy == 'allow-cloud':
        tier = 'CLOUD-HIGH'
    else:
        raise RoutingError('MODEL_NOT_FOUND: no tier available under privacy=%s' % privacy)
    needs_cloud = tier.startswith('CLOUD')
    return {'tier': tier, 'model_id': TIER_MODELS[tier], 'needs_cloud_consent': needs_cloud,
            'reasons': _reasons(tier, task, availability, privacy)}
