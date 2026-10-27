import tempfile
import unittest

from src.runtime.primitives import Executor
from src.runtime.watchers import Watchers, WatchError
from tests.runtime.test_primitives import ctx


class Watch(unittest.TestCase):
    def setUp(self):
        self.c, self.key = ctx(tempfile.mkdtemp())
        self.ex = Executor(self.c)

    def test_edge_triggered_events_and_unavailability(self):
        w = Watchers(self.ex, sleep=lambda s: True)        # loop runs one check and exits
        wid = w.start(self.key, 'uptime', 'ge', 1.0, 30)['watch_id']
        __import__('time').sleep(0.2)                       # let the loop's own first check finish
        w.check_once(wid); w.check_once(wid)
        kinds = [e['kind'] for e in self.ex.events_since(0)]
        self.assertEqual(kinds.count('watch_triggered'), 1)          # several polls, one crossing
        trig = next(e for e in self.ex.events_since(0) if e['kind'] == 'watch_triggered')
        self.assertEqual((trig['value'], trig['finding_kind']), (1.0, 'OBSERVED'))
        self.c.android._handles = {}                                  # device gone: event, never a fake value
        w.check_once(wid)
        self.assertEqual(self.ex.events_since(0)[-1]['kind'], 'watch_unavailable')

    def test_bounds(self):
        w = Watchers(self.ex, sleep=lambda s: True)
        for args in [('uptime', 'gt', 1, 5), ('uptime', 'xx', 1, 30), ('up time;rm', 'gt', 1, 30), ('wifi', 'gt', 'enabled', 30), ('uptime', 'gt', True, 30)]:
            with self.assertRaises(WatchError):
                w.start(self.key, *args)

    def test_primitives_and_consent(self):
        r = self.ex.execute('watch_start', self.key, {'finding': 'uptime', 'op': 'gt', 'threshold_number': 0.5, 'interval_s': 30}, consent=False)
        self.assertIn('CONSENT_REQUIRED', r['errors'][0])
        r = self.ex.execute('watch_start', self.key, {'finding': 'uptime', 'op': 'gt', 'interval_s': 30}, consent=True)
        self.assertIn('INVALID_WATCH', r['errors'][0])
        r = self.ex.execute('watch_start', self.key, {'finding': 'wifi', 'op': 'eq', 'threshold_text': 'enabled', 'interval_s': 30, 'lifetime_s': 60}, consent=True)
        wid = r['result']['watch_id']
        self.assertEqual(r['after'], 'RUNNING')
        s = self.ex.execute('watch_stop', self.key, {'watch_id': wid})
        self.assertEqual((s['state'], s['after']), ('VERIFIED', 'STOPPED'))
        self.assertIn('UNKNOWN_WATCH', self.ex.execute('watch_stop', self.key, {'watch_id': 'nope'})['errors'][0])


if __name__ == '__main__':
    unittest.main()
