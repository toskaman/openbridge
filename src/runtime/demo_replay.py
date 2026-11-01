"""Campaign Three §5.6 + judge-C W3: scripted UI replay of the S5/S5b receipts.

The replay bundle (docs/evidence/demo-replay-s5-s5b.json) carries verbatim
receipt data from the tracked S5/S5b proof docs. Playback is SIMULATED: it
touches no live hardware, issues no model call, and fabricates no footage.
Every replayed step shows the §5.6 chain:

  intent -> model -> proposal -> validation -> consent -> publish
    -> action -> verify -> revoke
"""
import json
from pathlib import Path

BUNDLE_REL = Path('docs') / 'evidence' / 'demo-replay-s5-s5b.json'
MAX_BUNDLE_BYTES = 65536

BUNDLE_ID = 'demo-replay-s5-s5b'
EVIDENCE_KIND = 'RECORDED_REAL_HARDWARE_RECEIPTS'
PLAYBACK = 'SIMULATED'

STAGES = ('intent', 'model', 'proposal', 'validation', 'consent',
          'publish', 'action', 'verify', 'revoke')

REPLAY_LABEL = 'REPLAY'
SIMULATED_LABEL = 'SIMULATED'


class ReplayError(ValueError):
    pass


def bundle_path():
    return Path(__file__).resolve().parents[2] / BUNDLE_REL


def load_bundle(path=None):
    """Load and validate the replay bundle. Raises ReplayError on any defect."""
    target = Path(path) if path is not None else bundle_path()
    try:
        if target.stat().st_size > MAX_BUNDLE_BYTES:
            raise ReplayError('Oversized replay bundle')
        raw = target.read_text(encoding='utf-8-sig')
    except OSError as error:
        raise ReplayError('Replay bundle unavailable') from error
    try:
        bundle = json.loads(raw)
    except ValueError as error:
        raise ReplayError('Replay bundle is not valid JSON') from error
    return validate_bundle(bundle)


def validate_bundle(bundle):
    if not isinstance(bundle, dict):
        raise ReplayError('Replay bundle must be an object')
    if bundle.get('bundle_id') != BUNDLE_ID:
        raise ReplayError('Invalid replay bundle identity')
    if bundle.get('evidence_kind') != EVIDENCE_KIND:
        raise ReplayError('Invalid replay evidence kind')
    if bundle.get('live_request') is not False:
        raise ReplayError('Replay bundle must declare live_request=false')
    if bundle.get('playback') != PLAYBACK:
        raise ReplayError('Replay bundle must declare SIMULATED playback')
    if list(bundle.get('stages_order') or []) != list(STAGES):
        raise ReplayError('Replay bundle must carry the 9-stage §5.6 chain')
    scenarios = bundle.get('scenarios')
    if not isinstance(scenarios, list) or len(scenarios) != 2:
        raise ReplayError('Replay bundle must carry exactly the S5 + S5b scenarios')
    seen = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ReplayError('Scenario must be an object')
        sid = scenario.get('scenario_id')
        if not sid or sid in seen:
            raise ReplayError('Scenario ids must be unique and non-empty')
        seen.add(sid)
        for key in ('title', 'verdict', 'honest_limits'):
            if not scenario.get(key):
                raise ReplayError('Scenario %r misses %r' % (sid, key))
        stages = scenario.get('stages')
        if not isinstance(stages, dict) or set(stages) != set(STAGES):
            raise ReplayError('Scenario %r must carry all 9 stages' % (sid,))
        for stage_id in STAGES:
            stage = stages[stage_id]
            if not isinstance(stage, dict):
                raise ReplayError('Stage %r of %r must be an object' % (stage_id, sid))
            if not stage.get('title') or not stage.get('source'):
                raise ReplayError('Stage %r of %r needs title + source' % (stage_id, sid))
            facts = stage.get('facts')
            if not isinstance(facts, list) or not facts:
                raise ReplayError('Stage %r of %r needs facts' % (stage_id, sid))
            for fact in facts:
                if (not isinstance(fact, list) or len(fact) != 2
                        or not all(isinstance(v, str) and v for v in fact)):
                    raise ReplayError('Stage %r of %r has a malformed fact' % (stage_id, sid))
    return bundle


def serve_bundle(path=None):
    """Read-only API payload for GET /api/demo-replay. Returns (code, body)."""
    try:
        bundle = load_bundle(path)
    except ReplayError as error:
        return 404, {'error': 'No verified demo replay available: %s' % error}
    return 200, {'evidence_kind': EVIDENCE_KIND, 'live_request': False,
                 'playback': PLAYBACK, 'bundle': bundle}
