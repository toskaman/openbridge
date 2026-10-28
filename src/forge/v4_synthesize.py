"""V4 MetaCapabilitySynthesizer: frozen prompt, strict candidate validation."""
import json
import secrets

from src.forge import v4_schemas as S

PROMPT_VERSION = 'v4-synth-1'
CANDIDATE_KEYS = {'schema_version', 'candidate_id', 'origin', 'intent', 'target_opaque_id',
                  'primitive_chain', 'preconditions', 'postconditions', 'required_grants',
                  'evidence_refs', 'model_run_id'}


class SynthError(ValueError):
    pass


def build_prompt(bundle, intent_text, primitive_ids, target_category):
    return ('SYNTH_PROMPT %s. Intent: %s. Target category: %s. Primitives: %s. '
            'Evidence bundle digest: %s. Reply with exactly one JSON CapabilityCandidate '
            '(no model_run_id field; host injects it). Every primitive_id must be listed. '
            'Every evidence_ref must come from the bundle.' % (
                PROMPT_VERSION, intent_text[:200], target_category, ','.join(sorted(primitive_ids)),
                S.digest(bundle)))


def validate_candidate(value, primitive_ids):
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
    if not isinstance(value['evidence_refs'], list) or not value['evidence_refs']:
        raise SynthError('EVIDENCE_REQUIRED')
    return value


def synthesize(client, tier, bundle, intent_text, primitive_ids, target_category):
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
        cand = validate_candidate(doc, primitive_ids)
    except SynthError as e:
        return (False, {'status': 'SCHEMA_REJECTED', 'reason': str(e)[:120]})
    cand['digest'] = S.digest({k: v for k, v in cand.items()})
    return (True, {'candidate': cand, 'prompt_version': PROMPT_VERSION,
                   'prompt_sha256': S.digest(prompt), 'usage': body.get('usage', {})})
