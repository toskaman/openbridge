"""PR78 default and explicit-override credit probes. Temporary ledgers only."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

HEAD = '42416d6cb17010f16d39647d8d8dc6a8583f4322'


def run():
    module = types.ModuleType('review_shared_credit')
    sys.modules[module.__name__] = module
    source = subprocess.check_output(['git', 'show', HEAD+':src/ai/broker.py'], text=True, encoding='utf-8')
    exec(compile(source, HEAD+':broker.py', 'exec'), module.__dict__)
    permit = module.CreditPermit(observation_id='same-observation',
        verified_at=datetime.now(timezone.utc)-timedelta(seconds=600),
        free_balance_usd=139.8, session_budget_usd=.20)
    results = {}
    with tempfile.TemporaryDirectory(prefix='ob-credit-review-') as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
        for mode in ('canonical_default', 'explicit_override'):
            count, refusals, paths = 0, 0, []
            for output in ('out-a', 'out-b'):
                ledger = module.resolve_ledger(None if mode == 'canonical_default' else Path(directory)/output/'budget.sqlite3')
                paths.append(str(ledger.relative_to(directory)))
                broker = module.RuntimeModelBroker(ledger, permit, evaluation_allowance_usd=.80, evaluation_authz='same-authz')
                for _ in range(8):
                    try:
                        broker._reserve()
                        count += 1
                    except module.ModelBlocked:
                        refusals += 1
            results[mode] = {'accepted': count, 'refused': refusals, 'reserved_usd': count*.1,
                             'authorized_allowance_usd': .80, 'relative_paths': paths,
                             'cap_enforced': count <= 8}
    return {'head': HEAD, 'results': results, 'actual_provider_calls': 0,
            'actual_hardware_calls': 0, 'actual_spend_usd': 0,
            'verdict': 'Default output-independent cap fixed; arbitrary explicit live ledger override remains unguarded.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Never overwrite receipts')
    report = run()
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        json.dump(report, file, indent=2)
        file.write('\n')
    print(json.dumps(report, indent=2))
    return 0 if report['results']['canonical_default']['cap_enforced'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
