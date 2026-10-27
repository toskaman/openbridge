import unittest
from types import SimpleNamespace

from src.adapters.android import AndroidAdapter
from src.fabric.guidance import guide


class WatchGuide(unittest.TestCase):
    def test_samsung_and_generic_steps(self):
        g = guide('watch_wireless_debugging', manufacturer='samsung')
        self.assertIn('Software version', ' '.join(g['steps']))
        self.assertIn('Pair new device', ' '.join(g['steps']))
        self.assertIn('Build number', ' '.join(guide('watch_wireless_debugging', manufacturer='google')['steps']))
        self.assertEqual(guide('watch_pair_failed')['issue'], 'watch_pair_failed')


class FakeRun:
    def __init__(self, outputs):
        self.outputs, self.calls = outputs, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd[1:])
        key = cmd[1]
        return SimpleNamespace(returncode=0, stdout=self.outputs.get(key, ''), stderr='')


class WatchPair(unittest.TestCase):
    def adapter(self, outputs):
        a = AndroidAdapter(runner=FakeRun(outputs))
        return a

    def test_validation_refuses_bad_input(self):
        a = self.adapter({})
        for args in (('8.8.8.8', 34947, '123456'), ('192.168.1.14', 80, '123456'), ('192.168.1.14', 34947, '12ab56'), ('127.0.0.1', 34947, '123456')):
            with self.assertRaises(ValueError):
                a.pair_wireless(*args)
        self.assertEqual(a.runner.calls, [])           # nothing sent to adb

    def test_pair_failed_and_success(self):
        a = self.adapter({'pair': 'Failed: Wrong password or connection was dropped.'})
        self.assertEqual(a.pair_wireless('192.168.1.14', 34947, '597174'), ('PAIR_FAILED', None))
        ok = self.adapter({'pair': 'Successfully paired to 192.168.1.14:34947',
                           'mdns': 'adb-X\t_adb-tls-connect._tcp\t192.168.1.14:42437\n',
                           'connect': 'connected to 192.168.1.14:42437',
                           'devices': 'List of devices attached\n192.168.1.14:42437\tdevice product:x model:SM_L310 device:w transport_id:9\n'})
        state, target = ok.pair_wireless('192.168.1.14', 34947, '597174')
        self.assertEqual(target, '192.168.1.14:42437')
        self.assertIn(['connect', '192.168.1.14:42437'], ok.runner.calls)


if __name__ == '__main__':
    unittest.main()
