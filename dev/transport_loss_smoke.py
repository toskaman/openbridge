"""Real transport loss on an owner-connected Android TV over ADB Wi-Fi: the link is dropped (adb disconnect) while
read_facts runs, then an action is attempted on the dead link, then the link is restored. Read-only on the device.
Usage: python -m dev.transport_loss_smoke <tv-ip:5555>. Prints states only."""
import json
import subprocess
import sys
import threading
import time

from src.runtime.primitives import Executor
from src.server import create_server


def main(addr):
    s = create_server(0)
    ex = Executor(s)
    out = {}
    d = ex.execute('bounded_discovery', 'fabric', {'providers': ['android']})
    tv = next(k for k, dev in s.fabric_registry.devices.items() if dev['category'] == 'tv' and any(i.strong for i in dev['identifiers']))
    out['baseline'] = ex.execute('read_facts', tv, {})['state']
    threading.Timer(0.4, lambda: subprocess.run(['adb', 'disconnect', addr], capture_output=True)).start()
    t0 = time.monotonic()
    r = ex.execute('read_facts', tv, {})
    out['during_drop'] = {'state': r['state'], 'verified': r['verified'], 'facts': len(r['result'].get('facts', [])),
                          'errors': [e[:60] for e in r['errors']], 'seconds': round(time.monotonic() - t0, 1)}
    time.sleep(1)
    s.android.discover()
    r = ex.execute('read_facts', tv, {})
    out['after_drop'] = {'state': r['state'], 'errors': [e[:60] for e in r['errors']]}
    subprocess.run(['adb', 'connect', addr], capture_output=True, timeout=20)
    time.sleep(2)
    s.android.discover()
    r = ex.execute('read_facts', tv, {})
    out['after_reconnect'] = {'state': r['state'], 'verified': r['verified'], 'facts': len(r['result'].get('facts', []))}
    out['recovery'] = ex.recovery().pending_transactions
    print(json.dumps(out, indent=1))
    s.server_close()


if __name__ == '__main__':
    main(sys.argv[1])
