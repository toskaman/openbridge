"""S3 plan objects (Forge side, offline): validated DAGs for Claude's executor.

A plan is pure data: steps with primitive, target, consent flag, verify hook
and dependencies. validate_plan enforces: known targets, capability support,
consent on every non-read step, a verify hook per step, acyclic dependencies.
summarize() turns executor receipts into honest per-step + overall states
(ok/partial/failed). Execution itself stays Claude-side (contract C2).
"""
VERIFY_KINDS = {'artifact', 'receipt', 'state'}


class PlanError(ValueError):
    pass


def _step_shape(s):
    if not isinstance(s, dict):
        raise PlanError('STEP_MUST_BE_OBJECT')
    for k in ('step_id', 'primitive', 'target', 'needs_consent', 'depends_on', 'verify'):
        if k not in s:
            raise PlanError('STEP_MISSING_%s' % k.upper())
    if not isinstance(s['step_id'], str) or not s['step_id']:
        raise PlanError('STEP_ID_INVALID')
    if not isinstance(s['depends_on'], list) or any(not isinstance(d, str) for d in s['depends_on']):
        raise PlanError('DEPENDS_INVALID')
    v = s['verify']
    if not isinstance(v, dict) or v.get('kind') not in VERIFY_KINDS or 'expect' not in v:
        raise PlanError('VERIFY_REQUIRED')


def validate_plan(plan, capabilities, read_primitives):
    """capabilities: {target: {primitive,...}} from VERIFIED descriptors.
    read_primitives: primitives that never change state (no consent needed)."""
    if not isinstance(plan, dict) or not isinstance(plan.get('steps'), list) or not plan['steps']:
        raise PlanError('PLAN_NEEDS_STEPS')
    ids = [s.get('step_id') for s in plan['steps']]
    if len(set(ids)) != len(ids):
        raise PlanError('DUP_STEP_ID')
    for s in plan['steps']:
        _step_shape(s)
        if s['target'] not in (capabilities or {}):
            raise PlanError('UNKNOWN_TARGET: %r' % (s['target'],))
        if s['primitive'] not in capabilities[s['target']]:
            raise PlanError('CAPABILITY_GAP: %s on %s' % (s['primitive'], s['target']))
        if s['primitive'] not in (read_primitives or ()) and s['needs_consent'] is not True:
            raise PlanError('CONSENT_REQUIRED: %s' % (s['step_id'],))
        for d in s['depends_on']:
            if d not in ids:
                raise PlanError('UNKNOWN_DEP: %r' % (d,))
            if d == s['step_id']:
                raise PlanError('CYCLE: self')
    order, done, visiting = [], set(), set()
    by_id = {s['step_id']: s for s in plan['steps']}

    def visit(sid):
        if sid in done:
            return
        if sid in visiting:
            raise PlanError('CYCLE')
        visiting.add(sid)
        for d in by_id[sid]['depends_on']:
            visit(d)
        visiting.discard(sid)
        done.add(sid)
        order.append(by_id[sid])
    for sid in ids:
        visit(sid)
    return {'plan_id': plan.get('plan_id'), 'goal': plan.get('goal'), 'order': order}


def summarize(plan, receipts):
    """Honest partial states from executor receipts. Never invents outcomes."""
    states = {}
    for s in plan.get('steps', []):
        r = (receipts or {}).get(s['step_id'])
        if not isinstance(r, dict) or 'status' not in r:
            states[s['step_id']] = 'pending'
        elif r['status'] == 'ok':
            states[s['step_id']] = 'ok'
        else:
            states[s['step_id']] = 'failed'
    vals = set(states.values())
    overall = 'ok' if vals == {'ok'} else ('pending' if vals <= {'ok', 'pending'} and 'pending' in vals
                                           else ('failed' if vals == {'failed'} else 'partial'))
    failed = [k for k, v in states.items() if v == 'failed']
    return {'states': states, 'overall': overall, 'failed': failed}
