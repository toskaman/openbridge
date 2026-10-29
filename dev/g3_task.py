"""Sealed G3 task specs: commit (sha256) before the run, reveal at run time.

A spec fixes everything the owner consents to and everything the jury checks, independently of the
model: the intent text given to Meta, the ONLY effect steps allowed in the generated plan, an
independent oracle read through the Executor (not through the manifest), the expected oracle value,
and a deterministic owner-side restore. Sol commits sha256(canonical spec) in a PR before any run;
the runner refuses a spec whose hash differs, so the task cannot be chosen or edited after results.
"""
import hashlib
import json

KEYS = {'spec_version', 'task_id', 'intent', 'target_category', 'offer', 'allowed_effects', 'oracle', 'expect', 'restore'}
ORACLE_ACTIONS = {'audio_state', 'screen_state', 'get'}
RESTORE_MODES = {'reinvoke', 'owner_action'}
OWNER_RESTORE_ACTIONS = {'set', 'key', 'restore'}


class SpecError(ValueError):
    pass


def canonical(spec):
    return json.dumps(spec, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def spec_sha256(spec):
    return hashlib.sha256(canonical(spec)).hexdigest()


def validate(spec):
    if not isinstance(spec, dict) or set(spec) != KEYS or spec['spec_version'] != 1:
        raise SpecError('spec keys/version')
    if not isinstance(spec['intent'], str) or not 10 <= len(spec['intent']) <= 200:
        raise SpecError('intent must be 10-200 chars (it is what the model sees)')
    if not isinstance(spec['offer'], list) or not spec['offer'] or not all(isinstance(p, str) for p in spec['offer']):
        raise SpecError('offer must list primitive ids')
    eff = spec['allowed_effects']
    if not isinstance(eff, list) or not 1 <= len(eff) <= 3 or any(set(e) != {'primitive_id', 'args'} or not isinstance(e['args'], dict) for e in eff):
        raise SpecError('allowed_effects: 1-3 exact {primitive_id, args}')
    if any(e['primitive_id'] not in spec['offer'] for e in eff):
        raise SpecError('every allowed effect must be offered')
    o = spec['oracle']
    if set(o) != {'action', 'args', 'field'} or o['action'] not in ORACLE_ACTIONS or not isinstance(o['args'], dict):
        raise SpecError('oracle: {action in %s, args, field}' % sorted(ORACLE_ACTIONS))
    if set(spec['expect']) != {'value'}:
        raise SpecError('expect: {value}')
    r = spec['restore']
    if r.get('mode') not in RESTORE_MODES:
        raise SpecError('restore.mode')
    if r['mode'] == 'owner_action' and (set(r) != {'mode', 'action', 'args'} or r['action'] not in OWNER_RESTORE_ACTIONS):
        raise SpecError('owner_action restore: {mode, action in %s, args}' % sorted(OWNER_RESTORE_ACTIONS))
    return spec


def load(path, expected_sha256):
    with open(path, encoding='utf-8') as f:
        raw = json.loads(f.read())
    spec = validate(raw)
    got = spec_sha256(spec)
    if got != (expected_sha256 or '').lower():
        raise SpecError('spec sha256 %s does not match the committed %s' % (got, expected_sha256))
    return spec


def effect_binding(steps, catalog, spec):
    """The plan's non-READ steps must equal the spec's allowed effects exactly (same order)."""
    effects = [{'primitive_id': s.get('primitive_id'), 'args': s.get('args')} for s in steps
               if (catalog.get(s.get('primitive_id')) or {}).get('side_effect_class') != 'READ']
    if effects != spec['allowed_effects']:
        return 'plan effects %s differ from the sealed allowed effects' % json.dumps(effects)[:200]
    return None


def field(obs, spec):
    return (obs or {}).get(spec['oracle']['field'])


def readable(obs, spec):
    if spec['oracle']['action'] == 'audio_state':
        return bool((obs or {}).get('readable'))
    return field(obs, spec) is not None


def observed(mid, spec):
    return field(mid, spec) == spec['expect']['value']


def restore_args(spec, pre):
    """Owner-side restore args with '$pre' replaced by the pre-run oracle field value."""
    args = {k: (field(pre, spec) if v == '$pre' else v) for k, v in spec['restore']['args'].items()}
    return {'action': spec['restore']['action'], 'args': args}


def predicate(spec, pre, mid, post, act_ok, restore_ok, after_revoke_http):
    reasons = []
    if not readable(pre, spec):
        reasons.append('oracle unreadable before the run')
    elif field(pre, spec) == spec['expect']['value']:
        reasons.append('pre already equals the expected value (no-op scores no success)')
    if not act_ok:
        reasons.append('act invoke must be VERIFIED/EXECUTED')
    if not observed(mid, spec):
        reasons.append('post-act oracle must show %s=%r' % (spec['oracle']['field'], spec['expect']['value']))
    if not restore_ok:
        reasons.append('restore must succeed')
    if field(post, spec) != field(pre, spec):
        reasons.append('post-restore oracle field must equal the pre-run value')
    if after_revoke_http == 200:
        reasons.append('invoke after revoke must be refused')
    return (not reasons), reasons


MUTE_SMOKE = {'spec_version': 1, 'task_id': 'smoke-tv-mute',
              'intent': 'Mute the TV audio, then confirm by reading the media stream state that it reports muted.',
              'target_category': 'tv',
              'offer': ['input.key', 'state.audio', 'state.screen', 'state.read_setting', 'app.list', 'device.read_descriptor'],
              'allowed_effects': [{'primitive_id': 'input.key', 'args': {'key': 'mute'}}],
              'oracle': {'action': 'audio_state', 'args': {}, 'field': 'muted'}, 'expect': {'value': True},
              'restore': {'mode': 'reinvoke'}}
