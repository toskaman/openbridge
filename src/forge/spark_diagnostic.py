"""Opt-in hosted Meta diagnostic on fixed synthetic evidence; never executes a check."""
import hashlib
import json
import time
from src.ai.broker import RuntimeModelBroker, ModelBlocked, MODEL_ID, ENDPOINT
from src.ai.registry import require

LIMIT = 'Synthetic evidence only; hypotheses are not verified causes.'


def fixture():
    # No runtime/device input can enter this cloud-only experiment.
    return {'source': 'SIMULATED', 'goal': 'Explain why an inspectable device is not supplying fresh relay observations.',
            'evidence': {'usb': 'Phone inspection over USB succeeds.',
                         'wifi': 'TV transport is reachable over Wi-Fi; reachability does not grant relay access.',
                         'permission': 'TV relay readiness reports nearby-device permission unavailable; the exact Android dialog has not been inspected.',
                         'ble': 'No fresh BLE observation is available through the TV; an earlier phone relay observation is stale.'},
            'owner_checks': [
                {'id': 'inspect_permission', 'description': 'Owner reads the TV permission state on its own screen; no permission change is performed.', 'requires': []},
                {'id': 'review_relay', 'description': 'Owner reviews current relay readiness after inspecting the permission state; no scan is started.', 'requires': ['inspect_permission']},
                {'id': 'compare_phone', 'description': 'Owner compares the phone relay evidence age without treating stale evidence as current.', 'requires': []}]}


def text(value, limit=1200):
    if not isinstance(value, str) or not 20 <= len(value.strip()) <= limit:
        raise ModelBlocked('Diagnostic prose invalid')


def validate(proposal, case):
    if not isinstance(proposal, dict) or set(proposal) != {'summary', 'hypotheses', 'checks', 'uncertainty', 'authorizes_execution'}:
        raise ModelBlocked('Diagnostic schema invalid')
    if proposal['authorizes_execution'] is not False or proposal['uncertainty'] != LIMIT:
        raise ModelBlocked('Diagnostic must remain uncertain and advisory')
    text(proposal['summary'])
    evidence = set(case['evidence'])
    candidates = {c['id']: c for c in case['owner_checks']}
    def refs(row):
        values = row['evidence_refs']
        if not isinstance(values, list) or not 1 <= len(values) <= len(evidence) or any(not isinstance(v, str) or v not in evidence for v in values) or len(set(values)) != len(values):
            raise ModelBlocked('Diagnostic evidence references invalid')
    hypotheses = proposal['hypotheses']; checks = proposal['checks']
    if not isinstance(hypotheses, list) or not 1 <= len(hypotheses) <= 3 or not isinstance(checks, list) or not 1 <= len(checks) <= len(candidates):
        raise ModelBlocked('Diagnostic list bounds invalid')
    for row in hypotheses:
        if not isinstance(row, dict) or set(row) != {'explanation', 'evidence_refs'}: raise ModelBlocked('Hypothesis invalid')
        text(row['explanation']); refs(row)
    seen = set()
    for row in checks:
        if not isinstance(row, dict) or set(row) != {'id', 'reason', 'evidence_refs'}: raise ModelBlocked('Owner check invalid')
        key = row['id']
        if not isinstance(key, str) or key not in candidates or key in seen or not set(candidates[key]['requires']) <= seen:
            raise ModelBlocked('Owner check unknown, duplicate or out of order')
        seen.add(key); text(row['reason']); refs(row)
    return proposal


class SparkDiagnostic(RuntimeModelBroker):
    def diagnose(self, case_id):
        if not isinstance(case_id, str) or case_id != 'blocked_relay':
            raise ModelBlocked('Only the fixed synthetic diagnostic case is approved')
        require(MODEL_ID, ENDPOINT)
        if self.transport is None: raise ModelBlocked('Meta transport unavailable')
        case = fixture()
        payload = {'model': MODEL_ID, 'max_completion_tokens': 900, 'messages': [
            {'role': 'developer', 'content':
             'Return only compact JSON with exactly summary (string), hypotheses (1-3 objects with explanation and evidence_refs), '
             'checks (1-3 objects with id, reason, evidence_refs), uncertainty (exactly '+LIMIT+'), authorizes_execution (false). '
             'Each prose field must be 20-1200 characters. Connect evidence from multiple transports, distinguish observations from possible causes, '
             'and explain an ordered read-only owner investigation. Use only supplied evidence keys and owner check IDs; respect requires ordering. '
             'Do not invent observations, claim a confirmed cause, propose commands, grant permissions, or claim a completed repair. All evidence is synthetic.'},
            {'role': 'user', 'content': json.dumps(case, sort_keys=True)}]}
        self._reserve()  # Shared durable budget; failure consumes reservation; no retry.
        started = time.monotonic()
        try:
            response = self.transport(payload)
            if response.get('model') != MODEL_ID: raise ModelBlocked('Returned model identity not approved')
            usage = response['usage']
            for field in ('prompt_tokens', 'completion_tokens'):
                if type(usage[field]) is not int or not 0 <= usage[field] <= 100000: raise ModelBlocked('Invalid provider usage')
            estimate = (usage['prompt_tokens']*1.25 + usage['completion_tokens']*4.25)/1000000
            if estimate > .10: raise ModelBlocked('Usage exceeds conservative reservation')
            choice = response['choices'][0]; message = choice['message']
            if choice.get('finish_reason') != 'stop' or message.get('tool_calls') or message.get('function_call'):
                raise ModelBlocked('Incomplete or tool-bearing diagnostic refused')
            content = message['content']
            if not isinstance(content, str) or len(content) > 16000: raise ModelBlocked('Diagnostic output too large')
            proposal = validate(json.loads(content), case)
            return {'model_id': MODEL_ID, 'provider': 'Meta Model API', 'source': 'SIMULATED', 'case_id': case_id,
                    'authorizes_execution': False, 'proposal': proposal, 'usage': usage, 'request_id': response.get('id'),
                    'estimated_cost_usd': estimate, 'reserved_usd': .10,
                    'elapsed_ms': round((time.monotonic()-started)*1000),
                    'input_sha256': hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
                    'validation_scope': 'Schema, reference membership and check order; not semantic diagnostic correctness.'}
        except ModelBlocked: raise
        except Exception: raise ModelBlocked('Diagnostic failed; reservation retained; no automatic retry') from None
