"""Campaign Two section 4.3: user-facing cross-device workflow composer.

Meta proposes a bounded multi-device workflow from actual capabilities; the
deterministic composer allows or refuses each step; the existing DAG engine
(src/runtime/workflows.py) executes whatever the composer admits. The model
is never trusted: unknown primitives, unverified devices, unpermitted routes
and invalid params become per-step refusals, never a guessed command.

Each composed step carries the seven section 4.3 fields: a typed primitive,
a verified device, a permitted route, the required authorization, a declared
expected effect, an independent verification method and a failure strategy.

Physical acts are never atomically rolled back: a finished step reports what
the device confirmed, and only state with a verified read-back is ever marked
RESTORED. Every composer surface repeats that disclaimer verbatim.
"""
import hashlib
import json
import time

COMPOSER_VERSION = 1
MAX_COMPOSED_STEPS = 8
MAX_REPLY_CHARS = 16384
COMPOSED_TTL_S = 300

# User-facing per-step outcomes (section 4.3). The DAG engine keeps its own
# internal states; summarize() maps them onto exactly these six.
OUTCOMES = ('EXECUTED_VERIFIED', 'EXECUTED_UNVERIFIED', 'REFUSED', 'FAILED',
            'UNKNOWN', 'RESTORED')
OUTCOME_LABELS = {
    'EXECUTED_VERIFIED': 'Executed and verified',
    'EXECUTED_UNVERIFIED': 'Executed but not independently verified',
    'REFUSED': 'Refused',
    'FAILED': 'Failed',
    'UNKNOWN': 'Unknown',
    'RESTORED': 'Reversible state restored',
}
FAILURE_STRATEGIES = ('fail', 'continue')

NO_ATOMIC_ROLLBACK = (
    'Physical acts are never atomically rolled back: each step reports what '
    'its device confirmed, and only state with a verified read-back is ever '
    'marked restored.')

# Skill audience by device category, mirroring Router._providers. This only
# shapes the proposal prompt; compose() re-checks every step against the live
# route truth, so a stale map can only refuse, never admit.
ANDROID = ('phone', 'tv', 'android', 'watch')
SKILL_AUDIENCE = {
    'ble_scan_room': 'fabric',
    'capture_montage': 'fabric',
    'retro_command': 'fabric',
    'device_facts': 'any linked device',
    'tv_volume_set': 'android',
    'tv_volume_step': 'android',
    'tv_sleep': 'android',
    'tv_wake': 'android',
    'screen_capture': 'android',
    'file_pull': 'android',
    'capability_probe': 'android',
    'companion_foreground': 'android',
    'capture_send': 'android',
    'file_push': 'android',
    'app_launch': 'android',
    'vacuum_command': 'vacuum',
    'pc_run': 'computer',
}

# Ollama structured-output constraint (shape only; values stay model-authored
# and are re-validated deterministically by proposal_from_reply + compose).
PROPOSAL_JSON_SCHEMA = {'type': 'object',
    'required': ['steps'],
    'properties': {'steps': {'type': 'array', 'minItems': 1,
        'maxItems': MAX_COMPOSED_STEPS,
        'items': {'type': 'object', 'required': ['skill_id', 'target', 'params'],
            'properties': {'skill_id': {'type': 'string'},
                           'target': {'type': 'string'},
                           'params': {'type': 'object'},
                           'on_fail': {'type': 'string',
                                       'enum': list(FAILURE_STRATEGIES)},
                           'needs': {'type': 'array',
                                     'items': {'type': 'string'}}}}}}}
_PROPOSAL_KEYS = {'skill_id', 'target', 'params', 'on_fail', 'needs'}


class ComposerError(ValueError):
    pass


def candidates_for(device):
    """Skill ids plausibly usable on one device (prompt grounding only).

    A device with no live link has no candidates: it cannot be verified, so
    the model is not invited to propose it. compose() still re-checks.
    """
    if not isinstance(device, dict) or not device.get('handles'):
        return []
    from src.runtime.routing import SKILLS
    cat = (device.get('category') or '').strip().lower()
    out = []
    for sid in sorted(SKILLS):
        aud = SKILL_AUDIENCE.get(sid, 'any linked device')
        if aud == 'fabric':
            continue
        if aud == 'any linked device' or aud == 'computer' and cat == 'computer' \
                or aud == 'vacuum' and cat == 'vacuum' \
                or aud == 'android' and cat in ANDROID + ('tablet',):
            out.append(sid)
    return out


def build_prompt(text, devices):
    """Strict capability-grounded composition prompt: labels only, never keys."""
    from src.runtime.nl_plan import param_hint
    from src.runtime.routing import SKILLS
    dev_lines = []
    for d in devices:
        cands = candidates_for(d)
        dev_lines.append('- %s (%s)%s' % (
            d.get('label'), d.get('category'),
            (': ' + ', '.join(cands)) if cands else ': no live link, do not use'))
    untargeted = sorted(s for s, aud in SKILL_AUDIENCE.items() if aud == 'fabric')
    skill_lines = ['- %s %s reversibility=%s consent=%s audience=%s: %s'
                   % (sid, param_hint(s.get('input')), s.get('reversibility'),
                      s.get('consent'), SKILL_AUDIENCE.get(sid, '?'),
                      s.get('plain'))
                   for sid, s in sorted(SKILLS.items())]
    return ('You compose device workflows. Reply with ONE JSON object and nothing else: '
            '{"steps": [{"skill_id": "<id>", "target": "<device label>", "params": {}}]}. '
            'Rules: 1..%d steps; skill_id must be listed below and plausible for the target; copy the '
            'target label EXACTLY character-for-character from the Devices list (never abbreviate; '
            '"fabric" only for untargeted skills); params must match the hint exactly, no extra keys. '
            'Optional per step: "on_fail" is "fail" (dependents stop, the default) or "continue" (run '
            'independent steps anyway); "needs" lists earlier step ids (["step1"]) for ordering, omit '
            'for a simple sequence. %s Only propose steps whose effect the owner accepts. '
            'Example: {"steps": [{"skill_id": "tv_volume_step", "target": "android tv", '
            '"params": {"direction": "down"}}]}. Request: %s\nDevices:\n%s\nUntargeted skills '
            '(target "fabric"): %s\nSkills:\n%s'
            % (MAX_COMPOSED_STEPS, NO_ATOMIC_ROLLBACK, text.strip()[:500],
               '\n'.join(dev_lines), ', '.join(untargeted), '\n'.join(skill_lines)))


def proposal_from_doc(doc):
    """Strictly validate a parsed proposal object (shape and bounds only).

    Skill, target and param validity are per-step compose() verdicts, not
    parse errors: the composer must refuse bad steps openly, not crash.
    """
    steps = doc.get('steps') if isinstance(doc, dict) else None
    if not isinstance(steps, list) or not steps or len(steps) > MAX_COMPOSED_STEPS:
        raise ComposerError('proposal needs steps[1..%d]' % MAX_COMPOSED_STEPS)
    ids = ['step%d' % i for i in range(1, len(steps) + 1)]
    out = []
    for i, (sid, s) in enumerate(zip(ids, steps), 1):
        if not isinstance(s, dict) or set(s) - _PROPOSAL_KEYS:
            raise ComposerError('step %d: only %s allowed' % (i, sorted(_PROPOSAL_KEYS)))
        if not isinstance(s.get('skill_id'), str) or not isinstance(s.get('target'), str):
            raise ComposerError('step %d: skill_id and target must be strings' % i)
        if not isinstance(s.get('params'), dict):
            raise ComposerError('step %d: params must be an object' % i)
        on_fail = s.get('on_fail', 'fail')
        if on_fail not in FAILURE_STRATEGIES:
            raise ComposerError('step %d: on_fail must be fail or continue' % i)
        needs = s.get('needs') or []
        if not isinstance(needs, list) or any(n not in ids[:i - 1] for n in needs):
            raise ComposerError('step %d: needs must name earlier steps only' % i)
        out.append({'id': sid, 'skill_id': s['skill_id'], 'target': s['target'],
                    'params': dict(s['params']), 'on_fail': on_fail, 'needs': list(needs)})
    return {'steps': out}


def proposal_from_reply(reply):
    """Strictly parse model JSON into a proposal. Raises ComposerError."""
    if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY_CHARS:
        raise ComposerError('model reply is empty or oversized')
    try:
        doc = json.loads(reply)
    except ValueError:
        raise ComposerError('model reply is not JSON') from None
    return proposal_from_doc(doc)


def verification_for(skill_id):
    """Independent verification method for one skill (owner-facing)."""
    from src.runtime.routing import SKILLS
    s = SKILLS.get(skill_id, {})
    if s.get('reversibility') == 'EXACT':
        return ('independent read-back equals the target; the before value is '
                'snapshotted for exact restore')
    if skill_id in ('capture_send', 'file_push'):
        return ('hash-verified write; undo by deleting the file on the device')
    if skill_id == 'vacuum_command':
        return ('status read after the command; momentary commands report '
                'verified=null and stay unverified')
    if skill_id in ('tv_volume_step', 'app_launch', 'retro_command', 'pc_run'):
        return ('device receipt only; no independent read-back, so the step '
                'stays unverified unless a later read confirms it')
    if s.get('reversibility') == 'NONE' and s.get('idempotent'):
        return 'receipt evidence from the live read'
    return 'device receipt; independent read-back where the device allows it'


def expected_effect(skill_id, params):
    """Declared expected effect for one step (owner-facing)."""
    from src.runtime.routing import SKILLS
    s = SKILLS.get(skill_id, {})
    plain = s.get('plain', skill_id)
    keys = ', '.join('%s=%s' % (k, params[k]) for k in sorted(params))
    effect = plain + ('' if not keys else ' (%s)' % keys)
    return '%s [reversibility: %s]' % (effect, s.get('reversibility', '?'))


def failure_note(skill_id, on_fail):
    """Failure strategy note: on_fail plus the no-atomic-rollback rule."""
    from src.runtime.routing import SKILLS
    rev = (SKILLS.get(skill_id) or {}).get('reversibility')
    cont = ('dependents stop' if on_fail == 'fail'
            else 'independent steps still run; dependents of this step stop')
    if rev == 'NONE':
        return 'read-only step, nothing to undo; on failure: %s.' % cont
    if rev == 'EXACT':
        return ('exact restore is available per step through the undo primitive '
                'with a verified read-back, never atomic across steps; on '
                'failure: %s.' % cont)
    return NO_ATOMIC_ROLLBACK + ' On failure: %s.' % cont


def _refuse(step, reason):
    return {'id': step['id'], 'skill_id': step['skill_id'], 'target': step['target'],
            'params': dict(step['params']), 'needs': list(step['needs']),
            'on_fail': step['on_fail'], 'status': 'refused', 'reason': reason,
            'device_key': None, 'route': None, 'authorization': None,
            'expected_effect': None, 'verification_method': None,
            'failure_strategy': None, 'reversibility': None}


def compose(proposal, devices, router):
    """Deterministically allow or refuse each proposed step.

    proposal: proposal_from_doc/proposal_from_reply output. devices: live
    snapshot rows ({key, label, category, handles}). router: Router (or a test
    double with skill_routes). Never raises for per-step problems: every step
    comes back 'allowed' or 'refused' with an open reason.
    """
    from src.runtime import nl_plan
    from src.runtime.primitives import validate, PrimitiveError
    from src.runtime.routing import SKILLS, RouteError
    if not isinstance(proposal, dict) or not isinstance(proposal.get('steps'), list):
        raise ComposerError('proposal must be a validated proposal object')
    if not devices:
        raise ComposerError('no live devices')
    steps = []
    for s in proposal['steps']:
        skill = s.get('skill_id')
        if skill not in SKILLS:
            steps.append(_refuse(s, 'unknown skill %r' % (skill,)))
            continue
        try:
            validate(SKILLS[skill]['input'], s.get('params') or {})
        except (PrimitiveError, TypeError, ValueError) as e:
            steps.append(_refuse(s, 'invalid params: %s' % e))
            continue
        if SKILLS[skill]['targeted']:
            try:
                label, key, _ = nl_plan.resolve_target(s.get('target'), devices)
            except nl_plan.PlanError as e:
                steps.append(_refuse(s, 'unverified device: %s' % e))
                continue
            dev = next((d for d in devices if d.get('key') == key), {})
            if not dev.get('handles'):
                steps.append(_refuse(s, 'unverified device: %r has no live link' % label))
                continue
            category = dev.get('category')
        else:
            if s.get('target') != 'fabric':
                steps.append(_refuse(s, 'untargeted skill needs target "fabric"'))
                continue
            label, key, category = 'fabric', 'fabric', 'fabric'
        try:
            doc = router.skill_routes(skill, None if key == 'fabric' else key)
        except RouteError as e:
            # A failed route check refuses, never admits — but only the
            # router's declared error type. Anything else (TypeError,
            # AttributeError from schema drift or a bad double) is an
            # infrastructure bug and must raise, never masquerade as a refusal.
            steps.append(_refuse(s, 'no permitted route: %s' % str(e)[:160]))
            continue
        sel = (doc or {}).get('selected_route_id')
        route = next((r for r in (doc or {}).get('routes', [])
                      if r.get('route_id') == sel and r.get('state') == 'READY'), None)
        if route is None:
            reasons = sorted({(r.get('reason') or 'unavailable')
                              for r in (doc or {}).get('routes', [])})
            steps.append(_refuse(
                s, 'no permitted route (%s)' % (', '.join(reasons) or 'none eligible')))
            continue
        hops = route.get('hops') or []
        consent = SKILLS[skill]['consent']
        steps.append({
            'id': s['id'], 'skill_id': skill, 'target': label,
            'params': dict(s.get('params') or {}), 'needs': list(s.get('needs') or []),
            'on_fail': s.get('on_fail', 'fail'), 'status': 'allowed', 'reason': '',
            'device_key': key, 'device_category': category,
            'route': {'route_id': route['route_id'],
                      'transports': [h.get('transport') for h in hops],
                      'primitive': hops[-1].get('primitive_id') if hops else None,
                      'operation': route.get('operation_id'),
                      'evidence': route.get('evidence'),
                      'rule': (doc.get('selection') or {}).get('rule')},
            'authorization': {'consent': consent, 'approval': consent != 'none',
                              'note': ('owner approves this step before it runs'
                                       if consent != 'none'
                                       else 'read-only, no approval needed')},
            'expected_effect': expected_effect(skill, s.get('params') or {}),
            'verification_method': verification_for(skill),
            'failure_strategy': {'on_fail': s.get('on_fail', 'fail'),
                                 'note': failure_note(skill, s.get('on_fail', 'fail'))},
            'reversibility': SKILLS[skill]['reversibility']})
    allowed = sum(1 for s in steps if s['status'] == 'allowed')
    return {'composer_version': COMPOSER_VERSION, 'steps': steps,
            'allowed': allowed, 'refused': len(steps) - allowed,
            'devices': [{'label': d.get('label'), 'category': d.get('category')}
                        for d in devices],
            'rollback': NO_ATOMIC_ROLLBACK}


def to_workflow(composed, now=None):
    """Compile allowed steps into a DAG-engine workflow body.

    Each compiled step carries the route evidence it was composed against
    (route_id, route_evidence, selection_rule), a composition timestamp with
    an expiry (composed_at, expires_at), and a deterministic per-step
    idempotency key. The DAG engine re-resolves routes immediately before
    dispatch and refuses on drift or expiry, so "READY at compose time" can
    never silently become "assumed READY at run time".

    Raises ComposerError when any step was refused (the owner revises the
    proposal instead) or when the result fails DAG validation.
    """
    from src.runtime.workflows import validate_workflow, WorkflowError
    steps = (composed or {}).get('steps') or []
    if not steps:
        raise ComposerError('nothing to compile')
    refused = [(s['id'], s.get('reason', '')) for s in steps if s['status'] != 'allowed']
    if refused:
        raise ComposerError('refused steps need revision: %s'
                            % '; '.join('%s (%s)' % r for r in refused)[:400])
    composed_at = time.time() if now is None else now
    expires_at = composed_at + COMPOSED_TTL_S
    out = []
    for s in steps:
        route = s.get('route') or {}
        key_src = json.dumps({'id': s['id'], 'skill_id': s['skill_id'],
                              'target': s['target'], 'params': s['params'],
                              'route_id': route.get('route_id'),
                              'composed_at': composed_at}, sort_keys=True, default=str)
        out.append({'id': s['id'], 'skill_id': s['skill_id'], 'target': s['target'],
                    'params': dict(s['params']), 'needs': list(s['needs']),
                    'on_fail': s['on_fail'],
                    'approval': bool((s.get('authorization') or {}).get('approval')),
                    'route_id': route.get('route_id'),
                    'route_evidence': route.get('evidence'),
                    'selection_rule': route.get('rule'),
                    'composed_at': composed_at, 'expires_at': expires_at,
                    'idempotency_key': 'idem-' + hashlib.sha256(key_src.encode()).hexdigest()[:32]})
    body = {'consent': True, 'composed_at': composed_at, 'expires_at': expires_at,
            'steps': out}
    try:
        validate_workflow(body)
    except WorkflowError as e:
        raise ComposerError('composed workflow invalid: %s' % e) from None
    return body


def _control_label(label_fn, skill, target_label, device_key):
    default = ('%s on %s' % (skill, target_label or device_key))[:40]
    if label_fn is None:
        return default
    try:
        text = label_fn(skill, target_label)
    except Exception:
        return default
    if not isinstance(text, str):
        return default
    clean = ''.join(ch for ch in text.strip() if ord(ch) >= 32
                    and ch not in '<>').strip()[:40]
    return clean or default


def to_controls(composed, relay_id, label_fn=None):
    """Compile a FULLY-allowed composition into a set_controls body.

    Mirrors to_workflow's fail-closed rule: any refused step aborts the
    whole install (the owner revises instead of silently losing a step).
    Model text never reaches skill/target/params — only sanitized labels.
    The returned body carries NO consent key: the caller adds
    consent:true only after the owner reviews preview[].
    """
    from src.fabric import relay as fabric_relay
    from src.runtime.routing import SKILLS
    if not isinstance(relay_id, str) or not relay_id:
        raise ComposerError('relay_id must be a non-empty string')
    steps = (composed or {}).get('steps') or []
    if not steps:
        raise ComposerError(
            'nothing to compile: request clarification, install nothing')
    refused = [(s.get('id', '?'), s.get('reason', ''))
               for s in steps if s.get('status') != 'allowed']
    if refused:
        raise ComposerError('refused steps need revision: %s'
                            % '; '.join('%s (%s)' % r for r in refused)[:400])
    if len(steps) > fabric_relay.MAX_CONTROLS:
        raise ComposerError('too many controls: %d > %d'
                            % (len(steps), fabric_relay.MAX_CONTROLS))
    controls, preview = [], []
    for s in steps:
        skill = s.get('skill_id')
        if skill not in SKILLS:
            raise ComposerError('unknown skill %r' % (skill,))
        key = s.get('device_key')
        if SKILLS[skill]['targeted'] and not isinstance(key, str):
            raise ComposerError(
                'targeted skill %r has no verified device' % (skill,))
        target = key if SKILLS[skill]['targeted'] else 'fabric'
        label = _control_label(label_fn, skill, s.get('target'), target)
        controls.append({'label': label, 'skill_id': skill, 'target': target,
                         'params': dict(s.get('params') or {})})
        preview.append({'id': s.get('id'), 'label': label, 'skill_id': skill,
                        'target': s.get('target'), 'device_key': target,
                        'expected_effect': s.get('expected_effect', ''),
                        'route_evidence': (s.get('route') or {}).get(
                            'evidence')})
    return {'relay_id': relay_id, 'controls': controls,
            'preview': {'steps': preview, 'refused': []}}


def outcome_of(step_state, receipt):
    """Map one DAG step state + receipt onto a user-facing outcome + note."""
    receipt = receipt or {}
    rstate = receipt.get('state')
    verified = receipt.get('verified') is True
    errors = '; '.join(receipt.get('errors', ()))[:200]
    if rstate == 'REVERTED':
        if verified:
            return 'RESTORED', 'reversible state restored and read back'
        return 'EXECUTED_UNVERIFIED', 'restore attempted but not verified'
    if step_state == 'DENIED' or rstate == 'BLOCKED':
        return 'REFUSED', errors or 'the deterministic engine refused this step'
    if step_state == 'SKIPPED':
        return 'REFUSED', 'the engine did not run this step'
    if rstate == 'VERIFIED' and verified:
        return 'EXECUTED_VERIFIED', 'independent read-back confirmed the effect'
    if step_state == 'TIMEOUT' or rstate in ('TIMEOUT', 'UNKNOWN_TIMEOUT'):
        return 'UNKNOWN', ('outcome unknown: the device may have acted; '
                            'check recovery before retrying')
    if rstate == 'FAILED' or step_state == 'FAILED':
        return 'FAILED', errors or 'the step failed'
    if rstate in ('EXECUTED', 'EXECUTED_UNVERIFIED', 'PARTIAL') or step_state in ('EXECUTED', 'UNVERIFIED'):
        if rstate == 'EXECUTED' and verified:
            return 'EXECUTED_VERIFIED', 'independent read-back confirmed the effect'
        return 'EXECUTED_UNVERIFIED', 'the device acted but no independent read-back confirmed it'
    return 'UNKNOWN', 'the step has no terminal outcome yet'


def summarize(record):
    """User-facing summary of a DAG workflow record: six outcomes + disclaimer."""
    record = record or {}
    verdicts = {'done': 'completed', 'partial': 'completed with unverified steps',
                'failed': 'failed', 'cancelled': 'cancelled',
                'waiting_approval': 'waiting for approval', 'running': 'running'}
    steps = []
    for s in record.get('steps') or []:
        outcome, note = outcome_of(s.get('state'), s.get('receipt'))
        extra = (s.get('note') or '')
        if outcome in ('REFUSED', 'FAILED', 'UNKNOWN') and extra:
            note = '%s (%s)' % (note, extra[:160])
        steps.append({'id': s.get('id'), 'outcome': outcome,
                      'label': OUTCOME_LABELS[outcome], 'note': note})
    counts = {o: sum(1 for s in steps if s['outcome'] == o) for o in OUTCOMES}
    return {'workflow_id': record.get('workflow_id', ''),
            'status': record.get('status', 'unknown'),
            'verdict': verdicts.get(record.get('status'), record.get('status', 'unknown')),
            'steps': steps, 'counts': counts, 'rollback': NO_ATOMIC_ROLLBACK}


def propose_and_compose(text, devices, router, proposer):
    """Full bridge: grounded prompt -> Meta proposer -> deterministic compose."""
    if not isinstance(text, str) or not text.strip():
        raise ComposerError('empty request')
    if not devices:
        raise ComposerError('no live devices')
    prompt = build_prompt(text, devices)
    try:
        res = proposer(prompt)
    except ComposerError:
        raise
    except Exception as e:  # noqa: BLE001 - a dead model is a refusal, never a guess
        raise ComposerError('model unavailable: %s' % e) from None
    if not isinstance(res, dict) or not res.get('content'):
        raise ComposerError('model returned no usable content')
    composed = compose(proposal_from_reply(res['content']), devices, router)
    composed['model_run'] = {'provider': 'meta', 'model': res.get('model_id', 'unknown'),
                             'endpoint': res.get('endpoint', '')}
    composed['reply_sha256'] = hashlib.sha256(res['content'].encode()).hexdigest()
    composed['reply_chars'] = len(res['content'])
    return composed


def catalog():
    """User-facing composer catalog: skills, outcomes and the rollback rule."""
    from src.runtime.routing import SKILLS
    return {'composer_version': COMPOSER_VERSION, 'max_steps': MAX_COMPOSED_STEPS,
            'skills': [{'skill_id': sid, 'plain': s.get('plain'),
                        'targeted': s.get('targeted'), 'reversibility': s.get('reversibility'),
                        'consent': s.get('consent'), 'input': s.get('input'),
                        'audience': SKILL_AUDIENCE.get(sid, 'any linked device'),
                        'verification': verification_for(sid)}
                       for sid, s in sorted(SKILLS.items())],
            'outcomes': [{'id': o, 'label': OUTCOME_LABELS[o]} for o in OUTCOMES],
            'rollback': NO_ATOMIC_ROLLBACK}
