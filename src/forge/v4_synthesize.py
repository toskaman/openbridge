"""V4 MetaCapabilitySynthesizer: frozen prompt, strict candidate validation."""
import json
import secrets

from src.forge import v4_schemas as S

PROMPT_VERSION = 'v4-synth-2'
CANDIDATE_KEYS = {'schema_version', 'candidate_id', 'origin', 'intent', 'target_opaque_id',
                  'primitive_chain', 'preconditions', 'postconditions', 'required_grants',
                  'evidence_refs', 'model_run_id'}
MAX_PROJECTION_DEVICES = 8
MAX_PROJECTION_FACTS = 64
GRANT_SCOPE = {'read', 'observe', 'control'}


class SynthError(ValueError):
    pass


def evidence_projection(bundle, target_category):
    """Bounded, value-free projection: opaque ids + fact descriptors the model may cite."""
    lines, n = [], 0
    for d in bundle['devices'][:MAX_PROJECTION_DEVICES]:
        if d['category'] != target_category:
            continue
        lines.append('device %s scope=%s' % (d['opaque_id'], ','.join(d['permission_scope'])))
        for f in d['facts']:
            if n >= MAX_PROJECTION_FACTS:
                lines.append('TRUNCATED: more facts exist; cite only listed refs')
                return '\n'.join(lines)
            lines.append('  fact %s kind=%s class=%s source=%s' % (
                f['evidence_ref'], f['kind'], f['value_class'], f['source']))
            n += 1
    if len(bundle['devices']) > MAX_PROJECTION_DEVICES:
        lines.append('TRUNCATED: more devices exist')
    return '\n'.join(lines)


def build_prompt(bundle, intent_text, primitive_ids, target_category):
    return ('SYNTH_PROMPT %s. Intent: %s. Target category: %s. Primitives: %s.\n'
            'Evidence projection (cite ONLY these refs, no others):\n%s\n'
            'Bundle digest: %s. Reply with exactly one JSON CapabilityCandidate '
            '(no model_run_id field; host injects it). Every primitive_id must be listed. '
            'target_opaque_id must be a device above.' % (
                PROMPT_VERSION, intent_text[:200], target_category, ','.join(sorted(primitive_ids)),
                evidence_projection(bundle, target_category), S.digest(bundle)))


def validate_candidate(value, primitive_ids, bundle=None, schemas=None, sources=None):
    if not isinstance(value, dict) or set(value) != CANDIDATE_KEYS:
        raise SynthError('SCHEMA_REJECTED')
    if value['schema_version'] != S.SCHEMA_VERSION or value['origin'] != 'meta_generated':
        raise SynthError('SCHEMA_REJECTED')
    chain = value['primitive_chain']
    if not isinstance(chain, list) or not chain:
        raise SynthError('EMPTY_CHAIN')
    for step in chain:
        if set(step) != {'primitive_id', 'input'} or not isinstance(step['input'], dict):
            raise SynthError('STEP_SHAPE')
        if step['primitive_id'] not in primitive_ids:
            raise SynthError('REJECTED_UNSUPPORTED_PRIMITIVE: %s' % (step['primitive_id'],))
        if schemas is not None and step['primitive_id'] in schemas:
            allowed = schemas[step['primitive_id']]
            if any(k not in allowed for k in step['input']):
                raise SynthError('UNDECLARED_INPUT')
            for k, v in step['input'].items():
                want = allowed[k]
                if want == 'string' and not isinstance(v, str):
                    raise SynthError('INPUT_TYPE')
    if not isinstance(value['evidence_refs'], list) or not value['evidence_refs']:
        raise SynthError('EVIDENCE_REQUIRED')
    grants = value['required_grants']
    if not isinstance(grants, list) or any(g not in GRANT_SCOPE for g in grants) or len(set(grants)) != len(grants):
        raise SynthError('GRANT_SCOPE')
    if bundle is not None:
        targets = [d for d in bundle['devices'] if d['opaque_id'] == value['target_opaque_id']]
        if not targets:
            raise SynthError('UNKNOWN_TARGET')
        scopes = set(targets[0].get('permission_scope', []))
        if any(g not in scopes for g in grants):
            raise SynthError('GRANT_NOT_IN_TARGET_SCOPE')
        known_refs = {f['evidence_ref'] for d in bundle['devices'] for f in d['facts']}
        allowed_src = set(sources or ())
        for r in value['evidence_refs']:
            if r in known_refs:
                continue
            if isinstance(r, str) and r.startswith('src:') and r in allowed_src:
                continue
            raise SynthError('INVENTED_EVIDENCE_REF')
    return value


def synthesize(client, tier, bundle, intent_text, primitive_ids, target_category,
               schemas=None, sources=None):
    """Propose a candidate only. This layer has no staging path: hosts must call
    v4_substrate.compile_first (trusted kernel) before anything is staged."""
    prompt = build_prompt(bundle, intent_text, primitive_ids, target_category)
    ok, body = client.generate(tier, prompt, {'max_s': 120})
    if not ok:
        return (False, body)
    try:
        doc = json.loads(body.get('text', ''))
    except (TypeError, ValueError):
        return (False, {'status': 'SCHEMA_REJECTED', 'reason': 'not JSON'})
    if not isinstance(doc, dict):
        return (False, {'status': 'SCHEMA_REJECTED', 'reason': 'not an object'})
    doc = dict(doc)
    doc['model_run_id'] = 'mr-' + secrets.token_hex(8)
    try:
        cand = validate_candidate(doc, primitive_ids, bundle=bundle, schemas=schemas,
                                  sources=sources)
    except SynthError as e:
        return (False, {'status': 'SCHEMA_REJECTED', 'reason': str(e)[:120]})
    cand['digest'] = S.digest({k: v for k, v in cand.items()})
    return (True, {'candidate': cand, 'prompt_version': PROMPT_VERSION,
                   'prompt_sha256': S.digest(prompt), 'usage': body.get('usage', {})})
