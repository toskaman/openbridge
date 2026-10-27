"""One supervised synthetic Spark diagnostic. Credential enters through stdin, never arguments/logs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from src.ai.broker import CreditPermit, MetaTransport, ModelBlocked
from src.forge.spark_diagnostic import SparkDiagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observed-at', required=True)
    parser.add_argument('--free-credits', required=True, type=float)
    parser.add_argument('--observation-id', required=True)
    args = parser.parse_args()
    try:
        observed = datetime.fromisoformat(args.observed_at)
        if observed.tzinfo is None or not 0 <= (datetime.now(timezone.utc)-observed).total_seconds() <= 300:
            raise ModelBlocked('Fresh promotional-credit verification required')
        key = sys.stdin.readline().strip()
        if not key.startswith('LLM_'): raise ModelBlocked('Credential unavailable')
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share'))) / 'OpenBridge'
        result = SparkDiagnostic(root/'runtime-budget.sqlite', CreditPermit(args.observation_id, observed, args.free_credits, .10), MetaTransport(key)).diagnose('blocked_relay')
        result['recorded_at_utc'] = datetime.now(timezone.utc).isoformat()
        result['credit_verification'] = 'Participant-confirmed promotional balance; supervised single request'
        print(json.dumps(result)); return 0
    except ModelBlocked as error:
        print(json.dumps({'status': 'BLOCKED', 'detail': str(error), 'automatic_retry': False})); return 1
    except (ValueError, OSError):
        print(json.dumps({'status': 'BLOCKED', 'detail': 'Diagnostic not confirmed; no retry. Check credit observation and retained reservation.'})); return 1


if __name__ == '__main__': raise SystemExit(main())
