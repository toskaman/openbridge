"""Explicitly authorized: disable then re-enable one allowlisted optional app (user 0) with exact verified restoration."""
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
from src.adapters.android_package import AndroidPackageState, DEFAULT, ENABLED, DISABLED, ALLOWED_PACKAGES
from src.core.transactions import TransactionEngine, TransactionBlocked

NAMES={DEFAULT:'default (enabled)',ENABLED:'enabled (explicit)',DISABLED:'disabled-user'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-owned-device',action='store_true')
    parser.add_argument('--package',required=True,choices=sorted(ALLOWED_PACKAGES))
    parser.add_argument('--recover-only',action='store_true')
    args=parser.parse_args()
    if not args.confirm_owned_device:
        raise SystemExit('Owner authorization flag required; no physical write attempted')
    adb=AndroidAdapter()
    devices=[d for d in adb.discover()['devices'] if d['state']=='device' and d['transport']=='USB']
    if len(devices)!=1:
        raise SystemExit('Exactly one authorized USB phone is required; no physical write attempted')
    adapter=AndroidPackageState(adb,devices[0]['id'],args.package)
    root=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'OpenBridge'
    journal=root/('physical-package-'+adapter.identity[-16:]+'.sqlite')
    engine=TransactionEngine(journal,adapter,allow_physical=True)
    status=engine.status()
    if status['active']:
        result=engine.revert(status['active']['id'])
        print(json.dumps({'status':result['state'],'mode':'RECOVERY_ONLY','new_change_attempted':False}));return
    if args.recover_only:
        print(json.dumps({'status':'NO_ACTIVE_TRANSACTION','new_change_attempted':False}));return
    before=adapter.read_setting()
    if before==DISABLED:
        raise SystemExit('Package is not currently enabled; refusing to change a state the owner chose')
    tid='package-'+uuid.uuid4().hex
    started=time.monotonic();failed=False;applied=observed=None
    engine.prepare(tid,DISABLED,consent=True)
    try:
        applied=engine.apply(tid);observed=adapter.read_setting()
    except TransactionBlocked:failed=True
    finally:restored=engine.revert(tid)
    after=adapter.read_setting()
    with closing(sqlite3.connect(journal)) as db:
        events=[r[0] for r in db.execute('SELECT state FROM events WHERE transaction_id=? ORDER BY sequence',(tid,))]
    receipt={'source':'ADB','simulated':False,'scope':'One authorized owned USB phone; one allowlisted optional app; Android user 0 only',
        'field':'package_enabled_state','package':args.package,'before':NAMES[before],'proposed':NAMES[DISABLED],
        'observed_after_apply':NAMES.get(observed),'observed_after_undo':NAMES.get(after),
        'outcome':'BLOCKED' if failed else 'VERIFIED_CHANGE_AND_UNDO','original_preserved':after==before,
        'final_state':restored['state'],'events':events,'elapsed_ms':round((time.monotonic()-started)*1000),
        'recorded_at':datetime.now().astimezone().isoformat(),
        'verification':'Each read re-checks USB authorization and build identity, then requires the exact dumpsys user-0 enabled code to agree with pm list -e and -d.',
        'privacy':'Serial, build fingerprint, address and private content excluded',
        'limitation':'One controlled reversible app-state loop. App data is preserved by disable-user. No universal compatibility claim.'}
    out='docs/physical-package-receipt.json'
    if not failed and not (applied['state']=='VERIFIED' and observed==DISABLED and restored['state']=='REVERTED' and after==before):
        receipt['outcome']='UNVERIFIED'
    Path(out).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))
    if receipt['outcome']!='VERIFIED_CHANGE_AND_UNDO':raise SystemExit(1)


if __name__=='__main__':
    main()
