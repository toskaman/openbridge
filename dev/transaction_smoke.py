"""Run one explicitly simulated snapshot/change/Undo proof. No device access."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import uuid
from src.adapters.simulated_setting import SimulatedSetting
from src.core.transactions import TransactionEngine


def main():
    private_root=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share'))) / 'OpenBridge'
    journal=private_root/'simulated-transactions.sqlite'
    adapter=SimulatedSetting(private_root/'simulated-setting.sqlite')
    engine=TransactionEngine(journal,adapter)
    transaction_id='sim-'+uuid.uuid4().hex
    before=adapter.read_setting()
    target=60 if before != 60 else 30
    snapshot=engine.prepare(transaction_id,target,consent=True)
    try:
        verified=engine.apply(transaction_id)
        observed=adapter.read_setting()
    finally:
        restored=engine.revert(transaction_id)
    after=adapter.read_setting()
    if observed != target or after != before or restored['state']!='REVERTED':
        raise RuntimeError('Simulation restoration check failed')
    with closing(sqlite3.connect(journal)) as db:
        events=[row[0] for row in db.execute('SELECT state FROM events WHERE transaction_id=? ORDER BY sequence',(transaction_id,))]
    receipt={'source':'SIMULATED','physical_device_access':False,'physical_writes':0,
             'transaction_id':transaction_id,'field':'screen_timeout_seconds',
             'before':snapshot['before'],'proposed':target,'observed_after_apply':observed,
             'observed_after_undo':after,'final_state':restored['state'],'events':events,
             'limitation':'Synthetic state only. This is not evidence of physical-device rollback.'}
    Path('docs/simulated-transaction-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))


if __name__=='__main__':
    main()
