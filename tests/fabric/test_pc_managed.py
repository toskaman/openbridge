"""pc_place_file + pc_wallpaper: gated on full control, fixed shapes only."""
import base64
import hashlib
import unittest
from types import SimpleNamespace

from src.fabric.contracts import Identifier
from src.fabric.registry import Registry
from src.fabric import pc_consent as PC
from src.runtime import montage as M
from src.runtime.capture_store import CaptureStore
from src.runtime.primitives import Executor


PNG = M.encode_png(8, 8, bytes((9, 9, 9, 255)) * 64)


class FakeBridge:
    ident = 'aa01bb02'

    def __init__(self):
        self.jobs = []

    def connected(self):
        return True

    def identity(self, _salt):
        return self.ident

    def run_job(self, command, shell, timeout_s):
        self.jobs.append((command, shell, timeout_s))
        return {'exit_code': 0, 'timed_out': False,
                'stdout_b64': base64.b64encode(b''),
                'stderr_b64': base64.b64encode(b'')}


def rig(tmp):
    reg = Registry()
    key = reg.upsert([Identifier('windows_machine_guid', 'aa01bb02', True)],
                     category='computer', label='PC 1')
    bridge = FakeBridge()
    store = CaptureStore(tmp / 'caps')
    consent = PC.PcConsentStore(tmp / 'pcfc.json')
    ctx = SimpleNamespace(fabric_registry=reg, fabric_salt=b's',
                          fabric_adapters=lambda _p=None: {'windows': bridge},
                          captures_dir=tmp / 'caps', pc_consent=consent)
    return Executor(ctx), key, bridge, store, consent


class PlaceFile(unittest.TestCase):
    def test_blocked_without_full_control(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ex, key, bridge, store, _ = rig(Path(tmp))
            tid = store.put(PNG, kind='cap')
            r = ex.execute('pc_place_file', key,
                           {'transfer_id': tid, 'name': 'wall.png'}, consent=True)
            self.assertNotEqual(r['state'], 'VERIFIED')
            self.assertIn('FULL_CONTROL_OFF', r['errors'][0])
            self.assertEqual(bridge.jobs, [])

    def test_bad_names_rejected_before_bridge(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ex, key, bridge, store, consent = rig(Path(tmp))
            consent.set('aa01bb02', True, confirm=True)
            tid = store.put(PNG, kind='cap')
            for bad in ('../x.png', 'a/b.png', 'x.exe', 'x.png ', 'a$(x).png',
                        "a'b.png", 'x.PnGgg', ''):
                with self.subTest(name=bad):
                    r = ex.execute('pc_place_file', key,
                                   {'transfer_id': tid, 'name': bad}, consent=True)
                    self.assertEqual(r['state'], 'BLOCKED')
            self.assertEqual(bridge.jobs, [])

    def test_place_verifies_hash_through_portal(self):
        import re
        import tempfile
        import urllib.request
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ex, key, bridge, store, consent = rig(Path(tmp))
            consent.set('aa01bb02', True, confirm=True)
            tid = store.put(PNG, kind='cap')

            def agent_dl(command, shell, timeout_s):
                m = re.search(r"Invoke-WebRequest -Uri '(http://[^']+)'", command)
                with urllib.request.urlopen(m.group(1), timeout=10) as r:
                    got = r.read()
                self.assertEqual(shell, 'powershell')
                out = hashlib.sha256(got).hexdigest()
                return {'exit_code': 0, 'timed_out': False,
                        'stdout_b64': base64.b64encode(out.encode()),
                        'stderr_b64': base64.b64encode(b'')}

            bridge.run_job = agent_dl
            r = ex.execute('pc_place_file', key,
                           {'transfer_id': tid, 'name': 'wall.png'}, consent=True)
            self.assertEqual(r['state'], 'VERIFIED')
            self.assertEqual(r['result']['sha256'], hashlib.sha256(PNG).hexdigest())
            self.assertIn('managed', r['result']['remote'])

    def test_non_image_bytes_rejected(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ex, key, bridge, store, consent = rig(Path(tmp))
            consent.set('aa01bb02', True, confirm=True)
            tid = store.put(b'MZ' + b'\x00' * 100, kind='cap')
            r = ex.execute('pc_place_file', key,
                           {'transfer_id': tid, 'name': 'wall.png'}, consent=True)
            self.assertEqual(r['state'], 'BLOCKED')
            self.assertEqual(bridge.jobs, [])


class Wallpaper(unittest.TestCase):
    def test_blocked_without_full_control(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ex, key, bridge, _, _ = rig(Path(tmp))
            r = ex.execute('pc_wallpaper', key, {'name': 'wall.png'}, consent=True)
            self.assertNotEqual(r['state'], 'VERIFIED')
            self.assertIn('FULL_CONTROL_OFF', r['errors'][0])
            self.assertEqual(bridge.jobs, [])

    def test_apply_verified_with_previous_recorded(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ex, key, bridge, _, consent = rig(Path(tmp))
            consent.set('aa01bb02', True, confirm=True)
            prev = 'C:\\Users\\o\\AppData\\Local\\OpenBridge\\managed\\old.png'
            cur = 'C:\\Users\\o\\AppData\\Local\\OpenBridge\\managed\\wall.png'

            def agent_apply(command, shell, timeout_s):
                self.assertIn('SystemParametersInfo(20,0,$f,3)', command)
                out = 'PREV|%s\nCUR|%s\n' % (prev, cur)
                return {'exit_code': 0, 'timed_out': False,
                        'stdout_b64': base64.b64encode(out.encode()),
                        'stderr_b64': base64.b64encode(b'')}

            bridge.run_job = agent_apply
            r = ex.execute('pc_wallpaper', key, {'name': 'wall.png'}, consent=True)
            self.assertEqual(r['state'], 'VERIFIED')
            self.assertEqual(r['result']['previous'], prev)
            self.assertTrue(r['result']['restorable'])

    def test_missing_file_is_blocked_not_failed(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            ex, key, bridge, _, consent = rig(Path(tmp))
            consent.set('aa01bb02', True, confirm=True)

            def agent_missing(command, shell, timeout_s):
                return {'exit_code': 2, 'timed_out': False,
                        'stdout_b64': base64.b64encode(b'MISSING\n'),
                        'stderr_b64': base64.b64encode(b'')}

            bridge.run_job = agent_missing
            r = ex.execute('pc_wallpaper', key, {'name': 'wall.png'}, consent=True)
            self.assertEqual(r['state'], 'BLOCKED')
            self.assertIn('MISSING_FILE', r['errors'][0])


if __name__ == '__main__':
    unittest.main()
