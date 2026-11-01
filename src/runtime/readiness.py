"""Readiness aggregation: fixed status vocabulary, per-feature truth.

Global is READY only when every probed feature is READY. Unknown probe
values become INVALID, never READY.

REQUIRED vs OPTIONAL: the offline judge demo only needs the core, a
supported OS, and a writable evidence store with free space. Local
models, the cloud key and adb-backed devices are OPTIONAL extras whose
absence must not block the demo verdict (judge-C W2).
"""
STATUSES = ('READY', 'MISSING', 'INVALID', 'INCOMPATIBLE', 'BLOCKED', 'PERMISSION_REQUIRED',
            'AUTH_REQUIRED', 'MODEL_NOT_FOUND', 'INSUFFICIENT_RESOURCES', 'API_UNAVAILABLE',
            'NOT_TESTED')

REQUIRED = ('core', 'os', 'evidence', 'storage')
OPTIONAL = ('local_fast', 'local_quality', 'cloud', 'devices')

LABELS = {'core': 'app core', 'os': 'operating system', 'evidence': 'evidence folder',
          'storage': 'disk space', 'local_fast': 'local fast model (Llama 3B)',
          'local_quality': 'local quality model (Glimmer 30B)', 'cloud': 'Meta cloud key',
          'devices': 'Android tools (adb)'}
WORDS = {'READY': 'ready', 'MISSING': 'missing', 'INVALID': 'invalid',
         'INCOMPATIBLE': 'incompatible', 'BLOCKED': 'blocked',
         'PERMISSION_REQUIRED': 'needs permission', 'AUTH_REQUIRED': 'needs sign-in',
         'MODEL_NOT_FOUND': 'model not installed',
         'INSUFFICIENT_RESOURCES': 'not enough resources',
         'API_UNAVAILABLE': 'service unreachable', 'NOT_TESTED': 'not tested'}


def plain_line(name, status):
    """One plain-language readiness line, e.g. 'Meta cloud key: missing'."""
    label = LABELS.get(name, str(name).replace('_', ' '))
    return '%s: %s' % (label, WORDS.get(status, str(status).lower().replace('_', ' ')))


def collect(probes, required=None):
    features = {name: (value if value in STATUSES else 'INVALID')
                for name, value in sorted(probes.items())}
    overall = 'READY' if features and all(v == 'READY' for v in features.values()) else 'BLOCKED'
    if not features:
        overall = 'NOT_TESTED'
    if required is None:
        return {'global': overall, 'features': features}
    need = {name: features.get(name, 'NOT_TESTED') for name in required}
    verdict = 'READY' if need and all(v == 'READY' for v in need.values()) else 'BLOCKED'
    if not features:
        verdict = 'NOT_TESTED'
    return {'global': verdict, 'overall': overall, 'features': features, 'required': need,
            'optional': {name: value for name, value in features.items()
                         if name not in set(required)}}
