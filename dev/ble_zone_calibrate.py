"""BLE zone calibration with the real relays (V4-11). Owner-run, opt-in, local only.

1. Start OpenBridge, pair the phone and TV Companions, run discovery.
2. `python -m dev.ble_zone_calibrate --list` shows advertisers seen by the relays; pick YOUR device's id (opt-in;
   never someone else's).
3. `python -m dev.ble_zone_calibrate --id addr:... --zones desk,doorway,living_room --runs 3 --seconds 60`
   asks you to stand in each zone with the device, triggers bounded relay scans and records RSSI per relay.
4. Writes artifacts/ble-zones/<date>.json (samples, no address) and prints precision/recall per zone,
   two relays vs single relay.
"""
import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.runtime import ble_zones

BASE = 'http://127.0.0.1:18765'


def call(path, body=None, token=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 method='GET' if body is None else 'POST',
                                 headers={'Content-Type': 'application/json', 'Origin': BASE, 'X-CSRF-Token': token or ''})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=40) as r:
        return json.loads(r.read())


def relays():
    rows = call('/api/v2/routes')['routes']
    return [(r['relay_id'], r['relay_device']) for r in rows if r.get('online') and r.get('permission_granted')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--id')
    ap.add_argument('--zones', default='desk,doorway,living_room')
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--seconds', type=int, default=60)
    a = ap.parse_args()
    if a.list:
        for adv in call('/api/v2/relays')['advertisers'][:40]:
            print(adv['id'], adv['relays'], adv['rssi_median'], adv['identity'])
        return
    token = call('/api/session')['csrf_token']
    rs = relays()
    if len(rs) < 2:
        print(f'Warning: {len(rs)} relay(s) online; zone results will be single-relay only.')
    samples = []
    for run in range(a.runs):
        for zone in a.zones.split(','):
            input(f'Run {run + 1}/{a.runs}: stand in "{zone}" with the device, then press Enter…')
            t_end = time.time() + a.seconds
            while time.time() < t_end:
                for rid, dev in rs:
                    call('/api/v2/execute', {'primitive_id': 'relay_ble_scan', 'device_key': dev, 'consent': True,
                                             'params': {'relay_id': rid, 'seconds': 3}}, token)
                for s in call(f'/api/v2/relays/samples?id={a.id}&since_s=10')['samples']:
                    s.update(zone=zone, run=run)
                    if s not in samples:
                        samples.append(s)
    rep = ble_zones.report(samples)
    out = Path('artifacts/ble-zones'); out.mkdir(parents=True, exist_ok=True)
    p = out / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
    p.write_text(json.dumps({'samples': samples, 'report': rep, 'status': 'REAL_HARDWARE (owner-run calibration)'}, indent=1), encoding='utf-8')
    print(json.dumps(rep, indent=1)); print('saved', p)


if __name__ == '__main__':
    main()
