"""V4 CrossDevicePlanner: frozen recipients/exclusions, scoped grants with expiry."""
from src.forge import v4_schemas as S


class FlowError(ValueError):
    pass


def grant(expiry, now):
    if not isinstance(expiry, (int, float)) or not expiry > now:
        raise FlowError('STALE_GRANT')
    return {'grant_id': 'g-' + S.digest('grant|%s|%s' % (expiry, now))[:12],
            'expiry': float(expiry)}


def compose(steps, recipients, exclusions, relays):
    rec, exc, rel = set(recipients), set(exclusions), set(relays)
    if rec & exc:
        raise FlowError('RECIPIENT_EXCLUDED')
    if rel & exc:
        raise FlowError('EXCLUDED_RELAY')
    for s in steps:
        if set(s) != {'primitive_id', 'target', 'input'} or not isinstance(s['input'], dict):
            raise FlowError('STEP_SHAPE')
    plan = {'schema_version': S.SCHEMA_VERSION, 'plan_id': 'p-pending',
            'steps': list(steps), 'recipients_frozen': sorted(rec),
            'exclusions_frozen': sorted(exc), 'relays_frozen': sorted(rel),
            'partial_policy': 'explicit-per-target-ack'}
    plan['plan_id'] = 'p-' + S.digest({k: v for k, v in plan.items() if k != 'plan_id'})[:16]
    return plan
