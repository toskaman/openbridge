"""V4-08 Wear OS dynamic manifest (SIMULATED_VERIFIED with a fake watch over the same ADB read path)."""
import tempfile
import unittest

from src.fabric import wear_manifest as wm
from src.runtime.primitives import Executor
from tests.runtime.test_primitives import ctx

PM = '\n'.join('feature:' + f for f in ('android.hardware.type.watch', 'android.hardware.bluetooth_le', 'android.hardware.wifi',
                                         'android.hardware.sensor.heartrate', 'android.software.secret_thing', 'reqGlEsVersion=0x30002'))


class Manifest(unittest.TestCase):
    def test_from_reported_features_only(self):
        m = wm.build(PM, [{'name': 'battery_level'}, {'name': 'uptime'}])
        caps = {c['capability']: c for c in m['capabilities']}
        self.assertIn('heart_rate_sensor_present', caps)
        self.assertEqual(caps['heart_rate_sensor_present']['level'], 'observe')
        self.assertIn('battery_read', caps)
        self.assertNotIn('gps_present', caps)
        self.assertEqual(caps['control']['status'], 'BLOCKED')
        self.assertFalse(any('secret' in c['evidence'] for c in m['capabilities']))

    def test_not_a_watch_and_change_detection(self):
        self.assertIsNone(wm.build('feature:android.hardware.wifi', []))
        a = wm.build(PM, [])['sha256']
        b = wm.build(PM.replace('feature:android.hardware.sensor.heartrate\n', ''), [])['sha256']
        self.assertNotEqual(a, b)

    def test_read_facts_on_watch(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, key = ctx(tmp)
            c.fabric_registry.devices[key]['category'] = 'watch'
            orig = c.android._run
            c.android._run = lambda args, max_bytes=131072: PM if args[3:] == ['pm', 'list', 'features'] else orig(args, max_bytes)
            r = Executor(c).execute('read_facts', key, {})
            self.assertEqual(r['state'], 'VERIFIED', r)
            self.assertEqual(r['result']['wear_manifest']['kind'], 'wear_os_dynamic')


if __name__ == '__main__':
    unittest.main()
