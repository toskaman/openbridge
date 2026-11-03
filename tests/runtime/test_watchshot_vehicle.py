"""Watchshot vehicle tests (doubles + synthetic PNGs; no adb, no server)."""
import hashlib
import unittest
from types import SimpleNamespace

from dev import watchshot_vehicle as W
from src.runtime import montage as M


def solid(w, h, rgba):
    return M.encode_png(w, h, bytes(rgba) * (w * h))


class ResolveTest(unittest.TestCase):
    def test_picks_single_adb_watch(self):
        devs = [{'key': 'k-tv', 'category': 'tv', 'handles': {'WIFI': 'h'}},
                {'key': 'k-w', 'category': 'watch', 'handles': {'WIFI': 'hw'}},
                {'key': 'k-w2', 'category': 'watch', 'handles': {}}]
        srv = SimpleNamespace(fabric_snapshot={'devices': devs})
        self.assertEqual(W.resolve_watch_key(srv), 'k-w')

    def test_fails_loudly_when_ambiguous(self):
        devs = [{'key': 'k-%d' % i, 'category': 'watch', 'handles': {'WIFI': 'h%d' % i}}
                for i in range(2)]
        with self.assertRaises(SystemExit):
            W.resolve_watch_key(SimpleNamespace(fabric_snapshot={'devices': devs}))

    def test_fails_loudly_when_none(self):
        with self.assertRaises(SystemExit):
            W.resolve_watch_key(SimpleNamespace(fabric_snapshot={'devices': []}))


class PipelineTest(unittest.TestCase):
    def test_self_test_passes(self):
        receipt = W.run_watchshot(W.SelfTestIO())
        self.assertEqual(receipt['verdict'], 'PASS')
        self.assertEqual([s['step'] for s in receipt['steps']],
                         ['capture', 'send', 'view'])

    def test_black_frame_shape_passes_as_bytes(self):
        receipt = W.run_watchshot(W.SelfTestIO(black=True))
        self.assertEqual(receipt['verdict'], 'PASS')  # DRM-black is data, not an error

    def test_hash_mismatch_fails_loudly(self):
        class Evil(W.SelfTestIO):
            def send_fit(self, fit, fw, fh):
                d = super().send_fit(fit, fw, fh)
                d['device_sha256'] = '0' * 64
                return d

        receipt = W.run_watchshot(Evil())
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('differ', receipt['steps'][-1]['reason'])

    def test_missing_view_readback_fails_loudly(self):
        class Blind(W.SelfTestIO):
            def view(self, name):
                return {'focused_app': None, 'power': 'awake'}

        receipt = W.run_watchshot(Blind())
        self.assertEqual(receipt['verdict'], 'FAIL')

    def test_capture_error_recorded_not_raised(self):
        class Boom(W.SelfTestIO):
            def capture(self):
                raise OSError('adb gone')

        receipt = W.run_watchshot(Boom())
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('OSError', receipt['steps'][-1]['reason'])

    def test_fit_actually_shrinks(self):
        raw = solid(1920, 1080, (1, 2, 3, 255))
        fit = M.fit_png(raw, W.WATCH_SIDE)
        self.assertEqual(M.png_size(fit), (448, 252))
        self.assertLess(len(fit), len(raw))


if __name__ == '__main__':
    unittest.main()
