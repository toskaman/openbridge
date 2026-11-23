"""Quality reports: nothing without consent, nothing identifying, firmware regressions found across homes."""
import json
import tempfile
import unittest
from pathlib import Path

from src.runtime import quality_reports as Q

T0 = 1_795_000_000.0          # 2026-11


def receipt(ok=True, seconds=0.8, state=None):
    return {'state': state or ('VERIFIED' if ok else 'FAILED'), 'verified': ok, 'device_key': 'dev-secret-key',
            'started_at': '2026-11-23T10:00:00+00:00', 'finished_at': '2026-11-23T10:00:%02d.%06d+00:00' % (int(seconds), round(seconds % 1 * 1e6)),
            'before': 'off', 'after': 'on', 'entity_id': 'light.kitchen_secret'}


ACME = {'manufacturer': 'Acme', 'model': 'Glow 2', 'firmware': '1.4.0'}


def home(firmware, ok, ko, seconds=0.8):
    q = Q.Quality(persist=False, clock=lambda: T0)
    q.enable()
    for _ in range(ok):
        q.observe(dict(ACME, firmware=firmware), 'light', 'ha_set:set_brightness', receipt(True, seconds))
    for _ in range(ko):
        q.observe(dict(ACME, firmware=firmware), 'light', 'ha_set:set_brightness', receipt(False, seconds))
    return q.export()


class Consent(unittest.TestCase):
    def test_off_by_default_records_nothing(self):
        q = Q.Quality(persist=False, clock=lambda: T0)
        self.assertFalse(q.enabled)
        self.assertFalse(q.observe(ACME, 'light', 'turn_on', receipt()))
        self.assertEqual(q.months, {})

    def test_disable_and_forget(self):
        with tempfile.TemporaryDirectory() as d:
            q = Q.Quality(Path(d) / 'q.json', clock=lambda: T0)
            q.enable()
            q.observe(ACME, 'light', 'turn_on', receipt())
            self.assertEqual(Q.Quality(Path(d) / 'q.json').export('2026-11')['rows'][0]['runs'], 1)
            q.disable(forget=True)
            q.observe(ACME, 'light', 'turn_on', receipt())
            self.assertEqual(Q.Quality(Path(d) / 'q.json').months, {})


class Export(unittest.TestCase):
    def test_export_holds_no_identifier(self):
        doc = home('1.4.0', 3, 1)
        text = json.dumps(doc)
        for secret in ('dev-secret-key', 'kitchen', 'light.kitchen', '10:00', '2026-11-23'):
            self.assertNotIn(secret, text)
        row = doc['rows'][0]
        self.assertEqual((row['runs'], row['verified'], row['failed']), (4, 3, 1))
        self.assertEqual(sum(row['latency']), 4)
        Q.validate_export(doc)

    def test_bad_month_and_bad_file(self):
        with self.assertRaises(Q.QualityError):
            Q.Quality(persist=False).export('2026-13')
        with self.assertRaises(Q.QualityError):
            Q.build_report([{'format': Q.FORMAT, 'kind': 'export', 'month': '2026-11', 'rows': [{'runs': -1}]}])


class Regressions(unittest.TestCase):
    def test_success_rate_regression_across_homes(self):
        exports = [home('1.4.0', 24, 1) for _ in range(3)] + [home('1.5.0', 18, 7) for _ in range(3)]
        rep = Q.build_report(exports)
        self.assertEqual(len(rep['regressions']), 1)
        g = rep['regressions'][0]
        self.assertEqual((g['kind'], g['from_firmware'], g['to_firmware']), ('success_rate', '1.4.0', '1.5.0'))
        self.assertTrue(all(r['few_homes'] for r in rep['rows']))          # 3 homes < MIN_HOMES
        md = Q.markdown(rep)
        self.assertIn('1.4.0 → 1.5.0', md)

    def test_latency_regression(self):
        rep = Q.build_report([home('2.0', 30, 0, 0.4), home('2.1', 30, 0, 3.0)])
        self.assertEqual([g['kind'] for g in rep['regressions']], ['latency_p95'])

    def test_too_few_runs_is_not_a_regression(self):
        rep = Q.build_report([home('1.4.0', 10, 0), home('1.5.0', 2, 8)])
        self.assertEqual(rep['regressions'], [])

    def test_versions_sort_numerically(self):
        rep = Q.build_report([home('1.10.0', 25, 0), home('1.9.0', 10, 15)])
        self.assertEqual(rep['regressions'], [])      # 1.9 -> 1.10 is an improvement, not a regression


class Wiring(unittest.TestCase):
    def test_learner_feeds_quality_only_with_consent(self):
        from src.runtime.device_learning import Learner
        learner = Learner(persist=False)
        q = Q.Quality(persist=False, clock=lambda: T0)
        learner.listeners.append(lambda r, c, a: q.observe(ACME, c, a, r))
        learner.observe_receipt(receipt(), category='light', action='ha_set:turn_on')
        self.assertEqual(q.months, {})
        q.enable()
        learner.observe_receipt(receipt(), category='light', action='ha_set:turn_on')
        self.assertEqual(q.export()['rows'][0]['action'], 'ha_set:turn_on')

    def test_a_failing_listener_never_breaks_learning(self):
        from src.runtime.device_learning import Learner
        learner = Learner(persist=False)
        learner.listeners.append(lambda *a: 1 / 0)
        learner.observe_receipt(receipt(), category='light', action='ha_set:turn_on')
        self.assertIn('dev-secret-key', learner.devices)

    def test_home_assistant_device_info(self):
        from src.adapters import home_assistant as HA
        seen = {}

        def http(method, url, token, body=None, timeout=None):
            seen['url'], seen['tpl'] = url, body['template']
            return [['light.kitchen', 'Acme', 'Glow 2', '1.4.0'], ['evil', 'x', 'y', 'z']]
        ha = HA.HomeAssistant('http://192.168.1.10:8123', 'token', http=http)
        info = ha.device_info(['light.kitchen', 'not an id; {{ x }}'])
        self.assertEqual(info, {'light.kitchen': {'manufacturer': 'Acme', 'model': 'Glow 2', 'firmware': '1.4.0'}})
        self.assertTrue(seen['url'].endswith('/api/template'))
        self.assertNotIn('not an id', seen['tpl'])


if __name__ == '__main__':
    unittest.main()
