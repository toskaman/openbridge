"""Command Center P0: NL quality router (Low local -> Medium local -> High = your connected AI).

The Low tier understands requests with OpenBridge's own command model (src/ai/own_model.py) and falls back to the
pinned Llama 3.2 3B when it is not installed (PreferredTransport); TIERS keeps the general models, which also serve
planning (`propose`, `plan-text`, `compose-text`).

Low/Medium endpoints MUST stay members of config/runtime_models.json (tested). High is the
model or API the owner connected by hand (src/ai/custom_provider.py); no paid model is built in.
The router never invents: malformed model output, unknown skills and low confidence become
unsupported/escalation_required, never a guessed command. A connected provider that is not on
this PC is used only with an explicit cloud_allowed consent; local failures alone never send
text off the PC. (The parser label stays "cloud" in intents for compatibility: it means
"the owner's connected provider".)
"""
import re

from src.runtime import intent as I
from src.runtime import skills as S

_WORD_RX_CACHE = {}


def _word_hit(keyword, hay):
    """Whole-word keyword hit (both boundaries). Substring matching ('set'
    inside 'reset', 'fabric' inside 'fabricant', 'ou' inside 'vous') fired
    the deterministic fallback on unrelated requests; word boundaries keep
    recall on true mentions (verified: 13/13 legit eval-1000 resolves kept,
    the 14th was itself a fabricant artifact). Patterns cached: the keyword
    catalog is static (<= ~50 entries)."""
    rx = _WORD_RX_CACHE.get(keyword)
    if rx is None:
        rx = re.compile(r'\b' + re.escape(keyword) + r'\b')
        _WORD_RX_CACHE[keyword] = rx
    return rx.search(hay) is not None

TIERS = {'low': ('llama3.2:3b-instruct-q4_K_M', 'http://127.0.0.1:11437'),
         'medium': ('muse-glimmer:30b-q4_K_M', 'http://127.0.0.1:11438')}


def high_tier(providers_path=None):
    """(model, endpoint) of the owner's active connected provider, or (None, None)."""
    from src.ai import custom_provider
    entry = custom_provider.active(providers_path)
    if entry is None:
        return None, None
    return entry['model'], custom_provider.endpoint(entry)
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
        self.last_ok = None   # last inference outcome: tags-present does not imply inference works
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
            self.last_ok = False
            raise TransportError(str(e)) from None
        payload = {'model': self.model_id, 'stream': False, 'format': INTENT_SCHEMA,
                   'keep_alive': '10m', 'options': {'temperature': 0, 'num_ctx': 4096},
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
            self.last_ok = True
            return out
        except TransportError:
            self.last_ok = False
            raise
        except Exception as e:
            self.last_ok = False
            raise TransportError(f'local parse failed: {type(e).__name__}') from None


class PreferredTransport:
    """OpenBridge's own command model first, the general model when it is absent or fails.

    `answered_by` names the model that produced the last reply, for the intent's provenance and the receipt.
    The fallback is tried only after the preferred model failed or is not installed, never in addition to a
    usable reply, so one request costs at most one call per model."""

    def __init__(self, preferred, fallback):
        self.preferred, self.fallback = preferred, fallback
        self.model_id = preferred.model_id
        self.endpoint = preferred.endpoint
        self.answered_by = None

    @property
    def last_ok(self):
        for t in (self.preferred, self.fallback):
            if getattr(t, 'last_ok', None) is not None:
                return t.last_ok
        return None

    def ready(self):
        return bool(self.preferred.ready() or self.fallback.ready())

    def __call__(self, prompt):
        self.answered_by = None
        if self.preferred.ready():
            try:
                out = self.preferred(prompt)
                self.answered_by = self.preferred.model_id
                return out
            except TransportError:
                pass
        out = self.fallback(prompt)
        self.answered_by = self.fallback.model_id
        return out


def build_prompt(text, lang):
    lines = ['You map a user request to ONE registered OpenBridge skill.',
             'Reply with ONLY a JSON object with exactly these keys: outcome (string),',
             'skill_id (string or null), targets (array of {kind, ref}), params (object),',
             'confidence (0..1), ambiguities (string array), clarifying_question (string or null).',
             'Use skill_id null + clarifying_question when ambiguous; unknown requests get',
             'skill_id null and confidence 0. Never invent a skill_id. Registered skills:']
    for c in S.all_skills():
        lines.append(f"- {c['skill_id']}: {c['description']} (targets: {','.join(c['targets'])}; "
                     f"words: {', '.join(c['keywords'])})")
    lines.append('Prefer resolving with the closest registered skill. Ask a clarifying '
                 'question ONLY when two or more registered skills match equally well.')
    lines.append('Example: "Start my vacuum" -> {"outcome": "start cleaning", '
                 '"skill_id": "vacuum.start", "targets": [{"kind": "device", "ref": "vacuum"}], '
                 '"params": {}, "confidence": 0.9, "ambiguities": [], "clarifying_question": null}')
    lines.append('Example: "How many devices are online" -> {"outcome": "count online devices", '
                 '"skill_id": "fabric.status", "targets": [{"kind": "category", "ref": "fabric"}], '
                 '"params": {}, "confidence": 0.9, "ambiguities": [], "clarifying_question": null}')
    lines.append('Example: "Scan for bluetooth devices" -> {"outcome": "scan nearby bluetooth", '
                 '"skill_id": "ble_scan_room", "targets": [{"kind": "device", "ref": "relay"}], '
                 '"params": {}, "confidence": 0.9, "ambiguities": [], "clarifying_question": null}')
    lines.append('Example: "Open YouTube on the TV" -> {"outcome": "open youtube on tv", '
                 '"skill_id": "app_launch", "targets": [{"kind": "device", "ref": "tv"}], '
                 '"params": {"package": "com.google.android.youtube.tv"}, "confidence": 0.9, '
                 '"ambiguities": [], "clarifying_question": null})')
    lines.append('Example: "Turn it up" -> {"outcome": "ambiguous tv volume set vs step", '
                 '"skill_id": null, "targets": [], "params": {}, "confidence": 0.0, '
                 '"ambiguities": ["set vs step"], '
                 '"clarifying_question": "Set an exact volume, or step up once?"}')
    lines.append('Example: "Turn the vacuum on and off" -> {"outcome": "conflicting start vs pause", '
                 '"skill_id": null, "targets": [], "params": {}, "confidence": 0.0, '
                 '"ambiguities": ["start vs pause"], '
                 '"clarifying_question": "Should the vacuum start, or pause?"}')
    lines.append('Example: "Book me a flight to Paris" -> {"outcome": "no registered skill books flights", '
                 '"skill_id": null, "targets": [], "params": {}, "confidence": 0.0, '
                 '"ambiguities": [], "clarifying_question": null})')
    lines.append(f'User language: {lang}. User request: {text}')
    return '\n'.join(lines)


def _keyword_fallback(text, outcome):
    """Deterministic catalog match used ONLY after a model abstention (skill null).

    Scores each registered skill by keyword hits in the request + stated outcome;
    resolves only on a unique best score, else None (no guessing). Callers must
    label the resolution as deterministic in the ambiguities.
    """
    hay = f'{text} {outcome or ""}'.lower()
    scored = sorted(((sum(1 for k in c['keywords'] if _word_hit(k, hay)), c['skill_id'])
                     for c in S.all_skills()), reverse=True)
    if len(scored) > 1 and scored[0][0] > scored[1][0] and scored[0][0] > 0:
        return scored[0][1]
    return None


def _fallback_candidate(text, reply, out):
    """Build the deterministic resolution after a model abstention, or None.

    Fabric-scoped skills get the virtual target injected when the model supplied
    none; every other skill still needs model-provided targets (no guessing)."""
    if not isinstance(reply, dict):
        return None
    fb = _keyword_fallback(text, reply.get('outcome'))
    if fb is None:
        return None
    targets = reply.get('targets')
    if not targets:
        if S.get(fb)['targets'] != ['fabric']:
            return None
        targets = [{'kind': 'category', 'ref': 'fabric'}]
    try:
        cand = dict(out, status='resolved', skill_id=fb,
                    outcome=str(reply.get('outcome') or text)[:300],
                    targets=targets,
                    params=reply['params'] if isinstance(reply.get('params'), dict) else {},
                    confidence=0.6,
                    ambiguities=['deterministic catalog match after model abstention'])
        S.resolve(fb, cand['params'])
        if I.validate_intent(cand):
            return None
        return cand
    except (S.SkillError, ValueError, TypeError, AttributeError):
        return None


# Skills that act on one fixed kind of device must be asked about that device. A request that never names it
# ("sors les poubelles" -> empty the vacuum's dust bin) is the model hesitating: OpenBridge asks before going on.
# Typos are tolerated (similarity >= 0.8 on words of 4+ letters); measured on the training generator, 99.8 % of the
# vacuum requests and 99.3 % of the TV requests still go straight through.
_DEVICE_WORDS = {
    'vacuum': ('aspirateur', 'aspi', 'robot', 'robots', 'vacuum', 'hoover', 'roomba', 'menage', 'nettoyage', 'nettoie',
               'nettoyer', 'clean', 'cleaning', 'poussiere', 'dust', 'dustbin', 'bac', 'base', 'dock', 'charge', 'recharge',
               'recharger', 'charger', 'balai', 'sol', 'floor', 'floors', 'autovidage', 'selfempty'),
    'tv': ('tv', 'tele', 'teles', 'television', 'televiseur', 'telly', 'ecran', 'screen', 'volume', 'son', 'sound',
           'youtube', 'netflix', 'prime', 'disney', 'spotify', 'twitch', 'plex', 'vlc', 'kodi', 'canal', 'mycanal', 'app',
           'appli', 'application', 'louder', 'plus', 'moins', 'fort'),
}
_DEVICE_NAMES = {'vacuum': ('le robot aspirateur', 'the robot vacuum'), 'tv': ('la télé', 'the TV')}


def _skill_family(sid):
    if sid.startswith('vacuum.'):
        return 'vacuum'
    if sid.startswith(('tv_', 'app_')):
        return 'tv'
    return None


def mentions_device(family, text):
    import difflib
    from src.ai.voice_normalize import fold
    toks = fold(text).split()
    words = _DEVICE_WORDS[family]
    for t in toks + [a + b for a, b in zip(toks, toks[1:])]:
        for w in words:
            if t == w or (len(w) >= 4 and len(t) >= 4 and difflib.SequenceMatcher(None, t, w).ratio() >= 0.8):
                return True
    return False


def _hesitation_guard(resolved):
    """A resolved fixed-device skill whose request never names the device becomes a question, never an action.

    Fresh requests only: a follow-up ("pause it") takes its device from the conversation (nl_followup)."""
    if resolved.get('status') != 'resolved':
        return resolved
    fam = _skill_family(resolved.get('skill_id') or '')
    if fam is None or mentions_device(fam, resolved.get('raw_text') or ''):
        return resolved
    fr = resolved.get('lang') == 'fr'
    name = _DEVICE_NAMES[fam][0 if fr else 1]
    q = ('Vous parlez de %s ? Votre demande ne le mentionne pas : dites-le pour que je continue.' % name) if fr \
        else ('Do you mean %s? Your request does not mention it: say so and I will go on.' % name)
    return dict(resolved, status='needs_clarification', clarifying_question=q,
                ambiguities=['device not mentioned: %s (model proposed %s)' % (fam, resolved['skill_id'])])


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
            amb = reply['ambiguities'] if isinstance(reply['ambiguities'], list) else []
            return dict(doc, status='needs_clarification',
                        clarifying_question=str(reply['clarifying_question'])[:300],
                        ambiguities=[str(a)[:200] for a in amb][:8])
        return dict(doc, status='unsupported',
                    ambiguities=['no registered skill matches'])
    if S.get(sid) is None:
        return dict(doc, status='unsupported',
                    ambiguities=[f'model proposed unknown skill {sid}'])
    conf = reply['confidence']
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) or conf < MIN_CONFIDENCE:
        return dict(doc, status='escalation_required',
                    ambiguities=['model confidence below 0.5'])
    tg, amb = reply['targets'], reply['ambiguities']
    if not isinstance(tg, list) or len(tg) > 8 or not isinstance(amb, list):
        return dict(doc, status='escalation_required',
                    ambiguities=['model reply shape invalid'])
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


class CustomIntentTransport:
    """Strict NL-parse transport over the owner's connected provider.

    The provider must have been connected by hand (registry check on every call). Replies must
    be a single JSON object; anything else becomes TransportError (-> escalation_required).
    Provider-reported token usage, when present, is kept on self.last_usage for receipts.
    """

    def __init__(self, entry, send=None, vault=None, providers_path=None):
        from src.ai import custom_provider
        self.entry = entry
        self.execution = custom_provider.execution(entry)
        self._t = custom_provider.ProviderTransport(entry, send=send, vault=vault)
        self.model_id, self.endpoint = self._t.model_id, self._t.endpoint
        self._providers_path = providers_path
        self.last_usage = None

    def ready(self):
        return True

    def __call__(self, prompt):
        from src.ai import custom_provider, registry
        try:
            registry.require(self.model_id, self.endpoint, providers_path=self._providers_path)
        except registry.RegistryInvalid as e:
            raise TransportError(str(e)) from None
        try:
            out, raw = self._t.chat_json(prompt)
        except custom_provider.ProviderError as e:
            raise TransportError('connected provider: %s' % e) from None
        usage = raw.get('usage') if isinstance(raw, dict) else None
        self.last_usage = {'usage': dict(usage), 'provider': self.entry['name']} \
            if isinstance(usage, dict) else {'provider': self.entry['name']}
        return out


def parse(text, lang, quality, local_transport, cloud_transport=None,
          medium_transport=None, cloud_allowed=False, before_cloud=None):
    doc = I.new_intent(text, lang)
    if quality not in ('low', 'medium', 'high', 'auto'):
        raise ValueError('quality must be low|medium|high|auto')
    prompt = build_prompt(text, lang)
    plan = {'low': [('low', local_transport, 'local')],
            'medium': [('medium', medium_transport, 'local')],
            'high': [('high', cloud_transport, 'cloud')],
            'auto': [('low', local_transport, 'local'),
                     ('medium', medium_transport, 'local')] if medium_transport
            else [('low', local_transport, 'local')]}[quality]
    skip = object()
    cloud_sent = [False]   # at most ONE send to the connected provider per parse

    def gated(tier, transport, parser):
        if transport is None:
            return skip
        if parser == 'cloud':
            cloud_sent[0] = True
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
        out = _hesitation_guard(_interpret(doc, reply, parser, getattr(transport, 'answered_by', None)
                                           or (TIERS[tier][0] if tier in TIERS else getattr(transport, 'model_id', None))))
        if out['status'] == 'unsupported' and 'no registered skill matches' in out['ambiguities']:
            cand = _fallback_candidate(text, reply, out)
            if cand is not None:
                return cand
        if out['status'] in ('resolved', 'unsupported', 'needs_clarification'):
            return out
        doc = out
    if quality in ('high', 'auto') and cloud_sent[0]:
        # The plan already spent its single connected-provider attempt; never send again.
        return dict(doc, status='escalation_required',
                    ambiguities=list(doc.get('ambiguities') or []) + ['cloud reply was not usable; not retried'])
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
                out = _hesitation_guard(_interpret(doc, reply, 'cloud', getattr(cloud_transport, 'model_id', None)))
                if out['status'] == 'unsupported' and 'no registered skill matches' in out['ambiguities']:
                    cand = _fallback_candidate(text, reply, out)
                    if cand is not None:
                        return cand
                if out['status'] in ('resolved', 'unsupported', 'needs_clarification'):
                    return out
                doc = out
        else:
            return dict(doc, status='escalation_required',
                        ambiguities=list(doc.get('ambiguities') or [])
                        + ['the connected AI needs explicit authorization (or none is connected)'])
    if doc['status'] == 'draft':
        doc = dict(doc, status='escalation_required',
                   ambiguities=['all local tiers failed'])
    return doc
