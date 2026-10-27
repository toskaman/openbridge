"""V4-07 visual read-back (SIMULATED_VERIFIED: generated PNG, fake Glimmer; no real screenshot in CI)."""
import json
import struct
import tempfile
import unittest
import zlib

from src.ai import visual_readback as vr


def png(w=40, h=50, filt=0):
    rows = []
    for y in range(h):
        px = bytes([y * 5 % 256, 10, 200, 255]) * w        # row colour encodes y
        if filt == 1:                                      # Sub filter
            px = bytes([px[i] if i < 4 else (px[i] - px[i - 4]) & 255 for i in range(len(px))])
        rows.append(bytes([filt]) + px)
    chunk = lambda k, d: struct.pack('>I', len(d)) + k + d + struct.pack('>I', zlib.crc32(k + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b'')


def decode_first_pixel(p):
    ihdr = next(d for k, d in vr._chunks(p) if k == b'IHDR')
    w, h = struct.unpack('>II', ihdr[:8])
    rows = vr._unfilter(zlib.decompress(b''.join(d for k, d in vr._chunks(p) if k == b'IDAT')), w, h, 4)
    return w, h, rows[0][:4]


class FakeGlimmer:
    model_id = 'muse-glimmer:30b-q4_K_M'; extra = {}; options = {}
    def __init__(self, screen='home_launcher', ready=True):
        self.screen, self._ready, self.payloads = screen, ready, []
    def ready(self):
        return self._ready
    def _call(self, payload):
        self.payloads.append(payload)
        return {'screen': self.screen, 'evidence': 'row of app tiles', 'confidence': 'high'}, {}


LAUNCHER = 'mCurrentFocus=Window{1a2b u0 com.google.android.tvlauncher/com.google.android.tvlauncher.MainActivity}'
SETTINGS = 'mCurrentFocus=Window{1a2b u0 com.android.tv.settings/com.android.tv.settings.MainSettings}'


class Crop(unittest.TestCase):
    def test_status_bar_rows_removed(self):
        for f in (0, 1):
            out = vr.crop_status_bar(png(filt=f), 0.2)
            w, h, first = decode_first_pixel(out)
            self.assertEqual((w, h), (40, 40))
            self.assertEqual(first[0], 10 * 5 % 256)          # row 10 is now the first row

    def test_rejects_non_png_and_huge(self):
        with self.assertRaises(ValueError):
            vr.crop_status_bar(b'GIF89a')


class Verdicts(unittest.TestCase):
    def reader(self, windows, power='Awake'):
        return lambda *a: {('dumpsys', 'power'): f'mWakefulness={power}', ('dumpsys', 'window', 'windows'): windows}[a]

    def test_agree_disagree_and_unavailable(self):
        g = FakeGlimmer('home_launcher')
        r = vr.readback(png, self.reader(LAUNCHER), g)
        self.assertEqual(r['verdict'], 'CONFIRMED')
        self.assertEqual(len(r['frame_sha256']), 64)
        self.assertIn('images', g.payloads[0]['messages'][1])
        self.assertEqual(vr.readback(png, self.reader(SETTINGS), FakeGlimmer('home_launcher'))['verdict'], 'INCONCLUSIVE')
        self.assertEqual(vr.readback(png, self.reader(LAUNCHER), FakeGlimmer(ready=False))['verdict'], 'STRUCTURED_ONLY')
        self.assertEqual(vr.readback(png, self.reader(LAUNCHER), None)['verdict'], 'STRUCTURED_ONLY')
        def boom(): raise ValueError('Screen capture unavailable')
        self.assertEqual(vr.readback(boom, self.reader(LAUNCHER), FakeGlimmer())['verdict'], 'STRUCTURED_ONLY')

    def test_sleeping_screen(self):
        r = vr.readback(png, self.reader(LAUNCHER, 'Asleep'), FakeGlimmer('screen_off_or_black'))
        self.assertEqual(r['structured']['screen'], 'screen_off_or_black')
        self.assertEqual(r['verdict'], 'CONFIRMED')

    def test_invalid_model_answer_is_not_trusted(self):
        g = FakeGlimmer('press_ok_button')
        self.assertEqual(vr.readback(png, self.reader(LAUNCHER), g)['verdict'], 'STRUCTURED_ONLY')


class Primitive(unittest.TestCase):
    def test_consent_and_readback_through_executor(self):
        from src.runtime.primitives import Executor
        from tests.runtime.test_primitives import ctx
        with tempfile.TemporaryDirectory() as tmp:
            c, key = ctx(tmp)
            c.android.screencap = lambda serial: png()
            orig = c.android._run
            def run(args, max_bytes=131072):
                if args[3:] == ['dumpsys', 'window', 'windows']: return LAUNCHER
                if args[3:] == ['dumpsys', 'power']: return 'mWakefulness=Awake'
                return orig(args, max_bytes)
            c.android._run = run
            c.vision_broker = FakeGlimmer()
            ex = Executor(c)
            self.assertEqual(ex.execute('visual_readback', key, {})['state'], 'BLOCKED')
            r = ex.execute('visual_readback', key, {}, consent=True)
            self.assertEqual(r['state'], 'VERIFIED', r)
            self.assertEqual(r['after'], 'CONFIRMED')


if __name__ == '__main__':
    unittest.main()
