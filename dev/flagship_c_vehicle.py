"""Flagship-C O3 vehicle: owner-tapped watch->TV volume rounds + receipts.

Live:  python -m dev.flagship_c_vehicle --rounds 3 --out E:/flag-c-o3.json
Self:  python -m dev.flagship_c_vehicle --self-test   (doubles only)

Live mode needs: watch relay online, TV ADB authorized, owner present for
taps. Prints sanitized JSON only. Any failed assert FAILS the round loudly.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

VEHICLE = 'flagship-c-o3/1'
PRESS_BUDGET_S = 300
VOLUME_RE = re.compile(r'STREAM_MUSIC[^:]*:\s*\S+[^0-9]*?(\d{1,2})\b')


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def run_vehicle(io, rounds):
    receipt = {'vehicle': VEHICLE, 'started_utc': utcnow(), 'rounds': [],
               'verdict': 'PASS'}
    for n in range(1, rounds + 1):
        io.state['round'] = n - 1
        step = {'n': n, 'verdict': 'FAIL', 'reason': ''}
        try:
            ids = io.install([{'label': 'TV volume +',
                               'skill_id': 'tv_volume_step'},
                              {'label': 'TV volume -',
                               'skill_id': 'tv_volume_step'}])
            v0 = io.read_volume()
            if v0 is None:
                raise AssertionError('oracle unreadable before press')
            io.prompt('Round %d: tap Vol+ on the watch, then ENTER' % n)
            req = io.await_press(ids[0], PRESS_BUDGET_S)
            if req is None:
                raise AssertionError('no genuine tap within %ds' % PRESS_BUDGET_S)
            time.sleep(1)
            v1 = io.read_volume()
            step.update({'v0': v0, 'v1': v1, 'delta': (v1 - v0) if v1 is not None else None,
                         'request_id': req})
            if v1 is None or v1 - v0 != 1:
                raise AssertionError('no volume change +1 (%r -> %r)' % (v0, v1))
            if io.journal_count(req) != 1:
                raise AssertionError('exactly-one violated for %s' % req)
            io.revoke()
            io.prompt('Round %d: tap Vol+ again (post-revoke, must do nothing), then ENTER' % n)
            if io.post_revoke_probe(ids[0]):
                raise AssertionError('post-revoke press executed')
            v2 = io.read_volume()
            if v2 != v1:
                raise AssertionError('post-revoke volume moved (%r -> %r)' % (v1, v2))
            step['verdict'] = 'PASS'
        except AssertionError as e:
            step['reason'] = str(e)[:200]
            receipt['verdict'] = 'FAIL'
        except Exception as e:  # noqa: BLE001 - vehicle must record, not crash
            step['reason'] = '%s: %s' % (type(e).__name__, str(e)[:160])
            receipt['verdict'] = 'FAIL'
        receipt['rounds'].append(step)
    receipt['finished_utc'] = utcnow()
    return receipt


class LiveIO:
    """Production paths: real server, real adb oracle, owner taps."""

    def __init__(self, server, relay_id, tv_key, tv_serial):
        from src.runtime import api_v2
        self.rc = api_v2.remote_controls(server)
        self.server = server
        self.relay_id = relay_id
        self.tv_key = tv_key
        self.tv_serial = tv_serial
        self.state = {}
        self._api_v2 = api_v2

    def install(self, controls):
        body = {'relay_id': self.relay_id, 'consent': True, 'controls': [
            {'label': c['label'], 'skill_id': c['skill_id'],
             'target': self.tv_key,
             'params': {'direction': 'up' if '+' in c['label'] else 'down'}}
            for c in controls]}
        st = self.rc.set_controls(body)
        return [c['control_id'] for c in st['controls']]

    def prompt(self, text):
        print('OWNER: ' + text, flush=True)
        input()

    def await_press(self, control_id, budget_s):
        seen = {r['request_id'] for r in self.rc.press_history(control_id)}
        deadline = time.time() + budget_s
        while time.time() < deadline:
            for r in self.rc.press_history(control_id):
                if r['request_id'] not in seen and not r.get('injected'):
                    return r['request_id']
            time.sleep(2)
        return None

    def read_volume(self):
        p = subprocess.run(['adb', '-s', self.tv_serial, 'shell',
                            'dumpsys', 'audio'], capture_output=True,
                           timeout=60, text=True)
        if p.returncode != 0:
            return None
        m = VOLUME_RE.search(p.stdout)
        return int(m.group(1)) if m else None

    def journal_count(self, request_id):
        ex = self._api_v2.executor(self.server)
        return sum(1 for e in ex.events_since(0)
                   if e.get('kind') == 'remote_request'
                   and e.get('request_id') == request_id
                   and e.get('state') == 'EXECUTED')

    def revoke(self):
        self.rc.set_controls({'relay_id': self.relay_id, 'controls': [],
                              'consent': True})

    def post_revoke_probe(self, control_id):
        v0 = self.read_volume()
        time.sleep(3)
        return self.read_volume() != v0


class SelfTestIO:
    """Scripted doubles: proves the vehicle records PASS and FAIL honestly."""

    def __init__(self):
        self.state = {}
        self.round_cfg = {'v0': 10, 'v1': 11, 'exec': 1, 'revoked_exec': 0}
        self._reads = 0

    def install(self, controls):
        return ['ctl-self-%d' % i for i in range(len(controls))]

    def prompt(self, text):
        pass

    def await_press(self, control_id, budget_s):
        return 'req-self'

    def read_volume(self):
        self._reads += 1
        if self._reads % 3 == 0:
            return self.round_cfg['v1']  # post-revoke read: unchanged
        return self.round_cfg['v0'] if self._reads % 3 == 1 else self.round_cfg['v1']

    def journal_count(self, request_id):
        return self.round_cfg['exec']

    def revoke(self):
        pass

    def post_revoke_probe(self, control_id):
        return bool(self.round_cfg['revoked_exec'])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--out', default=None)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--relay-id', default=None)
    ap.add_argument('--tv-key', default=None)
    ap.add_argument('--tv-serial', default=None)
    args = ap.parse_args(argv)
    if args.self_test:
        receipt = run_vehicle(SelfTestIO(), rounds=args.rounds)
    else:
        if not (args.relay_id and args.tv_key and args.tv_serial):
            ap.error('live mode needs --relay-id, --tv-key, --tv-serial')
        from src.server import create_server
        from src.cli import ensure_discovery, default_providers
        server = create_server()
        ensure_discovery(server, default_providers())
        io = LiveIO(server, args.relay_id, args.tv_key, args.tv_serial)
        receipt = run_vehicle(io, rounds=args.rounds)
    text = json.dumps(receipt, indent=1)
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    return 0 if receipt['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
