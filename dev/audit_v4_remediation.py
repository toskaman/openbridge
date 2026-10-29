"""Pinned before/after PR72 admission audit. No provider, hardware or key access."""
import argparse
import hashlib
import inspect
import json
import subprocess
from pathlib import Path

from dev import audit_v4_followup as original

BEFORE = '8a73b8f395ecf13a979f88fd93649cd3975b3f23'
AFTER = '366784fcbf039f18de26b3c7be60813eb70a76f6'


def run():
    # The old barrier requires both requests to reach compile. Correct replay
    # admission rejects the second before compile, so use bounded compile delay
    # on BOTH revisions. Actual kernel/schema/grant/fact checks remain intact.
    harness = inspect.getsource(original.probe_substrate_pr72)
    old = 'if n<2:barrier.wait(5)'
    if harness.count(old) != 1:
        raise RuntimeError('AUDIT_HARNESS_CHANGED')
    harness = harness.replace(old, 'if n<2:time.sleep(0.1)')
    results = {}
    for label, head in [('before', BEFORE), ('after', AFTER)]:
        scope = dict(vars(original))
        scope['SUBSTRATE_HEAD'] = head
        # git_json closes over the original module; bind the exact head here.
        scope['git_json'] = lambda path, ref=head: json.loads(subprocess.check_output(
            ['git', 'show', ref + ':' + path], cwd=original.ROOT))
        exec(compile(harness, 'audit_v4_remediation_probe.py', 'exec'), scope)
        results[label] = scope['probe_substrate_pr72']()
    b, a = results['before'], results['after']
    checks = {
        'old_duplicate_reproduced': b['same_operation_mock_effects'] == 2,
        'new_single_effect': a['same_operation_mock_effects'] == 1,
        'new_replay_rejected': len(a['errors']) == 1 and 'operation_id already used' in a['errors'][0],
        'old_fact_gaps_reproduced': b['current_provenance_downgrade_accepted'] and b['signed_unverified_fact_accepted'],
        'new_fact_gaps_rejected': not a['current_provenance_downgrade_accepted'] and not a['signed_unverified_fact_accepted'],
    }
    return {'results': results, 'checks': checks,
            'harness_sha256': hashlib.sha256(harness.encode()).hexdigest(),
            'scope': 'Real invoke/schema/signatures/fact checks; mocked compile, device lookup and effects; two concurrent callers with bounded compile delay. Narrow findings S4/S5 only.',
            'release_gate': 'BLOCKED: other findings and acceptance gates remain open',
            'actual_provider_calls': 0, 'actual_hardware_calls': 0, 'actual_spend_usd': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Never overwrite audit receipts')
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(result, file, indent=2)
        file.write('\n')
    print(json.dumps(result, indent=2))
    return 0 if all(result['checks'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
