"""V4-03 crash drill: an external supervisor crashes a real transaction at each failpoint and proves recovery.

For each failpoint the supervisor starts a separate worker process that runs the transaction with
OPENBRIDGE_FAILPOINT set; the worker exits abruptly (code 97) at that point. A second, fresh process then
plays the restarted server: it opens the same durable journal, reads the device state independently,
and runs the normal recovery. Pass = worker died at the point, recovery ended REVERTED, and the read-back
equals the value recorded before the transaction.

  python -m dev.crash_drill --target sim                              (any PC, CI)
  python -m dev.crash_drill --target phone --confirm-owned-device     (owned USB phone, allowlisted app)
Prints states only."""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from src.core.transactions import FAILPOINTS, TransactionEngine


def make_engine(target, workdir):
    if target == 'sim':
        from src.adapters.simulated_setting import SimulatedSetting
        return TransactionEngine(Path(workdir) / 'journal.sqlite', SimulatedSetting(Path(workdir) / 'setting.sqlite')), 'sim'
    from src.adapters.android import AndroidAdapter
    from src.adapters.android_package import AndroidPackageState, ALLOWED_PACKAGES
    adb = AndroidAdapter()
    dev = next(d for d in adb.discover()['devices'] if d['state'] == 'device' and d['transport'] == 'USB')
    serial = next(k for k, v in adb._handles.items() if v == dev['id'])
    installed = adb._run(['-s', serial, 'shell', 'pm', 'list', 'packages']).split()
    package = next(p for p in sorted(ALLOWED_PACKAGES) if 'package:' + p in installed)
    adapter = AndroidPackageState(adb, dev['id'], package)
    return TransactionEngine(Path(workdir) / 'journal.sqlite', adapter, allow_physical=True), 'phone'


def target_value(engine):
    if engine.adapter.__class__.__name__ == 'SimulatedSetting':
        return 60
    from src.adapters.android_package import DISABLED
    return DISABLED


def worker(target, workdir, txid):
    """Runs the transaction; dies at the configured failpoint."""
    engine, _ = make_engine(target, workdir)
    engine.prepare(txid, target_value(engine), consent=True)
    engine.apply(txid)
    engine.revert(txid)          # reached only when the failpoint is during_revert, or none fired
    print('NO_CRASH')


def recover(target, workdir):
    """The restarted process: journal + independent read-back + normal recovery."""
    engine, _ = make_engine(target, workdir)
    st = engine.status()
    active = st['active']
    out = {'found_in_journal': active['state'] if active else None, 'value_at_restart': st['current_value']}
    if active:
        out['recovery'] = engine.revert(active['id'])['state']
        out['before'] = active['before']
    out['value_after'] = engine.adapter.read_setting()
    print(json.dumps(out))


def supervise(target):
    results = []
    root = Path(tempfile.mkdtemp(prefix='ob-crash-')) if target == 'sim' else \
        Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'OpenBridge' / 'crash-drill'
    root.mkdir(parents=True, exist_ok=True)
    py = [sys.executable, '-m', 'dev.crash_drill']
    flag = ['--confirm-owned-device'] if target == 'phone' else []
    for point in FAILPOINTS:
        workdir = root / point
        workdir.mkdir(exist_ok=True)
        if target == 'sim':
            # seed a known starting value
            subprocess.run(py + ['--seed', str(workdir)], check=True, capture_output=True)
        env = dict(os.environ, OPENBRIDGE_FAILPOINT=point)
        t0 = time.monotonic()
        w = subprocess.run(py + ['--worker', target, str(workdir), 'drill-' + uuid.uuid4().hex[:12]] + flag,
                           env=env, capture_output=True, text=True, timeout=120)
        env.pop('OPENBRIDGE_FAILPOINT')
        r = subprocess.run(py + ['--recover', target, str(workdir)] + flag, env=env, capture_output=True, text=True, timeout=120)
        try:
            rec = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            rec = {'error': (r.stderr or r.stdout)[-200:]}
        ok = (w.returncode == 97 and rec.get('recovery') in ('REVERTED', None)
              and rec.get('value_after') == rec.get('before', rec.get('value_at_restart')))
        results.append({'failpoint': point, 'worker_exit': w.returncode, **rec,
                        'seconds': round(time.monotonic() - t0, 1), 'pass': ok})
    print(json.dumps({'target': target, 'passed': sum(r['pass'] for r in results), 'of': len(results), 'drills': results}, indent=1))
    return all(r['pass'] for r in results)


def main():
    a = sys.argv[1:]
    if '--seed' in a:
        from src.adapters.simulated_setting import SimulatedSetting
        s = SimulatedSetting(Path(a[a.index('--seed') + 1]) / 'setting.sqlite')
        s.write_setting(30)
        return
    if ('--target' in a and a[a.index('--target') + 1] == 'phone' or 'phone' in a) and '--confirm-owned-device' not in a:
        raise SystemExit('Owner authorization flag required for the phone target')
    if '--worker' in a:
        i = a.index('--worker'); return worker(a[i + 1], a[i + 2], a[i + 3])
    if '--recover' in a:
        i = a.index('--recover'); return recover(a[i + 1], a[i + 2])
    sys.exit(0 if supervise(a[a.index('--target') + 1] if '--target' in a else 'sim') else 1)


if __name__ == '__main__':
    main()
