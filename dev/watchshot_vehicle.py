"""Watchshot vehicle: TV-or-PC screenshot -> watch render + receipts (D/E).

Live:  python -m dev.watchshot_vehicle --source tv --out E:/watchshot.json
       python -m dev.watchshot_vehicle --source pc --out E:/watchshot.json
Self:  python -m dev.watchshot_vehicle --self-test   (doubles only)

Owner-run, one explicit invocation = one bounded pipeline. Every
device step goes through the real Router (routes + arm + invoke with
the owner's consent). The PC capture itself is vehicle-local (PIL on
Windows) and is labeled as such in the receipt — it is NOT a routed
skill. Prints sanitized JSON only. Failures are loud, never silent.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone

VEHICLE = 'watchshot/1'
WATCH_SIDE = 448


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def resolve_watch_key(server):
    """The ADB-linked watch (exactly 1). Never guesses among several."""
    devs = (server.fabric_snapshot or {}).get('devices', []) or []
    cands = [d for d in devs
             if d.get('category') == 'watch' and d.get('handles')]
    if len(cands) != 1:
        raise SystemExit('watch auto-resolve failed: %d candidates %s; pass --watch-key'
                         % (len(cands), sorted(c.get('key') for c in cands)))
    return cands[0]['key']


def run_watchshot(io):
    receipt = {'vehicle': VEHICLE, 'started_utc': utcnow(), 'steps': [],
               'verdict': 'FAIL'}
    try:
        from src.runtime import montage as M
        cap = io.capture()
        receipt['steps'].append({'step': 'capture', 'ok': True,
                                 'origin': cap['origin'], 'bytes': len(cap['raw']),
                                 'size': '%dx%d' % (cap['w'], cap['h']),
                                 'sha256': cap['sha256'][:16]})
        fit = M.fit_png(cap['raw'], WATCH_SIDE)
        fw, fh = M.png_size(fit)
        sent = io.send_fit(fit, fw, fh)
        if sent['device_sha256'] != hashlib.sha256(fit).hexdigest():
            raise AssertionError('device bytes differ from fitted PNG')
        receipt['steps'].append({'step': 'send', 'ok': True,
                                 'capture_id': sent['capture_id'],
                                 'remote': sent['remote'], 'bytes': len(fit),
                                 'size': '%dx%d' % (fw, fh),
                                 'device_sha256': sent['device_sha256'][:16]})
        seen = io.view(sent['name'])
        if not seen.get('focused_app'):
            raise AssertionError('viewer read-back missing (no focused_app)')
        receipt['steps'].append({'step': 'view', 'ok': True,
                                 'focused_app': seen.get('focused_app'),
                                 'power': seen.get('power')})
        receipt['verdict'] = 'PASS'
    except AssertionError as e:
        receipt['steps'].append({'step': 'failed', 'ok': False,
                                 'reason': str(e)[:200]})
    except Exception as e:  # noqa: BLE001 - vehicle must record, not crash
        receipt['steps'].append({'step': 'failed', 'ok': False, 'reason': '%s: %s'
                                 % (type(e).__name__, str(e)[:160])})
    receipt['finished_utc'] = utcnow()
    return receipt


class LiveIO:
    """Production paths: real Router, real ADB, owner-run consent."""

    def __init__(self, server, source, tv_key, watch_key):
        from src.runtime.api_v2 import executor, router
        self.rt = router(server)
        self.ex = executor(server)
        self.source = source
        self.tv_key = tv_key
        self.watch_key = watch_key
        self.actor = 'owner:watchshot-vehicle'

    def _routed(self, skill_id, target, params):
        from src.runtime.routing import RouteError
        doc = self.rt.skill_routes(skill_id, target)
        if not doc.get('selected_route_id'):
            reasons = sorted({r['reason'] for r in doc.get('routes', [])
                              if r.get('reason')}) or ['no route']
            raise RouteError(409, 'NO_ROUTE', ','.join(reasons))
        lease = self.rt.arm({'skill_id': skill_id, 'target': target,
                             'route_id': doc['selected_route_id'],
                             'params': params, 'consent': True},
                            actor=self.actor)
        body = {'invocation_id': lease['invocation_id'],
                'route_id': lease['route_id'], 'lease_id': lease['lease_id'],
                'graph_revision': lease['graph_revision'],
                'skill_id': skill_id, 'params': params, 'consent': True,
                'target': target}
        rc = self.rt.invoke(body, actor=self.actor)
        if (rc.get('state') or '').upper() not in ('EXECUTED', 'VERIFIED', 'REVERTED'):
            raise AssertionError('%s %s: %s' % (skill_id, rc.get('state'), (rc.get('errors') or ['?'])[0]))
        return rc

    def capture(self):
        if self.source == 'pc':
            return self._capture_pc()
        rc = self._routed('screen_capture', self.tv_key, {})
        res = rc.get('result') or {}
        store = self.ex._captures()
        raw = bytes(store.get(res['capture_id']))
        return {'origin': 'tv:adb-screencap', 'raw': raw, 'w': res['width'],
                'h': res['height'], 'sha256': res['sha256']}

    def _capture_pc(self):
        import io as _io
        try:
            from PIL import ImageGrab
        except ImportError:
            raise AssertionError('PC capture needs Pillow (not installed)')
        try:
            img = ImageGrab.grab(all_screens=True)
        except Exception as e:  # noqa: BLE001 - backend specifics vary
            raise AssertionError('PC capture failed: %s' % e)
        buf = _io.BytesIO()
        img.save(buf, format='PNG')
        raw = buf.getvalue()
        return {'origin': 'pc:local-pillow-all-screens (owner-run tool, not a routed skill)',
                'raw': raw, 'w': img.width, 'h': img.height,
                'sha256': hashlib.sha256(raw).hexdigest()}

    def send_fit(self, fit, fw, fh):
        del fw, fh
        store = self.ex._captures()
        cid = store.put(fit, kind='cap')
        name = cid + '.png'
        rc = self._routed('capture_send', self.watch_key,
                          {'capture_id': cid, 'name': name})
        res = rc.get('result') or {}
        return {'capture_id': cid, 'name': name, 'remote': res.get('remote'),
                'device_sha256': res.get('sha256')}

    def view(self, name):
        rc = self._routed('view_image', self.watch_key, {'name': name})
        screen = ((rc.get('result') or {}).get('screen')) or {}
        if not screen.get('focused_app'):
            raise AssertionError('viewer read-back missing (no focused_app)')
        return screen


class SelfTestIO:
    """Scripted doubles: honest PASS + black-frame DRM shape."""

    def __init__(self, black=False):
        self.black = black

    def capture(self):
        from src.runtime import montage as M
        color = (0, 0, 0, 255) if self.black else (10, 200, 90, 255)
        raw = M.encode_png(96, 48, bytes(color) * (96 * 48))
        return {'origin': 'self-test', 'raw': raw, 'w': 96, 'h': 48,
                'sha256': hashlib.sha256(raw).hexdigest()}

    def send_fit(self, fit, fw, fh):
        return {'capture_id': 'cap-self', 'name': 'cap-self.png',
                'remote': '/sdcard/OpenBridge/cap-self.png',
                'device_sha256': hashlib.sha256(fit).hexdigest()}

    def view(self, name):
        return {'focused_app': 'com.test.viewer', 'power': 'awake'}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', choices=('tv', 'pc'), default='tv')
    ap.add_argument('--out', default=None)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--tv-key', default=None)
    ap.add_argument('--watch-key', default=None)
    args = ap.parse_args(argv)
    if args.self_test:
        receipt = run_watchshot(SelfTestIO())
    else:
        from argparse import Namespace
        from dev.flagship_c_vehicle import resolve_tv_key
        from src.adapters.android import default_remember_path as _remember_path
        from src.server import create_server
        from src.cli import ensure_discovery, default_providers
        server = create_server(adb_remember=_remember_path())
        ensure_discovery(server, default_providers(Namespace()))
        tv_key = args.tv_key or (resolve_tv_key(server) if args.source == 'tv' else None)
        watch_key = args.watch_key or resolve_watch_key(server)
        io = LiveIO(server, args.source, tv_key, watch_key)
        receipt = run_watchshot(io)
        receipt['source'] = args.source
        receipt['watch_key'] = watch_key
        if tv_key:
            receipt['tv_key'] = tv_key
    text = json.dumps(receipt, indent=1)
    print(text)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    return 0 if receipt['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
