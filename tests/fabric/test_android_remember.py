"""Remembered WiFi-ADB reconnect: exact remembered endpoints only, never a scan."""
import json
import unittest
from types import SimpleNamespace

from src.adapters.android import AndroidAdapter


def run_factory(devices_out, calls):
    def run(args, **kw):
        calls.append(args[1:])
        if args[1:3] == ['devices', '-l']:
            return SimpleNamespace(returncode=0, stdout=devices_out)
        if args[1] == 'connect':
            return SimpleNamespace(returncode=0, stdout='connected\n')
        return SimpleNamespace(returncode=0, stdout='')
    return run


WIFI_DEVICES = 'List of devices attached\n192.168.1.14:5555\tdevice product:x model:y device:z\n\n'
EMPTY_DEVICES = 'List of devices attached\n\n'


class Remember(unittest.TestCase):
    def test_seen_wifi_serial_is_persisted(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            ad = AndroidAdapter(executable='adb', runner=run_factory(WIFI_DEVICES, calls),
                                remember_path=str(Path(tmp) / 'adb_known.json'))
            ad.discover()
            saved = json.loads((Path(tmp) / 'adb_known.json').read_text(encoding='utf-8'))
            self.assertIn('192.168.1.14:5555', saved['endpoints'])

    def test_reconnect_targets_only_remembered_private(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'adb_known.json'
            p.write_text(json.dumps({'endpoints': ['192.168.1.14:5555', '8.8.8.8:5555',
                                                  '127.0.0.1:5555', 'not-an-endpoint',
                                                  '192.168.1.15:99999']}), encoding='utf-8')
            calls = []
            ad = AndroidAdapter(executable='adb', runner=run_factory(EMPTY_DEVICES, calls),
                                remember_path=str(p))
            ad.discover()
            connects = [c[1] for c in calls if c and c[0] == 'connect']
            self.assertEqual(connects, ['192.168.1.14:5555'])

    def test_no_reconnect_when_already_connected(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'adb_known.json'
            p.write_text(json.dumps({'endpoints': ['192.168.1.14:5555']}), encoding='utf-8')
            calls = []
            ad = AndroidAdapter(executable='adb', runner=run_factory(WIFI_DEVICES, calls),
                                remember_path=str(p))
            ad.discover()
            self.assertEqual([c for c in calls if c and c[0] == 'connect'], [])

    def test_throttles_repeated_attempts(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'adb_known.json'
            p.write_text(json.dumps({'endpoints': ['192.168.1.14:5555']}), encoding='utf-8')
            calls = []
            ad = AndroidAdapter(executable='adb', runner=run_factory(EMPTY_DEVICES, calls),
                                remember_path=str(p))
            ad.discover()
            ad.discover()
            connects = [c for c in calls if c and c[0] == 'connect']
            self.assertEqual(len(connects), 1)

    def test_bounded_to_four_endpoints(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            eps = ['192.168.1.%d:5555' % i for i in range(10, 16)]
            p = Path(tmp) / 'adb_known.json'
            p.write_text(json.dumps({'endpoints': eps}), encoding='utf-8')
            calls = []
            ad = AndroidAdapter(executable='adb', runner=run_factory(EMPTY_DEVICES, calls),
                                remember_path=str(p))
            ad.discover()
            connects = [c for c in calls if c and c[0] == 'connect']
            self.assertEqual(len(connects), 4)

    def test_corrupt_file_ignored(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'adb_known.json'
            p.write_text('{oops', encoding='utf-8')
            calls = []
            ad = AndroidAdapter(executable='adb', runner=run_factory(EMPTY_DEVICES, calls),
                                remember_path=str(p))
            doc = ad.discover()
            self.assertEqual(doc['status'], 'WAITING_FOR_DEVICE')
            self.assertEqual([c for c in calls if c and c[0] == 'connect'], [])

    def test_disabled_by_default(self):
        calls = []
        ad = AndroidAdapter(executable='adb', runner=run_factory(EMPTY_DEVICES, calls))
        ad.discover()
        self.assertEqual([c for c in calls if c and c[0] == 'connect'], [])


    def test_fresh_boot_does_not_suppress_first_reconnect(self):
        # Regression (CI ubuntu 2/2): the throttle used 0 as the
        # "never attempted" sentinel against time.monotonic(), so on
        # a host booted <REMEMBER_WINDOW_S ago the FIRST reconnect
        # was wrongly throttled. A first attempt must always fire.
        import tempfile
        import time as time_mod
        import unittest.mock
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'adb_known.json'
            p.write_text(json.dumps({'endpoints': ['192.168.1.14:5555']}),
                         encoding='utf-8')
            calls = []
            ad = AndroidAdapter(executable='adb',
                                runner=run_factory(EMPTY_DEVICES, calls),
                                remember_path=str(p))
            with unittest.mock.patch.object(time_mod, 'monotonic',
                                            return_value=5.0):
                ad.discover()
            connects = [c for c in calls if c and c[0] == 'connect']
            self.assertEqual(len(connects), 1)


if __name__ == '__main__':
    unittest.main()
