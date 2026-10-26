"""One supervised runtime-core call; reads credential from stdin, never logs it."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from src.ai.broker import RuntimeModelBroker, MetaTransport, CreditPermit, ModelBlocked
from src.adapters.simulated import discover


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observed-at',required=True)
    parser.add_argument('--free-credits',required=True,type=float)
    parser.add_argument('--observation-id',required=True)
    args=parser.parse_args()
    try:
        observed=datetime.fromisoformat(args.observed_at)
        if observed.tzinfo is None or not 0 <= (datetime.now(timezone.utc)-observed).total_seconds() <= 300:
            raise ModelBlocked('Credit observation expired; no provider call made')
        key=sys.stdin.readline().strip()
        if not key.startswith('LLM_'):
            raise ModelBlocked('Meta credential unavailable')
        private_root=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share'))) / 'OpenBridge'
        broker=RuntimeModelBroker(private_root/'runtime-budget.sqlite',
            CreditPermit(args.observation_id,observed,args.free_credits,0.10),MetaTransport(key))
        result=broker.recommend(discover()[0]['facts'])
        result['recorded_at_utc']=datetime.now(timezone.utc).isoformat()
        result['credit_verification']='Participant-confirmed promotional balance; supervised single request'
        print(json.dumps(result))
        return 0
    except (ValueError,OSError):
        print(json.dumps({'status':'BLOCKED','detail':'Supervised verification failed; no retry; inspect local budget and credit observation.'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
