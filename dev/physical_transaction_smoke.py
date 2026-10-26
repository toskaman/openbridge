"""Explicitly authorized single-phone screen-timeout change and exact restoration."""
import argparse
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from src.adapters.android import AndroidAdapter
from src.adapters.android_timeout import AndroidTimeoutSetting
from src.core.transactions import TransactionEngine, TransactionBlocked


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-owned-device',action='store_true')
    parser.add_argument('--recover-only',action='store_true')
    args=parser.parse_args()
    if not args.confirm_owned_device:
        raise SystemExit('Owner authorization flag required; no physical write attempted')
    adb=AndroidAdapter()
    devices=[d for d in adb.discover()['devices'] if d['state']=='device' and d['transport']=='USB']
    if len(devices)!=1:
        raise SystemExit('Exactly one authorized USB phone is required; no physical write attempted')
    adapter=AndroidTimeoutSetting(adb,devices[0]['id'])
    private_root=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share'))) / 'OpenBridge'
    journal=private_root/('physical-timeout-'+adapter.identity[-16:]+'.sqlite')
    engine=TransactionEngine(journal,adapter,allow_physical=True)
    status=engine.status()
    if status['active']:
        result=engine.revert(status['active']['id'])
        print(json.dumps({'status':result['state'],'mode':'RECOVERY_ONLY','new_change_attempted':False}))
        return
    if args.recover_only:
        print(json.dumps({'status':'NO_ACTIVE_TRANSACTION','new_change_attempted':False}))
        return
    if Path('docs/physical-transaction-attempt.json').exists() or Path('docs/physical-transaction-receipt.json').exists():
        raise SystemExit('Prior physical evidence exists. Review it before authorizing a new attempt; no automatic retry.')
    transaction_id='physical-'+uuid.uuid4().hex
    before=adapter.read_setting()
    target=60 if before!=60 else 30
    snapshot=engine.prepare(transaction_id,target,consent=True)
    started=time.monotonic()
    operation_failed=False
    applied=None
    observed=None
    try:
        applied=engine.apply(transaction_id)
        observed=adapter.read_setting()
    except TransactionBlocked:
        operation_failed=True
    finally:
        restored=engine.revert(transaction_id)
    after=adapter.read_setting()
    if operation_failed:
        print(json.dumps({'source':'ADB','status':'BLOCKED','original_preserved':after==before,
                          'journal_state':restored['state'],'physical_change_verified':False,
                          'automatic_retry':False}))
        raise SystemExit(1)
    if applied['state']!='VERIFIED' or observed!=target or restored['state']!='REVERTED' or after!=before:
        raise RuntimeError('Physical setting restoration was not independently verified')
    with closing(sqlite3.connect(journal)) as db:
        events=[row[0] for row in db.execute('SELECT state FROM events WHERE transaction_id=? ORDER BY sequence',(transaction_id,))]
    receipt={'source':'ADB','simulated':False,'scope':'One authorized owned USB phone; screen timeout only',
        'field':'screen_timeout_seconds','before':snapshot['before'],'proposed':target,
        'observed_after_apply':observed,'observed_after_undo':after,'final_state':restored['state'],
        'elapsed_ms':round((time.monotonic()-started)*1000),'recorded_at':datetime.now().astimezone().isoformat(),
        'events':events,'privacy':'Serial, build fingerprint, address and private content excluded',
        'limitation':'One controlled physical setting loop. No universal device or firmware compatibility claim.'}
    Path('docs/physical-transaction-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__':
    main()
