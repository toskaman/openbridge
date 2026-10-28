"""Command Center P0: NL quality router (Low local -> Medium local -> High cloud).

Tier endpoints MUST stay members of config/runtime_models.json (tested). The
router never invents: malformed model output, unknown skills and low confidence
become unsupported/escalation_required, never a guessed command. Cloud is used
only with an explicit cloud_allowed consent; local failures alone never trigger
a paid call.
"""
from src.runtime import intent as I
from src.runtime import skills as S

TIERS = {'low': ('llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437'),
         'medium': ('muse-glimmer:30b-q4_K_M', 'http://127.0.0.1:11438'),
         'high': ('muse-spark-1.3', 'https://api.meta.ai/v1/chat/completions')}
MIN_CONFIDENCE = 0.5


class TransportError(Exception):
    pass


class _GateBlocked(Exception):
    pass


INTENT_SCHEMA = {'type': 'object', 'additionalProperties': False,
    'required': ['outcome', 'skill_id', 'targets', 'params', 'confidence',
                 'ambiguities', 'clarifying_question'],
    'properties': {
        'outcome': {'type': 'string'},
        'skill_id': {'type': ['string', 'null']},
        'targets': {'type': 'array', 'maxItems': 8, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['kind', 'ref'],
            'properties': {'kind': {'type': 'string',
                                    'enum': ['device', 'group', 'category', 'room', 'originator']},
                           'ref': {'type': 'string'}}}},
        'params': {'type': 'object'},
        'confidence': {'type': 'number'},
        'ambiguities': {'type': 'array', 'maxItems': 8, 'items': {'type': 'string'}},
        'clarifying_question': {'type': ['string', 'null']}}}


class OllamaIntentTransport:
    """Strict NL-parse transport over a pinned local Ollama endpoint.

    Mirrors LocalMetaBroker's identity/digest/shape checks; the endpoint must be
    declared in the runtime manifest. Any deviation becomes TransportError, which
    the router turns into escalation_required — never a guessed command.
    """

    def __init__(self, model_id, endpoint, digest=None, catalog=None, chat=None, timeout=120):
        from src.ai.local_meta import local_request
        self.model_id, self.endpoint, self.digest = model_id, endpoint, digest
        self._catalog = catalog or (lambda: local_request('/api/tags', endpoint=endpoint))
        self._chat = chat or (lambda payload: local_request('/api/chat', payload,
                                                             endpoint=endpoint, timeout=timeout))

    def ready(self):
        try:
            rows = self._catalog().get('models', [])
            m = next((r for r in rows if r.get('name') == self.model_id), None)
            if m is None:
                return False
            if self.digest is not None:
                return m.get('digest', '').removeprefix('sha256:') == self.digest
            return True
        except Exception:
            return False

    def __call__(self, prompt):
        from src.ai import registry
        try:
            registry.require(self.model_id, self.endpoint)
        except registry.RegistryInvalid as e:
            raise TransportError(str(e)) from None
        payload = {'model': self.model_id, 'stream': False, 'format': INTENT_SCHEMA,
                   'keep_alive': '30s', 'options': {'temperature': 0, 'num_ctx': 4096},
                   'messages': [{'role': 'system', 'content':
                                  'Reply in English only as compact JSON matching the schema.'},
                                 {'role': 'user', 'content': prompt}]}
        try:
            r = self._chat(payload)
            if r.get('model') != self.model_id or r.get('done') is not True \
                    or r.get('done_reason') != 'stop':
                raise TransportError('model identity or completion state invalid')
            msg = r['message']
            if msg.get('tool_calls') or not isinstance(msg.get('content'), str) \
                    or len(msg['content']) > 16384:
                raise TransportError('unexpected output shape')
            for k in ('prompt_eval_count', 'eval_count'):
                if type(r.get(k)) is not int or not 0 <= r[k] <= 8192:
                    raise TransportError('usage metadata invalid')
            out = __import__('json').loads(msg['content'])
            if not isinstance(out, dict):
                raise TransportError('reply is not an object')
            return out
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(f'local parse failed: {type(e).__name__}') from None


def build_prompt(text, lang):
    lines = ['You map a user request to ONE registered OpenBridge skill.',
             'Reply with ONLY a JSON object with exactly these keys: outcome (string),',
             'skill_id (string or null), targets (array of {kind, ref}), params (object),',
             'confidence (0..1), ambiguities (string array), clarifying_question (string or null).',
             'Use skill_id null + clarifying_question when ambiguous; unknown requests get',
             'skill_id null and confidence 0. Never invent a skill_id. Registered skills:']
    for c in S.all_skills():
        lines.append(f"- {c['skill_id']}: {c['description']} (targets: {','.join(c['targets'])})")
    lines.append('Example: "Start my vacuum" -> {"outcome": "start cleaning", '
                 '"skill_id": "vacuum.start", "targets": [{"kind": "device", "ref": "vacuum"}], '
                 '"params": {}, "confidence": 0.9, "ambiguities": [], "clarifying_question": null}')
    lines.append('Example: "Turn on my vacuum" -> {"outcome": "ambiguous power vs clean", '
                 '"skill_id": null, "targets": [], "params": {}, "confidence": 0.0, '
                 '"ambiguities": ["power vs clean"], '
                 '"clarifying_question": "Power on, or start cleaning?"}')
    lines.append(f'User language: {lang}. User request: {text}')
    return '\n'.join(lines)


def _keyword_fallback(text, outcome):
    """Deterministic catalog match used ONLY after a model abstention (skill null).

    Scores each registered skill by keyword hits in the request + stated outcome;
    resolves only on a unique best score, else None (no guessing). Callers must
    label the resolution as deterministic in the ambiguities.
    """
    hay = f'{text} {outcome or ""}'.lower()
    scored = sorted(((sum(1 for k in c['keywords'] if k in hay), c['skill_id'])
                     for c in S.all_skills()), reverse=True)
    if len(scored) > 1 and scored[0][0] > scored[1][0] and scored[0][0] > 0:
        return scored[0][1]
    return None


def _interpret(doc, reply, parser, model_id):
    doc = dict(doc, provenance={'parser': parser, 'model_id': model_id})
    if (not isinstance(reply, dict) or set(reply) !=
            {'outcome', 'skill_id', 'targets', 'params', 'confidence',
             'ambiguities', 'clarifying_question'}):
        return dict(doc, status='escalation_required',
                    ambiguities=['model reply malformed'])
    sid = reply['skill_id']
    if sid is None:
        if reply['clarifying_question']:
            return dict(doc, status='needs_clarification',
                        clarifying_question=str(reply['clarifying_question'])[:300],
                        ambiguities=[str(a)[:200] for a in reply['ambiguities']][:8])
        return dict(doc, status='unsupported',
                    ambiguities=['no registered skill matches'])
    if S.get(sid) is None:
        return dict(doc, status='unsupported',
                    ambiguities=[f'model proposed unknown skill {sid}'])
    conf = reply['confidence']
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) or conf < MIN_CONFIDENCE:
        return dict(doc, status='escalation_required',
                    ambiguities=['model confidence below 0.5'])
    try:
        resolved = dict(doc, status='resolved', outcome=str(reply['outcome'])[:300],
                        skill_id=sid, targets=reply['targets'], params=reply['params'],
                        confidence=float(conf),
                        ambiguities=[str(a)[:200] for a in reply['ambiguities']][:8])
        S.resolve(sid, reply['params'] if isinstance(reply['params'], dict) else {'!': 1})
    except (S.SkillError, ValueError, TypeError, AttributeError):
        return dict(doc, status='escalation_required',
                    ambiguities=['resolved document failed validation'])
    if I.validate_intent(resolved):
        return dict(doc, status='escalation_required',
                    ambiguities=I.validate_intent(resolved)[:4])
    return resolved


class CloudIntentTransport:
    """Strict NL-parse transport over the Meta Model API.

    Reuses a caller-supplied sender (the broker's MetaTransport in production).
    Model identity, usage bounds and per-call cost ceiling mirror the advisory
    broker; last usage is kept on self.last_usage for receipts.
    """

    def __init__(self, model_id, endpoint, send):
        self.model_id, self.endpoint, self._send = model_id, endpoint, send
        self.last_usage = None

    def __call__(self, prompt):
        import json
        from src.ai import registry
        try:
            registry.require(self.model_id, self.endpoint)
        except registry.RegistryInvalid as e:
            raise TransportError(str(e)) from None
        payload = {'model': self.model_id, 'max_completion_tokens': 4000,
                   'messages': [{'role': 'developer', 'content':
                                 'Reply with ONLY a JSON object matching the requested schema.'},
                                {'role': 'user', 'content': prompt}]}
        try:
            r = self._send(payload)
            if r.get('model') != self.model_id:
                raise TransportError('returned model identity is not approved')
            usage = r['usage']
            for f in ('prompt_tokens', 'completion_tokens'):
                if type(usage[f]) is not int or not 0 <= usage[f] <= 100_000:
                    raise TransportError('invalid provider usage')
            content = r['choices'][0]['message'].get('content')
            if not isinstance(content, str) or not content.strip() or len(content) > 16384:
                raise TransportError('model returned no usable content')
            out = json.loads(content)
            if not isinstance(out, dict):
                raise TransportError('reply is not an object')
            estimate = (usage['prompt_tokens'] * 1.25 + usage['completion_tokens'] * 4.25) / 1_000_000
            if estimate > 0.10:
                raise TransportError('provider usage exceeded per-call ceiling')
            self.last_usage = {'usage': dict(usage), 'estimated_cost_usd': estimate,
                               'request_id': r.get('id')}
            return out
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(f'cloud parse failed: {type(e).__name__}') from None


def parse(text, lang, quality, local_transport, cloud_transport=None,
          medium_transport=None, cloud_allowed=False, before_cloud=None):
    doc = I.new_intent(text, lang)
    if quality not in ('low', 'medium', 'high', 'auto'):
        raise ValueError('quality must be low|medium|high|auto')
    prompt = build_prompt(text, lang)
    plan = {'low': [('low', local_transport, 'local')],
            'medium': [('medium', local_transport, 'local')],
            'high': [('high', cloud_transport, 'cloud')],
            'auto': [('low', local_transport, 'local'),
                     ('medium', medium_transport, 'local')] if medium_transport
            else [('low', local_transport, 'local')]}[quality]
    skip = object()

    def gated(tier, transport, parser):
        if transport is None:
            return skip
        if parser == 'cloud' and before_cloud is not None:
            try:
                before_cloud()
            except Exception as e:
                raise _GateBlocked(str(e)[:200])
        try:
            return transport(prompt)
        except TransportError:
            return skip

    for tier, transport, parser in plan:
        try:
            reply = gated(tier, transport, parser)
        except _GateBlocked as e:
            return dict(doc, status='escalation_required', ambiguities=[str(e)])
        if reply is skip:
            continue
        out = _interpret(doc, reply, parser, TIERS[tier][0])
        if out['status'] == 'unsupported' and 'no registered skill matches' in out['ambiguities'] \
                and isinstance(reply, dict):
            fb = _keyword_fallback(text, reply.get('outcome'))
            if fb is not None and reply.get('targets'):
                try:
                    cand = dict(out, status='resolved', skill_id=fb,
                                outcome=str(reply.get('outcome') or text)[:300],
                                targets=reply['targets'],
                                params=reply['params'] if isinstance(reply.get('params'), dict) else {},
                                confidence=0.6,
                                ambiguities=['deterministic catalog match after model abstention'])
                    S.resolve(fb, cand['params'])
                    if not I.validate_intent(cand):
                        return cand
                except (S.SkillError, ValueError, TypeError, AttributeError):
                    pass
        if out['status'] in ('resolved', 'unsupported', 'needs_clarification'):
            return out
        doc = out
    if quality in ('high', 'auto'):
        if cloud_transport is not None and cloud_allowed:
            if before_cloud is not None:
                try:
                    before_cloud()
                except Exception as e:
                    return dict(doc, status='escalation_required', ambiguities=[str(e)[:200]])
            try:
                reply = cloud_transport(prompt)
            except TransportError:
                pass
            else:
                out = _interpret(doc, reply, 'cloud', TIERS['high'][0])
                if out['status'] == 'unsupported' and 'no registered skill matches' in out['ambiguities'] \
                        and isinstance(reply, dict):
                    fb = _keyword_fallback(text, reply.get('outcome'))
                    if fb is not None and reply.get('targets'):
                        try:
                            cand = dict(out, status='resolved', skill_id=fb,
                                        outcome=str(reply.get('outcome') or text)[:300],
                                        targets=reply['targets'],
                                        params=reply['params'] if isinstance(reply.get('params'), dict) else {},
                                        confidence=0.6,
                                        ambiguities=['deterministic catalog match after model abstention'])
                            S.resolve(fb, cand['params'])
                            if not I.validate_intent(cand):
                                return cand
                        except (S.SkillError, ValueError, TypeError, AttributeError):
                            pass
                if out['status'] in ('resolved', 'unsupported', 'needs_clarification'):
                    return out
                doc = out
        else:
            return dict(doc, status='escalation_required',
                        ambiguities=list(doc.get('ambiguities') or [])
                        + ['cloud needs explicit authorization'])
    if doc['status'] == 'draft':
        doc = dict(doc, status='escalation_required',
                   ambiguities=['all local tiers failed'])
    return doc
