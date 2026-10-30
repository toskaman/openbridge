"""Readiness aggregation: fixed status vocabulary, per-feature truth.

Global is READY only when every probed feature is READY. Unknown probe
values become INVALID, never READY.
"""
STATUSES = ('READY', 'MISSING', 'INVALID', 'INCOMPATIBLE', 'BLOCKED', 'PERMISSION_REQUIRED',
            'AUTH_REQUIRED', 'MODEL_NOT_FOUND', 'INSUFFICIENT_RESOURCES', 'API_UNAVAILABLE',
            'NOT_TESTED')


def collect(probes):
    features = {name: (value if value in STATUSES else 'INVALID')
                for name, value in sorted(probes.items())}
    overall = 'READY' if features and all(v == 'READY' for v in features.values()) else 'BLOCKED'
    if not features:
        overall = 'NOT_TESTED'
    return {'global': overall, 'features': features}
