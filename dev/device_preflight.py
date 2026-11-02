"""Device-frontier preflight: safe owner-run checks before filming O3/A rounds.

Read-only except one owner-driven step: the oracle validation asks the
owner to press Vol+ ON THE TV REMOTE (not the watch), proving the adb
oracle tracks real volume without touching any OpenBridge path.

Usage:
  python -m dev.device_preflight --tv-serial <adb-serial> [--rounds 3]
                                 [--out E:/preflight.json]

Exit 0 only when every check passes. Prints sanitized JSON only.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

from dev.flagship_c_vehicle import music_state_from_dumpsys, resolve_tv_key

CHECK_TIMEOUT_S = 90


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def adb(*args, timeout=CHECK_TIMEOUT_S):
    p = subprocess.run(['adb'] + list(args), capture_output=True,
                       timeout=timeout, text=True)
    return p.returncode, (p.stdout or '')[:6000]


def parse_volume(dumpsys_text):
    return music_state_from_dumpsys(dumpsys_text)[0]


def parse_max(dumpsys_text):
    return music_state_from_dumpsys(dumpsys_text)[1]


class Preflight:
    def __init__(self, tv_serial, rounds):
        self.tv_serial = tv_serial
        self.rounds = rounds
        self.checks = []
        self.server = None

    def record(self, name, ok, detail=''):
        self.checks.append({'check': name, 'ok': bool(ok),
                            'detail': str(detail)[:220]})
        return ok

    def check_adb(self):
        code, out = adb('devices')
        if code != 0:
            return self.record('adb_devices', False, 'adb failed rc=%d' % code)
        state = None
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == self.tv_serial:
                state = parts[1]
        if state == 'device':
            return self.record('adb_devices', True, self.tv_serial)
        return self.record('adb_devices', False,
                           '%s state=%s' % (self.tv_serial, state))

    def check_discovery(self):
        from argparse import Namespace
        from src.server import create_server
        from src.cli import ensure_discovery, default_providers
        try:
            server = create_server()
            ensure_discovery(server, default_providers(Namespace()))
        except Exception as e:  # noqa: BLE001 - preflight records, not crashes
            return self.record('discovery', False, '%s: %s'
                               % (type(e).__name__, e))
        self.server = server
        try:
            tv_key = resolve_tv_key(server)
        except SystemExit as e:
            return self.record('tv_resolve', False, str(e))
        devs = (server.fabric_snapshot or {}).get('devices', []) or []
        census = {}
        for d in devs:
            census[d.get('category', '?')] = census.get(d.get('category', '?'), 0) + 1
        self.record('discovery', True, 'devices=%d %s' % (len(devs), census))
        self.tv_key = tv_key
        return self.record('tv_resolve', True, tv_key)

    def check_key_rotation(self):
        from argparse import Namespace
        from src.server import create_server
        from src.cli import ensure_discovery, default_providers
        try:
            s2 = create_server()
            ensure_discovery(s2, default_providers(Namespace()))
            k2 = resolve_tv_key(s2)
        except Exception as e:  # noqa: BLE001 - preflight records, not crashes
            return self.record('key_rotation', False, '%s: %s'
                               % (type(e).__name__, e))
        same = (k2 == getattr(self, 'tv_key', None))
        return self.record('key_rotation', True,
                           'stable' if same else 'ROTATED (vehicle resolves in-process)')

    def check_relay(self):
        from dev.flagship_c_vehicle import resolve_relay_id
        try:
            rid = resolve_relay_id(self.server)
        except SystemExit as e:
            return self.record('watch_relay', False, str(e))
        self.relay_id = rid
        return self.record('watch_relay', True, rid)

    def check_routes(self):
        from src.runtime.api_v2 import router
        rt = router(self.server)
        ok = True
        for skill in ('tv_volume_step', 'tv_sleep'):
            try:
                doc = rt.skill_routes(skill, self.tv_key)
            except Exception as e:  # noqa: BLE001 - preflight records
                self.record('route_' + skill, False, '%s: %s'
                            % (type(e).__name__, e))
                ok = False
                continue
            if doc.get('selected_route_id'):
                self.record('route_' + skill, True, doc['selected_route_id'])
            else:
                reasons = sorted({r['reason'] for r in doc.get('routes', [])
                                  if r.get('reason')}) or ['no route']
                self.record('route_' + skill, False, ','.join(reasons))
                ok = False
        return ok

    def read_tv_volume(self):
        code, out = adb('-s', self.tv_serial, 'shell', 'dumpsys', 'audio')
        if code != 0:
            return None
        return parse_volume(out)

    def check_oracle(self, io_input=input):
        v0 = self.read_tv_volume()
        if v0 is None:
            return self.record('oracle', False, 'unreadable before tap')
        print('OWNER: press Vol+ ONCE on the TV remote (not the watch), then ENTER',
              flush=True)
        io_input()
        time.sleep(1)
        v1 = self.read_tv_volume()
        if v1 is None:
            return self.record('oracle', False, 'unreadable after tap')
        if v1 - v0 != 1:
            return self.record('oracle', False, 'delta %r -> %r (want +1)' % (v0, v1))
        self.v0, self.v1 = v0, v1
        return self.record('oracle', True, '%d -> %d' % (v0, v1))

    def check_headroom(self):
        code, out = adb('-s', self.tv_serial, 'shell', 'dumpsys', 'audio')
        vmax = parse_max(out) if code == 0 else None
        if vmax is None:
            return self.record('headroom', False, 'max unknown; lower TV volume first')
        cur = getattr(self, 'v1', None)
        if cur is None:
            return self.record('headroom', False, 'no oracle reading')
        if cur + self.rounds > vmax:
            return self.record('headroom', False,
                               'vol %d + %d rounds > max %d; lower volume'
                               % (cur, self.rounds, vmax))
        return self.record('headroom', True, '%d + %d <= %d' % (cur, self.rounds, vmax))

    def run(self, io_input=input):
        if not self.check_adb():
            return self.verdict()
        if not self.check_discovery():
            return self.verdict()
        self.check_key_rotation()
        relay_ok = self.check_relay()
        if relay_ok:
            self.check_routes()
        else:
            self.record('route_tv_volume_step', False, 'skipped: no relay')
            self.record('route_tv_sleep', False, 'skipped: no relay')
        if self.check_oracle(io_input):
            self.check_headroom()
        return self.verdict()

    def verdict(self):
        ok = all(c['ok'] for c in self.checks)
        return {'preflight': 'device-frontier/1', 'at_utc': utcnow(),
                'tv_serial': self.tv_serial, 'checks': self.checks,
                'verdict': 'GO' if ok else 'NO-GO'}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--tv-serial', required=True)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--out', default=None)
    args = ap.parse_args(argv)
    receipt = Preflight(args.tv_serial, args.rounds).run()
    text = json.dumps(receipt, indent=1)
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    return 0 if receipt['verdict'] == 'GO' else 1


if __name__ == '__main__':
    sys.exit(main())
