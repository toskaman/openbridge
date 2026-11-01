"""S4 NL->workflow planning bridge: a Meta model proposes a multi-step plan, the
deterministic validator admits only registered skills on live devices.

The model is never trusted: unknown skills, unresolvable targets and invalid
params become PlanError, never a guessed command. Execution stays on the
existing Router + workflow engine with per-step approval and consent binding.

Campaign Two S4.7: replies use the discriminated Meta result envelope
(Proposal | Clarification | Refusal). A refusal or clarification validates
to nothing executable -- the model may always refuse instead of emitting
steps. Bare {"steps": [...]} replies are still accepted for backward
compatibility with recorded prompts and direct API users.
"""
import hashlib
import json

MAX_STEPS = 8
MAX_REPLY_CHARS = 16384

# Ollama structured-output constraint (shape only; values stay model-authored
# and are re-validated deterministically by plan_from_reply).
PLAN_JSON_SCHEMA = {'type': 'object',
    'required': ['steps'],
    'properties': {'steps': {'type': 'array', 'minItems': 1, 'maxItems': MAX_STEPS,
        'items': {'type': 'object', 'required': ['skill_id', 'target', 'params'],
            'properties': {'skill_id': {'type': 'string'}, 'target': {'type': 'string'},
                           'params': {'type': 'object'}}}}}}

# S4.7 envelope constraint: the same steps shape wrapped in the shared
# discriminated outcome, so constrained decoding can still emit a refusal
# or a clarification instead of steps.
PLAN_RESPONSE_SCHEMA = {'type': 'object',
    'required': ['outcome'],
    'properties': {'outcome': {'type': 'string'},
                   'steps': {'type': 'array', 'minItems': 1, 'maxItems': MAX_STEPS,
                       'items': {'type': 'object', 'required': ['skill_id', 'target', 'params'],
                           'properties': {'skill_id': {'type': 'string'}, 'target': {'type': 'string'},
                                          'params': {'type': 'object'}}}},
                   'reason': {'type': 'string'},
                   'code': {'type': 'string'},
                   'clarifying_question': {'type': 'string'}}}


class PlanError(ValueError):
    pass


class TransportError(Exception):
    pass


def _param_hint(schema):
    props = (schema or {}).get('properties') or {}
    bits = []
    for name, sub in sorted(props.items()):
        if isinstance(sub, dict) and 'enum' in sub:
            bits.append('%s=%s' % (name, '|'.join(str(v) for v in sub['enum'][:12])))
        elif isinstance(sub, dict):
            bits.append('%s:%s' % (name, sub.get('type', 'any')))
    return '{%s}' % ', '.join(bits)


def param_hint(schema):
    """Public param-shape hint for prompt builders (S4 + S5 share it)."""
    return _param_hint(schema)


def build_prompt(text, devices):
    """Strict planning prompt: labels + categories only, never device keys."""
    from src.runtime.routing import SKILLS
    dev_lines = ['- %s (%s)' % (d.get('label'), d.get('category')) for d in devices]
    skill_lines = ['- %s %s reversibility=%s consent=%s' % (sid, _param_hint(s.get('input')),
                                                            s.get('reversibility'), s.get('consent'))
                   for sid, s in sorted(SKILLS.items())]
    prompt = ('You plan device actions. Reply with ONE JSON object and nothing else: '
            '{"steps": [{"skill_id": "<id>", "target": "<device label>", '
            '"params": {}}]}. Rules: 1..%d steps; skill_id must be listed below; copy the target '
            'label EXACTLY character-for-character from the Devices list (never abbreviate; '
            '"fabric" only for untargeted skills); params must match the hint exactly, no extra '
            'keys. Example: {"steps": [{"skill_id": "tv_volume_step", "target": "android tv", '
            '"params": {"direction": "down"}}]}. Request: %s\nDevices:\n%s\nSkills:\n%s'
            % (MAX_STEPS, text.strip()[:500], '\n'.join(dev_lines), '\n'.join(skill_lines)))
    prompt += (' If the request needs a skill, device, capability, approval bypass or '
               'irreversible change not covered above, do NOT guess steps: reply '
               '{"outcome": "refusal", "reason": "<why, <=500 chars>"} with no steps. '
               'If exactly two readings match equally well, reply '
               '{"outcome": "clarification", "clarifying_question": "<one question>"} '
               'with no steps. A proposal wraps the steps object as '
               '{"outcome": "proposal", "steps": [...]}.')
    return prompt


def resolve_target(target, devices):
    """Validate a model target; return (label, key_hint, disambiguated).

    The LABEL is the stable reference: device keys rotate every discovery, so
    plan-time keys would be stale at run time. The run layer re-resolves the
    label against the live snapshot (same ghost rule as here).
    """
    if not isinstance(target, str) or not target or len(target) > 64:
        raise PlanError('invalid target %r' % (target,))
    for d in devices:
        if d.get('key') == target:
            return d.get('label'), d['key'], False
    hits = [d for d in devices if (d.get('label') or '').strip().lower() == target.strip().lower()]
    if len(hits) == 1:
        return hits[0].get('label'), hits[0]['key'], False
    linked = [d for d in hits if d.get('handles')]
    if len(hits) > 1 and len(linked) == 1:
        # Ghost rows (mDNS/media shadows with no link) can never execute;
        # routing would mark them link_down. Collapse openly, never silently.
        return linked[0].get('label'), linked[0]['key'], True
    raise PlanError('target %r matches %d live devices' % (target, len(hits)))


def _resolve_target(target, devices):
    label, _, disambiguated = resolve_target(target, devices)
    return label, disambiguated


def _spec_from_steps(steps, devices):
    """Strictly validate a steps list into a workflow body. Raises PlanError."""
    from src.runtime.primitives import validate, PrimitiveError
    from src.runtime.routing import SKILLS
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        raise PlanError('reply needs steps[1..%d]' % MAX_STEPS)
    out = []
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or set(s) - {'skill_id', 'target', 'params'}:
            raise PlanError('step %d: only skill_id/target/params allowed' % i)
        skill = s.get('skill_id')
        if skill not in SKILLS:
            raise PlanError('step %d: unknown skill %r' % (i, skill))
        target = s.get('target')
        disambiguated = False
        if SKILLS[skill]['targeted']:
            target, disambiguated = _resolve_target(target, devices)
        elif target != 'fabric':
            raise PlanError('step %d: untargeted skill needs target "fabric"' % i)
        params = s.get('params')
        if not isinstance(params, dict):
            raise PlanError('step %d: params must be an object' % i)
        try:
            validate(SKILLS[skill]['input'], params)
        except PrimitiveError as e:
            raise PlanError('step %d: invalid params: %s' % (i, e)) from None
        step = {'id': 'step%d' % i, 'skill_id': skill, 'target': target,
                'params': dict(params), 'approval': SKILLS[skill]['consent'] != 'none',
                'reversibility': SKILLS[skill]['reversibility']}
        if disambiguated:
            step['disambiguated'] = True
        out.append(step)
    return {'consent': True, 'steps': out}


def parse_plan_response(doc, devices):
    """Split an enveloped reply into (outcome, spec|None, detail).

    Only outcome == 'proposal' yields a validated spec; refusal and
    clarification yield None (nothing executable). Raises PlanError on any
    shape violation, including a payload smuggled on a non-proposal.
    """
    from src.forge import meta_result
    try:
        outcome, spec, detail, _ = meta_result.parse(
            doc, 'steps', lambda steps: _spec_from_steps(steps, devices))
    except meta_result.MetaError as e:
        raise PlanError(str(e)) from None
    return outcome, spec, detail


def _apply_intent_effect_gate(request_text, spec, devices):
    """FINAL FRONTIER S8: refuse/clarify proposals unrelated to the request."""
    from src.runtime import intent_effect
    try:
        intent_effect.check(request_text, spec, devices)
    except intent_effect.IntentEffectError as e:
        verb = 'refused' if e.kind == intent_effect.REFUSAL else 'needs clarification'
        raise PlanError('model %s: %s' % (verb, e.detail)) from None


def plan_from_reply(reply, devices, request_text=None):
    """Strictly validate model JSON into a workflow body. Raises PlanError.

    Accepts the S4.7 discriminated envelope (a proposal's steps are
    validated; a refusal or clarification raises PlanError carrying the
    model's own words, so nothing executes) and, for backward
    compatibility, a bare {"steps": [...]} object.

    When request_text is given, the S8 intent/effect gate additionally
    verifies the proposal actually matches the requested effect; unrelated
    substitutions raise PlanError as a refusal or a clarification.
    """
    if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY_CHARS:
        raise PlanError('model reply is empty or oversized')
    try:
        doc = json.loads(reply)
    except ValueError:
        raise PlanError('model reply is not JSON') from None
    if isinstance(doc, dict) and 'outcome' in doc:
        outcome, spec, detail = parse_plan_response(doc, devices)
        if outcome != 'proposal':
            verb = 'refused' if outcome == 'refusal' else 'needs clarification'
            raise PlanError('model %s: %s' % (verb, detail))
        if request_text is not None:
            _apply_intent_effect_gate(request_text, spec, devices)
        return spec
    steps = doc.get('steps') if isinstance(doc, dict) else None
    spec = _spec_from_steps(steps, devices)
    if request_text is not None:
        _apply_intent_effect_gate(request_text, spec, devices)
    return spec


def local_chat(model_id, endpoint, timeout=180, chat=None, format=None, options=None):
    """Pinned local Meta chat transport, mirroring nl_router's identity/shape checks."""
    from src.ai.local_meta import local_request
    send = chat or (lambda payload: local_request('/api/chat', payload, endpoint=endpoint, timeout=timeout))
    run_options = {'temperature': 0}
    run_options.update(options or {})

    def run(prompt):
        # think=False: thinking models (Glimmer) would otherwise burn the
        # whole token budget on an unconstrained thinking trace and return
        # empty content (done_reason=length, eval=cap). Ignored by
        # non-thinking models. Same precedent as the tier probe payload.
        payload = {'model': model_id, 'stream': False, 'think': False,
                   'format': format or PLAN_JSON_SCHEMA,
                   'options': run_options, 'keep_alive': '10m',
                   'messages': [{'role': 'system', 'content':
                                 'Reply in English only as compact JSON matching the schema.'},
                                {'role': 'user', 'content': prompt}]}
        try:
            r = send(payload)
        except Exception as e:
            raise TransportError('%s: %s' % (model_id, e)) from None
        if r.get('model') != model_id or r.get('done') is not True or r.get('done_reason') != 'stop':
            raise TransportError('model identity or completion state invalid')
        content = (r.get('message') or {}).get('content', '')
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_REPLY_CHARS:
            raise TransportError('%s returned no usable content' % model_id)
        return {'model_id': model_id, 'endpoint': endpoint, 'content': content}

    return run


def plan(text, devices, transport):
    """Full bridge: prompt -> transport -> strict validation + provenance."""
    if not text.strip():
        raise PlanError('empty request')
    if not devices:
        raise PlanError('no live devices')
    try:
        res = transport(build_prompt(text, devices))
    except TransportError as e:
        raise PlanError('model unavailable: %s' % e) from None
    if not isinstance(res, dict) or not res.get('content'):
        raise PlanError('model returned no usable content')
    spec = plan_from_reply(res['content'], devices, request_text=text)
    return {'spec': spec,
            'model_run': {'provider': 'meta', 'model': res.get('model_id', 'unknown'),
                          'endpoint': res.get('endpoint', '')},
            'reply_sha256': hashlib.sha256(res['content'].encode()).hexdigest(),
            'reply_chars': len(res['content'])}
