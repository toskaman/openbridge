"""Physical cable pull during real writes on the owned USB phone (owner pulls the cable by hand).

The script runs continuous exact loops (prepare → apply → read-back → revert → read-back) on one allowlisted optional
app, so that the pull lands inside a transaction. It records the phase hit, the journal state, then waits for the owner
to plug the cable back and runs the normal recovery. Status lines go to artifacts/cable_pull_status.txt.
Usage: python -m dev.cable_pull_smoke --confirm-owned-device"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

from src.adapters.android import AndroidAdapter
from src.adapters.android_package import AndroidPackageState, DISABLED, ALLOWED_PACKAGES
from src.core.transactions import TransactionEngine, TransactionBlocked

STATUS = Path('artifacts/cable_pull_status.txt')


def say(msg):
    STATUS.parent.mkdir(exist_ok=True)
    with STATUS.open('a', encoding='utf-8') as f:
        f.write(f'{time.strftime("%H:%M:%S")} {msg}\n')


def usb(adb):
    return next((d for d in adb.discover()['devices'] if d['state'] == 'device' and d['transport'] == 'USB'), None)


def main():
    if '--confirm-owned-device' not in sys.argv:
        raise SystemExit('Owner authorization flag required')
    STATUS.parent.mkdir(exist_ok=True); STATUS.write_text('', encoding='utf-8')
    adb = AndroidAdapter()
    dev = usb(adb)
    serial = next(k for k, v in adb._handles.items() if v == dev['id'])
    installed = adb._run(['-s', serial, 'shell', 'pm', 'list', 'packages']).split()
    package = next(p for p in sorted(ALLOWED_PACKAGES) if 'package:' + p in installed)
    adapter = AndroidPackageState(adb, dev['id'], package)
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
    journal = root / ('cablepull-' + adapter.identity[-16:] + '.sqlite')
    engine = TransactionEngine(journal, adapter, allow_physical=True)
    if engine.status()['active']:
        raise SystemExit('Earlier transaction active; recover first')
    before = adapter.read_setting()
    if before == DISABLED:
        raise SystemExit('Package disabled by owner; refusing')
    out = {'before': before, 'cycles_completed': 0}
    say('CYCLING')
    deadline, phase, tid = time.monotonic() + 120, 'idle', None
    try:
        while time.monotonic() < deadline:
            tid = 'pull-' + uuid.uuid4().hex
            phase = 'prepare'; engine.prepare(tid, DISABLED, consent=True)
            phase = 'apply'; engine.apply(tid)
            phase = 'readback_disabled'
            if adapter.read_setting() != DISABLED:
                raise TransactionBlocked('read-back mismatch')
            phase = 'revert'; engine.revert(tid)
            phase = 'readback_restored'
            if adapter.read_setting() != before:
                raise TransactionBlocked('restore read-back mismatch')
            phase = 'idle'; tid = None
            out['cycles_completed'] += 1
        out['result'] = 'NO_PULL_DETECTED'
    except Exception as e:
        out['pulled_during_phase'] = phase
        out['error'] = f'{type(e).__name__}: {str(e)[:100]}'
        out['reported_success_for_interrupted_tx'] = False
        try:
            out['journal_state'] = engine.get(tid)['state'] if tid else 'no open transaction'
        except Exception as e2:
            out['journal_state'] = 'not readable while unplugged (' + type(e2).__name__ + ')'
    say('PULLED ' + json.dumps(out))
    say('WAITING_FOR_REPLUG')
    for _ in range(170):
        time.sleep(1)
        try:
            d = usb(adb)
        except Exception:
            d = None
        if d:
            break
    else:
        say('DONE ' + json.dumps(dict(out, recovery='PHONE_NOT_BACK')))
        return
    time.sleep(2)
    a2 = AndroidPackageState(adb, usb(adb)['id'], package)
    e2 = TransactionEngine(journal, a2, allow_physical=True)
    act = e2.status()['active']
    out['active_after_replug'] = act['state'] if act else None
    out['recovery'] = e2.revert(act['id'])['state'] if act else 'NOTHING_PENDING'
    out['after'] = a2.read_setting()
    out['original_preserved'] = out['after'] == before
    say('DONE ' + json.dumps(out))
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
