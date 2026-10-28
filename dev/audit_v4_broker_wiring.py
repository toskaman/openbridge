"""Pinned PR84 broker-factory and real-compiler regression battery; offline only."""
import argparse
import json
from pathlib import Path
from dev import audit_v4_compiler_integration as battery

HEAD = '08e9c81'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Never overwrite receipts')
    import subprocess
    battery.FORGE = subprocess.check_output(['git', 'rev-parse', HEAD], text=True).strip()
    report = battery.run()
    report['scope'] = ('Four real compiler tests and35 agent-layer tests, including real LocalMetaBroker '
                       'digest readiness with injected catalog/chat responses. No live model endpoint or hardware.')
    report['release_gate'] = 'BLOCKED: live credit override, fair unseen evaluation and physical acceptance remain'
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(report['test_output'])
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
