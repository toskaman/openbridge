"""Wallpaper vehicle: one owner-selected image -> N full-control PCs (H).

Live:  python -m dev.wallpaper_vehicle --image E:/pic/wall.png --pcs <k1,k2> --out E:/wall.json
Self:  python -m dev.wallpaper_vehicle --self-test   (doubles only)

Owner-run, one explicit invocation = one bounded distribution. Every
PC step goes through the real Router (routes + arm + invoke with the
owner's consent); each PC needs full control enabled or its step is
refused loudly. Per-PC receipts; one failure = PARTIAL, never a
false global success. Prints sanitized JSON only.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

VEHICLE = 'wallpaper/1'
MAX_BYTES = 8 * 1024 * 1024


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class StepError(Exception):
    pass


class VehicleIO:
    pcs = []

    def stage(self, path):
        raise NotImplementedError

    def place(self, pc_key, transfer_id, name):
        raise NotImplementedError

    def apply(self, pc_key, name):
        raise NotImplementedError


def run_wallpaper(io, image_label):
    receipt = {'vehicle': VEHICLE, 'started_utc': utcnow(),
               'image': str(image_label)[:120], 'pcs': [], 'verdict': 'FAIL'}
    if not list(getattr(io, 'pcs', [])):
        receipt['finished_utc'] = utcnow()
        receipt['reason'] = 'no target PCs'
        return receipt
    try:
        staged = io.stage(image_label)
    except Exception as e:  # noqa: BLE001 - vehicle records, not crashes
        receipt['finished_utc'] = utcnow()
        receipt['reason'] = '%s: %s' % (type(e).__name__, str(e)[:160])
        return receipt
    receipt['staged'] = {'transfer_id': staged['transfer_id'], 'bytes': staged['bytes'],
                         'sha256': staged['sha256'][:16], 'name': staged['name']}
    for pc in io.pcs:
        row = {'pc': pc, 'ok': False}
        try:
            placed = io.place(pc, staged['transfer_id'], staged['name'])
            if placed['sha256'] != staged['sha256']:
                raise StepError('device bytes differ from staged image')
            seen = io.apply(pc, staged['name'])
            row.update({'ok': True, 'remote': placed['remote'],
                        'sha256': placed['sha256'][:16],
                        'previous': (seen.get('previous') or '')[:120],
                        'restorable': bool(seen.get('restorable'))})
        except StepError as e:
            row['reason'] = str(e)[:200]
        except Exception as e:  # noqa: BLE001 - per-PC truth, never a throw
            row['reason'] = '%s: %s' % (type(e).__name__, str(e)[:160])
        receipt['pcs'].append(row)
    oks = sum(1 for p in receipt['pcs'] if p['ok'])
    receipt['verdict'] = 'PASS' if oks == len(receipt['pcs']) else ('PARTIAL' if oks else 'FAIL')
    receipt['finished_utc'] = utcnow()
    return receipt


class LiveIO(VehicleIO):
    def __init__(self, server, image_path, pcs):
        from src.runtime.api_v2 import executor, router
        self.rt = router(server)
        self.ex = executor(server)
        self.image_path = image_path
        self.pcs = list(pcs)
        self.actor = 'owner:wallpaper-vehicle'

    def _routed(self, skill_id, target, params):
        from src.runtime.routing import RouteError
        doc = self.rt.skill_routes(skill_id, target)
        if not doc.get('selected_route_id'):
            reasons = sorted({r['reason'] for r in doc.get('routes', [])
                              if r.get('reason')}) or ['no route']
            raise StepError('NO_ROUTE: ' + ','.join(reasons))
        lease = self.rt.arm({'skill_id': skill_id, 'target': target,
                             'route_id': doc['selected_route_id'],
                             'params': params, 'consent': True}, actor=self.actor)
        rc = self.rt.invoke({'invocation_id': lease['invocation_id'],
                             'route_id': lease['route_id'], 'lease_id': lease['lease_id'],
                             'graph_revision': lease['graph_revision'],
                             'skill_id': skill_id, 'params': params,
                             'consent': True, 'target': target}, actor=self.actor)
        if (rc.get('state') or '').upper() not in ('EXECUTED', 'VERIFIED'):
            raise StepError('%s %s: %s' % (skill_id, rc.get('state'), (rc.get('errors') or ['?'])[0]))
        return rc.get('result') or {}

    def stage(self, path):
        import os
        from pathlib import Path
        p = Path(self.image_path)
        if not p.is_file():
            raise StepError('image file not found')
        data = p.read_bytes()
        if len(data) > MAX_BYTES or not data:
            raise StepError('image must be 1 byte..8 MB')
        if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')):
            raise StepError('image must be PNG/JPEG bytes')
        name = p.name
        if len(name) > 64 or not name.replace('.', '').replace('_', '').replace('-', '').isalnum():
            raise StepError('image filename must be a strict basename')
        tid = self.ex._captures().put(bytes(data), kind='cap')
        return {'transfer_id': tid, 'sha256': hashlib.sha256(data).hexdigest(),
                'bytes': len(data), 'name': name}

    def place(self, pc_key, transfer_id, name):
        res = self._routed('pc_place_file', pc_key, {'transfer_id': transfer_id, 'name': name})
        return {'remote': res.get('remote'), 'sha256': res.get('sha256')}

    def apply(self, pc_key, name):
        res = self._routed('pc_wallpaper', pc_key, {'name': name})
        return {'previous': res.get('previous'), 'restorable': res.get('restorable')}


class SelfTestIO(VehicleIO):
    pcs = ['pc-a', 'pc-b']

    def stage(self, path):
        from src.runtime import montage as M
        raw = M.encode_png(8, 8, bytes((1, 2, 3, 255)) * 64)
        return {'transfer_id': 't-self', 'sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw), 'name': 'self.png'}

    def place(self, pc_key, transfer_id, name):
        return {'remote': 'managed\\' + name,
                'sha256': self.stage(None)['sha256']}

    def apply(self, pc_key, name):
        return {'previous': 'C:\\win\\old.png', 'restorable': False}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', default=None)
    ap.add_argument('--pcs', default='')
    ap.add_argument('--out', default=None)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args(argv)
    if args.self_test:
        receipt = run_wallpaper(SelfTestIO(), 'self-test')
    else:
        if not args.image or not args.pcs.strip():
            ap.error('live mode needs --image <png/jpg> and --pcs <key,key,..>')
        from argparse import Namespace
        from src.server import create_server
        from src.adapters.android import default_remember_path
        from src.cli import ensure_discovery, default_providers
        server = create_server(adb_remember=default_remember_path())
        ensure_discovery(server, default_providers(Namespace()))
        io = LiveIO(server, args.image, [k.strip() for k in args.pcs.split(',') if k.strip()])
        receipt = run_wallpaper(io, args.image)
    text = json.dumps(receipt, indent=1)
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    return 0 if receipt['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
