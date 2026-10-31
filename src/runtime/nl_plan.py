"""S4 NL->workflow planning bridge: a Meta model proposes a multi-step plan, the
deterministic validator admits only registered skills on live devices.

The model is never trusted: unknown skills, unresolvable targets and invalid
params become PlanError, never a guessed command. Execution stays on the
existing Router + workflow engine with per-step approval and consent binding.
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


def build_prompt(text, devices):
    """Strict planning prompt: labels + categories only, never device keys."""
    from src.runtime.routing import SKILLS
    dev_lines = ['- %s (%s)' % (d.get('label'), d.get('category')) for d in devices]
    skill_lines = ['- %s %s reversibility=%s consent=%s' % (sid, _param_hint(s.get('input')),
                                                            s.get('reversibility'), s.get('consent'))
                   for sid, s in sorted(SKILLS.items())]
    return ('You plan device actions. Reply with ONE JSON object and nothing else: '
            '{"steps": [{"skill_id": "<id>", "target": "<device label>", '
            '"params": {}}]}. Rules: 1..%d steps; skill_id must be listed below; copy the target '
            'label EXACTLY character-for-character from the Devices list (never abbreviate; '
            '"fabric" only for untargeted skills); params must match the hint exactly, no extra '
            'keys. Example: {"steps": [{"skill_id": "tv_volume_step", "target": "android tv", '
            '"params": {"direction": "down"}}]}. Request: %s\nDevices:\n%s\nSkills:\n%s'
            % (MAX_STEPS, text.strip()[:500], '\n'.join(dev_lines), '\n'.join(skill_lines)))


def resolve_target(target, devices):
    """Validate a model target; return (label, key_hint, disambiguated).

    The LABEL is the stable reference: device keys rotate every discovery, so
    plan-time keys would be stale at run time. The run layer re-resolves the
    label against the live snapshot (same ghost rule as here)."""
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


def plan_from_reply(reply, devices):
    """Strictly validate model JSON into a workflow body. Raises PlanError."""
    from src.runtime.primitives import validate, PrimitiveError
    from src.runtime.routing import SKILLS
    if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY_CHARS:
        raise PlanError('model reply is empty or oversized')
    try:
        doc = json.loads(reply)
    except ValueError:
        raise PlanError('model reply is not JSON') from None
    steps = doc.get('steps') if isinstance(doc, dict) else None
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


def local_chat(model_id, endpoint, timeout=180, chat=None):
    """Pinned local Meta chat transport, mirroring nl_router's identity/shape checks."""
    from src.ai.local_meta import local_request
    send = chat or (lambda payload: local_request('/api/chat', payload, endpoint=endpoint, timeout=timeout))

    def run(prompt):
        payload = {'model': model_id, 'stream': False, 'format': PLAN_JSON_SCHEMA,
                   'keep_alive': '10m', 'options': {'temperature': 0, 'num_ctx': 4096},
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
    spec = plan_from_reply(res['content'], devices)
    return {'spec': spec,
            'model_run': {'provider': 'meta', 'model': res.get('model_id', 'unknown'),
                          'endpoint': res.get('endpoint', '')},
            'reply_sha256': hashlib.sha256(res['content'].encode()).hexdigest(),
            'reply_chars': len(res['content'])}
