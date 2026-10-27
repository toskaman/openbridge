"""Explicitly authorized, owned USB phone: the ADB transport is reset from the host (`adb -s <serial> reconnect`)
while an allowlisted optional-app write is in flight. Checks that OpenBridge never reports success, that the journal
keeps the transaction recoverable, and that recovery restores the exact original state once the phone is back.
This is a host-side transport reset, NOT a physical cable pull. Prints states only."""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from src.adapters.android import AndroidAdapter
from src.adapters.android_package import AndroidPackageState, DISABLED, ALLOWED_PACKAGES
from src.core.transactions import TransactionEngine, TransactionBlocked


def main(delay):
    if '--confirm-owned-device' not in sys.argv:
        raise SystemExit('Owner authorization flag required')
    adb = AndroidAdapter()
    dev = next(d for d in adb.discover()['devices'] if d['state'] == 'device' and d['transport'] == 'USB')
    serial = next(k for k, v in adb._handles.items() if v == dev['id'])
    installed = adb._run(['-s', serial, 'shell', 'pm', 'list', 'packages']).split()
    package = next(p for p in sorted(ALLOWED_PACKAGES) if 'package:' + p in installed)
    adapter = AndroidPackageState(adb, dev['id'], package)
    root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local/share'))) / 'OpenBridge'
    engine = TransactionEngine(root / ('linkloss-' + adapter.identity[-16:] + '.sqlite'), adapter, allow_physical=True)
    act = engine.status()['active']
    if act:
        r = engine.revert(act['id'])
        print(json.dumps({'recovered_earlier': act['state'], 'recovery': r['state'], 'now': adapter.read_setting()}))
        return
    before = adapter.read_setting()
    if before == DISABLED:
        raise SystemExit('Package already disabled by the owner; refusing')
    out = {'package_allowlisted': True, 'before': before, 'reset_after_s': delay}
    tid = 'linkloss-' + uuid.uuid4().hex
    engine.prepare(tid, DISABLED, consent=True)
    threading.Timer(delay, lambda: subprocess.run(['adb', '-s', serial, 'reconnect'], capture_output=True)).start()
    try:
        out['apply'] = engine.apply(tid)['state']
        out['readback_after_apply'] = adapter.read_setting()
    except (TransactionBlocked, ValueError, OSError) as e:
        out['apply'] = 'BLOCKED: ' + type(e).__name__ + ': ' + str(e)[:80]
    try:
        out['state_after_fault'] = engine.get(tid)['state']
    except Exception as e:
        out['state_after_fault'] = 'unreadable: ' + type(e).__name__
    try:
        out['immediate_revert'] = engine.revert(tid)['state']
    except (TransactionBlocked, ValueError, OSError) as e:
        out['immediate_revert'] = 'BLOCKED: ' + str(e)[:80]
    try:
        out['pending_after_fault'] = engine.get(tid)['state']
    except Exception as e:
        out['pending_after_fault'] = 'unreadable: ' + type(e).__name__
    # wait for the phone to come back, then run the normal recovery path
    for _ in range(30):
        time.sleep(1)
        adb.discover()
        try:
            adapter2 = AndroidPackageState(adb, next(d['id'] for d in adb.discover()['devices'] if d['state'] == 'device' and d['transport'] == 'USB'), package)
            break
        except (StopIteration, ValueError):
            adapter2 = None
    if adapter2 is None:
        out['recovery'] = 'PHONE_NOT_BACK'
    else:
        e2 = TransactionEngine(root / ('linkloss-' + adapter2.identity[-16:] + '.sqlite'), adapter2, allow_physical=True)
        print(json.dumps(out), flush=True)
        act = e2.status()['active']
        out['recovery'] = e2.revert(act['id'])['state'] if act else 'NOTHING_PENDING'
        after = adapter2.read_setting()
        out['after'] = after
        out['original_preserved'] = after == before
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(float(next((a for a in sys.argv[1:] if not a.startswith('--')), '0.05')))
