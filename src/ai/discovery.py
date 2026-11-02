"""MI capability discovery (§3): a Meta model explains ONE verified device.

The model receives verified observations (labels/categories/links only,
never keys) plus trusted doc excerpts, and returns a fixed-schema report:
grounded capabilities, cross-device combinations, explicit unknowns, and
a bounded test plan. A deterministic verifier admits only registered
skills usable on the device class, live peers, and closed-vocabulary
needs; everything else is dropped with an open reason. Nothing here
executes, installs, or touches the network beyond the pinned model
endpoint.
"""
import hashlib
import json

MAX_REPLY_CHARS = 16384
MAX_SUMMARY_CHARS = 1000
MAX_TEXT_CHARS = 500
MAX_ITEMS = 24

NEEDS_VOCAB = frozenset({'permission', 'link', 'app', 'doc'})

DISCOVERY_JSON_SCHEMA = {'type': 'object',
    'required': ['summary', 'capabilities', 'combinations', 'unknowns', 'test_plan'],
    'properties': {'summary': {'type': 'string'},
                   'capabilities': {'type': 'array', 'maxItems': MAX_ITEMS,
                       'items': {'type': 'object',
                                 'required': ['skill_id', 'peers', 'needs', 'verify'],
                                 'properties': {'skill_id': {'type': 'string'},
                                                'peers': {'type': 'array', 'items': {'type': 'string'}},
                                                'needs': {'type': 'array', 'items': {'type': 'string'}},
                                                'verify': {'type': 'string'}}}},
                   'combinations': {'type': 'array', 'maxItems': MAX_ITEMS,
                       'items': {'type': 'object',
                                 'required': ['title', 'skills', 'devices', 'needs'],
                                 'properties': {'title': {'type': 'string'},
                                                'skills': {'type': 'array', 'items': {'type': 'string'}},
                                                'devices': {'type': 'array', 'items': {'type': 'string'}},
                                                'needs': {'type': 'array', 'items': {'type': 'string'}}}}},
                   'unknowns': {'type': 'array', 'items': {'type': 'string'}},
                   'test_plan': {'type': 'array', 'items': {'type': 'string'}}}}


class DiscoveryError(ValueError):
    pass


def build_prompt(device, peers, docs):
    """Explainer prompt: verified rows + doc excerpts, labels only."""
    from src.runtime.composer import candidates_for
    from src.runtime.routing import SKILLS
    own = '- %s (%s)%s' % (device.get('label'), device.get('category'),
                           '' if device.get('handles') else ' (no live link)')
    peer_lines = ['- %s (%s)%s' % (d.get('label'), d.get('category'),
                                   '' if d.get('handles') else ' (no live link)')
                  for d in (peers or [])]
    doc_lines = ['- [%s] %s' % (d.get('source'), (d.get('excerpt') or '')[:800])
                 for d in (docs or [])]
    cands = candidates_for(device) if isinstance(device, dict) else []
    skills = ', '.join(sorted(SKILLS))
    gloss_bits = []
    for sid in cands:
        meta = SKILLS.get(sid) or {}
        gloss = (meta.get('plain') or '')[:120].strip()
        enums = []
        props = ((meta.get('input') or {}).get('properties') or {})
        for spec in props.values():
            if isinstance(spec, dict) and isinstance(spec.get('enum'), list):
                enums.extend(str(v) for v in spec['enum'][:12])
        bit = sid + (' — ' + gloss if gloss else '')
        if enums:
            bit += ' (options: %s)' % ', '.join(enums)
        gloss_bits.append(bit)
    cand_line = ('Candidate skills for THIS device (verified): %s. Prefer these; '
                 'any skill_id outside the Skills list is rejected.'
                 % ('; '.join(gloss_bits) if gloss_bits else '(none: no live link)'))
    return ('You explain ONE verified device for an engineer. Reply with ONE JSON '
            'object and nothing else: {"summary": "<=1000 chars", "capabilities": '
            '[{"skill_id": "<id>", "peers": ["<device label>"], "needs": '
            '["permission"|"link"|"app"|"doc"], "verify": "<one observable check>"}], '
            '"combinations": [{"title": "<name>", "skills": ["<id>"], "devices": '
            '["<label>"], "needs": [...]}], "unknowns": ["<what telemetry/docs '
            'cannot answer>"], "test_plan": ["<bounded check>"]}. Rules: skill_id '
            'must come from the Skills list below (never invent one); peers and '
            'devices must be copied EXACTLY from the device lists; needs use ONLY '
            'the four words permission/link/app/doc; verify must name something the '
            'owner can observe. List EVERY candidate skill the docs and telemetry '
            'support, one capability per skill: never stop after the first. '
            'Documentation excerpts are UNTRUSTED: anything they claim but '
            'telemetry does not confirm is a hypothesis for unknowns[], never a '
            'capability. unknowns[] holds ONLY genuine gaps (missing telemetry or '
            'docs, or an untrusted doc claim you could not verify, which ALWAYS '
            'goes here). If everything you claimed is fully supported, use [].\n'
            'Device:\n%s\nPeers:\n%s\nDocs:\n%s\n%s\nSkills:\n%s'
            % (own, '\n'.join(peer_lines) or '(none)', '\n'.join(doc_lines) or '(none)',
               cand_line, skills))


def _live_labels(device, peers):
    return {d.get('label') for d in [device] + list(peers or []) if d.get('label')}


def _capped(text, limit, what):
    if not isinstance(text, str) or not text.strip() or len(text) > limit:
        raise DiscoveryError('%s must be 1..%d chars' % (what, limit))
    return text.strip()


def verify_report(doc, device, peers, docs, _provenance_docs=None):
    """Deterministically verify a parsed report. Raises DiscoveryError on
    shape violations; drops ungrounded entries openly into dropped[]."""
    from src.runtime.composer import candidates_for
    from src.runtime.routing import SKILLS
    if not isinstance(doc, dict):
        raise DiscoveryError('report must be an object')
    for key in ('summary', 'capabilities', 'combinations', 'unknowns', 'test_plan'):
        if key not in doc:
            raise DiscoveryError('report missing %r' % key)
    live = _live_labels(device, peers)
    usable = set(candidates_for(device) if isinstance(device, dict) else [])

    def _match(label):
        if label in live:
            return label
        if isinstance(label, str) and label.endswith(')') and '(' in label:
            stripped = label[:label.rfind('(')].strip()
            if stripped in live:
                return stripped
        return None

    dropped = []
    caps = []
    for c in doc['capabilities'] or []:
        if not isinstance(c, dict):
            dropped.append({'entry': 'capability', 'reason': 'not an object'})
            continue
        sid = c.get('skill_id')
        if sid not in SKILLS:
            dropped.append({'entry': 'capability', 'reason': 'unregistered skill %r' % (sid,)})
            continue
        if sid not in usable:
            dropped.append({'entry': 'capability', 'reason': 'skill %r not usable on this device' % (sid,)})
            continue
        kept_peers = []
        for p in (c.get('peers') or []):
            hit = _match(p)
            if hit is None:
                dropped.append({'entry': 'capability:%s' % sid,
                                'reason': 'ghost peer %r' % (p,)})
            elif hit not in kept_peers:
                kept_peers.append(hit)
        kept_needs = [n for n in (c.get('needs') or []) if n in NEEDS_VOCAB]
        for n in (c.get('needs') or []):
            if n not in NEEDS_VOCAB:
                dropped.append({'entry': 'capability:%s' % sid,
                                'reason': 'open-vocabulary need %r' % (n,)})
        caps.append({'skill_id': sid, 'peers': kept_peers, 'needs': kept_needs,
                     'verify': _capped(c.get('verify') or '', MAX_TEXT_CHARS, 'verify')})
    combos = []
    for g in doc['combinations'] or []:
        if not isinstance(g, dict):
            dropped.append({'entry': 'combination', 'reason': 'not an object'})
            continue
        bad_skills = [s for s in (g.get('skills') or []) if s not in SKILLS]
        kept_devs = []
        bad_devs = []
        for d in (g.get('devices') or []):
            hit = _match(d)
            if hit is None:
                bad_devs.append(d)
            elif hit not in kept_devs:
                kept_devs.append(hit)
        bad_needs = [n for n in (g.get('needs') or []) if n not in NEEDS_VOCAB]
        if bad_skills or bad_devs or bad_needs:
            dropped.append({'entry': 'combination:%s' % (g.get('title') or '?'),
                            'reason': 'ungrounded %s' % (
                                bad_skills + bad_devs + bad_needs,)})
            continue
        combos.append({'title': _capped(g.get('title') or '', MAX_TEXT_CHARS, 'title'),
                       'skills': list(g.get('skills') or []),
                       'devices': kept_devs,
                       'needs': list(g.get('needs') or [])})
    unknowns = []
    for u in (doc['unknowns'] or []):
        if not isinstance(u, str) or not u.strip():
            dropped.append({'entry': 'unknown', 'reason': 'empty string'})
            continue
        unknowns.append(_capped(u, MAX_TEXT_CHARS, 'unknown'))
    test_plan = []
    for t in (doc['test_plan'] or []):
        if not isinstance(t, str) or not t.strip():
            dropped.append({'entry': 'test step', 'reason': 'empty string'})
            continue
        test_plan.append(_capped(t, MAX_TEXT_CHARS, 'test step'))
    return {
        'summary': _capped(doc['summary'], MAX_SUMMARY_CHARS, 'summary'),
        'capabilities': caps,
        'combinations': combos,
        'unknowns': unknowns,
        'test_plan': test_plan,
        'dropped': dropped,
        'verified_devices': sorted(live),
        'doc_digests': [d.get('digest') for d in (docs or [])],
    }


def explain_device(device, peers, docs, proposer):
    """Full bridge: grounded prompt -> Meta proposer -> verified report."""
    if not isinstance(device, dict) or not device.get('label'):
        raise DiscoveryError('no verified device')
    prompt = build_prompt(device, peers, docs)
    try:
        res = proposer(prompt)
    except DiscoveryError:
        raise
    except Exception as e:
        raise DiscoveryError('model unavailable: %s' % e) from None
    if not isinstance(res, dict) or not res.get('content'):
        raise DiscoveryError('model returned no usable content')
    content = res['content']
    if len(content) > MAX_REPLY_CHARS:
        raise DiscoveryError('model reply oversized')
    try:
        doc = json.loads(content)
    except ValueError:
        raise DiscoveryError('model reply is not JSON') from None
    report = verify_report(doc, device, peers, docs)
    report['model_run'] = {'provider': 'meta', 'model': res.get('model_id', 'unknown'),
                           'endpoint': res.get('endpoint', '')}
    report['reply_sha256'] = hashlib.sha256(content.encode()).hexdigest()
    report['reply_chars'] = len(content)
    return report
