"""PR85 offline audio-oracle parser/registry review. Never executes hardware driver."""
import argparse
import hashlib
import io
import json
import subprocess
import sys
import types
import unittest
from pathlib import Path

HEAD = '089c39f3803fc1a25a40ed6b719b04ad6789d4ad'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Never overwrite receipts')
    hashes = {}
    def raw(path):
        data = subprocess.check_output(['git', 'show', HEAD+':'+path])
        hashes[path] = hashlib.sha256(data).hexdigest()
        return data
    import src.fabric
    for name, path in [('src.fabric.android_actions','src/fabric/android_actions.py'),
                       ('review_audio_registry','src/substrate/registry.py')]:
        module = types.ModuleType(name)
        module.__package__ = name.rpartition('.')[0]
        sys.modules[name] = module
        if name.startswith('src.fabric.'):
            src.fabric.android_actions = module
        exec(compile(raw(path), path, 'exec'), module.__dict__)
    package = types.ModuleType('src.substrate')
    package.__path__ = []
    sys.modules['src.substrate'] = package
    sys.modules['src.substrate.registry'] = sys.modules['review_audio_registry']
    tests = types.ModuleType('review_audio_tests')
    exec(compile(raw('tests/fabric/test_audio_state.py'), 'PR85/tests', 'exec'), tests.__dict__)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    checks = {}
    for label, dump in [('missing_music','- STREAM_ALARM:\n Muted: true\n'),
                        ('unknown_muted','- STREAM_MUSIC:\n Muted: UNKNOWN\n'),
                        ('neighbour_muted','- STREAM_MUSIC:\n Max: 15\n- STREAM_ALARM:\n Muted: true\n')]:
        value = src.fabric.android_actions.AndroidActions(lambda *args:dump, 'tv').audio_state()
        checks[label] = value['muted'] is None and value['readable'] is False
    transcript = json.loads(raw('docs/evidence/v4/HW_STATE_AUDIO_TRANSCRIPT.json'))
    reads = [step['result'] for step in transcript['steps'] if step['action']=='audio_state']
    report = {'head': HEAD, 'source_sha256': hashes, 'tests_run': result.testsRun,
              'test_success': result.wasSuccessful(), 'test_output': log.getvalue(),
              'unknown_format_checks': checks, 'contributor_reported_mute_volume': [[r['muted'],r['volume_index']] for r in reads],
              'reported_initial_final_read_equal': reads[0] == reads[-1],
              'physical_result_independently_observed': False, 'actual_provider_calls': 0,
              'actual_hardware_calls': 0, 'actual_spend_usd': 0,
              'scope': 'Parser/registry tests and transcript consistency only; hardware driver never imported/executed.'}
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(log.getvalue())
    print(json.dumps(checks))
    return 0 if result.wasSuccessful() and all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
