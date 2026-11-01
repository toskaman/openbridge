"""F90 endurance harness tests (Campaign One S3.5). NEW FILE, no src changes.

Covers the long-session harness in dev/f90_endurance.py at small deterministic
scales: report schema, exact op/error totals, injected-fault measurement,
bounded fabric growth, graceful shutdown after heavy use, and external stop.
"""
import threading
import unittest

from dev import f90_endurance as E


def small_run(**over):
    kw = dict(cycles=8, rate=8.0, workers=2, devices=24, relays=4, seed=7,
              sample_interval=0.5)
    kw.update(over)
    return E.run(**kw)


class ReportSchemaTests(unittest.TestCase):
    def test_all_metric_families_present(self):
        r = small_run()
        for key in ('config', 'ops', 'ops_total', 'errors', 'error_total',
                    'error_rate', 'latency_ms', 'cpu', 'memory', 'threads',
                    'sockets', 'queue', 'journal', 'fabric', 'shutdown'):
            self.assertIn(key, r)
        self.assertIn('p95', r['latency_ms'])
        self.assertIn('rss_delta_mb', r['memory'])
        self.assertIn('delta', r['threads'])
        self.assertIn('delta', r['sockets'])
        self.assertIn('max_depth', r['queue'])
        self.assertIn('bytes', r['journal'])
        self.assertIn('graceful', r['shutdown'])

    def test_every_issued_cycle_produces_one_dispatch_latency(self):
        r = small_run()
        self.assertEqual(r['config']['issued'], 8)
        self.assertEqual(r['latency_ms']['n'], 8)
        self.assertEqual(r['ops']['discover'], 8)
        self.assertEqual(r['ops']['dispatch'], 8)
        self.assertEqual(r['ops']['journal'], 8)


class DeterminismTests(unittest.TestCase):
    def test_same_seed_reproduces_totals(self):
        kw = dict(cycles=40, rate=20.0, workers=2, devices=40, relays=4, seed=11)
        first, second = small_run(**kw), small_run(**kw)
        self.assertEqual(first['ops'], second['ops'])
        self.assertEqual(first['errors'], second['errors'])
        self.assertEqual(first['config']['issued'], second['config']['issued'])
        self.assertEqual(first['fabric'], second['fabric'])
        self.assertEqual(first['ops']['pair'], 4 + 1)  # pool + one churn at seq 24
        self.assertEqual(first['ops']['revoke'], 1)
        self.assertEqual(first['ops']['flap'], 0)
        self.assertEqual(first['error_total'], 0)


class FaultMeasurementTests(unittest.TestCase):
    def test_injected_faults_counted_with_low_error_rate(self):
        r = small_run(cycles=140, rate=40.0, workers=2, devices=60, relays=4)
        # Deterministic fault schedule: malformed at seq 60, timeout at seq 100.
        self.assertEqual(r['errors'], {'RelayError': 2})
        self.assertEqual(r['error_total'], 2)
        self.assertLess(r['error_rate'], 0.05)
        self.assertGreater(r['error_rate'], 0.0)
        # Churn at seq 24/49/74/99/124, flap recovery at seq 59/119.
        self.assertEqual(r['ops']['flap'], 2)
        self.assertEqual(r['ops']['revoke'], 5 + 2)
        self.assertEqual(r['ops']['pair'], 4 + 5 + 2)

    def test_bounded_fabric_and_threads(self):
        r = small_run(cycles=60, rate=20.0, workers=2, devices=60, relays=4)
        self.assertLess(r['fabric']['devices'], 1200)  # far under the 2000 cap
        self.assertLess(r['fabric']['links'], 2500)
        self.assertLessEqual(r['threads']['delta'], 0)
        self.assertLessEqual(r['threads']['peak'],
                             r['threads']['start'] + 2 + 1)  # workers + sampler
        self.assertLessEqual(r['queue']['max_depth'], 4)  # bounded queue maxsize
        self.assertEqual(r['config']['shed'], 0)
        # Simulated wire uses no sockets by construction; None means psutil
        # is absent so the delta is unmeasurable (stdlib-only envs).
        self.assertIn(r['sockets']['delta'], (0, None))
        self.assertLessEqual(r['journal']['open_entries'], 5)
        self.assertEqual(r['journal']['tmp_debris'], [])


class ShutdownTests(unittest.TestCase):
    def test_graceful_shutdown_after_heavy_use(self):
        r = small_run(cycles=120, rate=60.0, workers=4, devices=120, relays=8)
        self.assertTrue(r['shutdown']['graceful'])
        self.assertEqual(r['shutdown']['workers_hung'], [])
        self.assertEqual(r['shutdown']['harness_threads_live'], [])
        self.assertEqual(r['queue']['pending_at_shutdown'], 0)
        self.assertLessEqual(r['threads']['delta'], 0)
        self.assertEqual(r['journal']['tmp_debris'], [])
        self.assertTrue(r['journal']['dir_removed'])
        self.assertLess(r['shutdown']['drain_s'], E.SHUTDOWN_JOIN_S)
        self.assertEqual(r['ops']['discover'], 120)

    def test_external_stop_still_shuts_down_gracefully(self):
        stop = threading.Event()
        # Pool enrollment costs ~1s of PBKDF2 before the first cycle issues.
        timer = threading.Timer(2.0, stop.set)  # event-driven stop, no polling
        timer.start()
        try:
            r = E.run(cycles=1000, rate=20.0, workers=2, devices=24, relays=4,
                      seed=7, sample_interval=0.5, stop=stop)
        finally:
            timer.cancel()
        self.assertLess(r['config']['issued'], 1000)
        self.assertGreater(r['config']['issued'], 0)
        self.assertTrue(r['shutdown']['graceful'])
        self.assertEqual(r['shutdown']['harness_threads_live'], [])
        self.assertLessEqual(r['threads']['delta'], 0)


if __name__ == '__main__':
    unittest.main()
