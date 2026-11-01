"""V4-01 timeline + hypotheses (SIMULATED_VERIFIED: synthetic drills; labels live in a separate file)."""
import json
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.runtime import hypotheses
from src.runtime.timeline import Timeline
from src.runtime.primitives import Executor
from tests.runtime.test_primitives import ctx

HERE = Path(__file__).parent / 'drills'
FORBIDDEN = ('caused by', 'root cause is', 'proves', 'proven cause:')


def load(name):
    tl = Timeline(clock=lambda: 10_000)
    for dev, cat, n, v, t in sorted(json.loads((HERE / 'timeline_drills.json').read_text(encoding='utf-8'))[name], key=lambda r: r[4]):
        tl.observe(dev, cat, n, v, 'drill', t=t)
    return tl


class Drills(unittest.TestCase):
    def test_every_drill_matches_its_independent_label(self):
        labels = json.loads((HERE / 'timeline_labels.json').read_text(encoding='utf-8'))
        for name, lab in labels.items():
            with self.subTest(drill=name):
                a = hypotheses.analyze(load(name).rows(), lab['target'])
                if 'verdict' in lab:
                    self.assertEqual(a['verdict'], lab['verdict'])
                    continue
                ids = [h['id'] for h in a['hypotheses']]
                self.assertGreaterEqual(len(ids), 2, 'at least two competing hypotheses')
                self.assertEqual(ids[-1], 'unobserved_cause')
                if 'top' in lab:
                    self.assertEqual(ids[0], lab['top'])
                if 'top_any_of' in lab:
                    self.assertIn(ids[0], lab['top_any_of'])
                for m in lab.get('must_include', ()):
                    self.assertIn(m, ids)
                if 'top_confidence' in lab:
                    self.assertEqual(a['hypotheses'][0]['confidence'], lab['top_confidence'])

    def test_every_hypothesis_cites_existing_entries_and_never_claims_cause(self):
        for name in json.loads((HERE / 'timeline_drills.json').read_text(encoding='utf-8')):
            tl = load(name)
            ids = {e['id'] for e in tl.rows()}
            a = hypotheses.analyze(tl.rows(), 'tv')
            for h in a['hypotheses']:
                self.assertTrue(set(h['cites']) <= ids)
                self.assertEqual(h['kind'], 'INFERRED')
                self.assertFalse(any(f in h['statement'].lower() for f in FORBIDDEN))

    def test_counterexamples_lower_confidence(self):
        a = hypotheses.analyze(load('coincidence_once').rows(), 'tv')
        h = a['hypotheses'][0]
        self.assertEqual(h['counterexamples']['occurrences_without_symptom'], 2)
        self.assertEqual(h['confidence'], 'low')


class TimelineStore(unittest.TestCase):
    def test_only_transitions_are_kept(self):
        tl = Timeline(clock=lambda: 0)
        for t in range(10):
            tl.observe('d', 'tv', 'wifi', 'enabled', t=t)
        tl.observe('d', 'tv', 'wifi', 'disabled', t=11)
        rows = tl.rows()
        self.assertEqual([(r['kind'], r['value'], r['previous']) for r in rows], [('first', 'enabled', None), ('change', 'disabled', 'enabled')])
        self.assertEqual(rows[0]['last_confirmed_at'][11:19], '00:00:09')

    def test_failed_read_becomes_a_link_fact(self):
        tl = Timeline(clock=lambda: 0)
        tl.ingest_receipt('d', 'phone', {'state': 'BLOCKED', 'errors': ['DEVICE_UNAVAILABLE: no link']})
        tl.ingest_receipt('d', 'phone', {'state': 'BLOCKED', 'errors': ['CONSENT_REQUIRED: x']})
        self.assertEqual([(r['name'], r['value']) for r in tl.rows()], [('link', 'lost')])

    def test_bounded(self):
        tl = Timeline(clock=lambda: 0, max_entries=50)
        for i in range(500):
            tl.observe('d', 'tv', 'n', i, t=i)
        self.assertEqual(len(tl.rows(limit=10_000)), 50)


class Probe(unittest.TestCase):
    def test_probe_is_read_only_and_feeds_the_timeline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            c, key = ctx(tmp)
            ex = Executor(c)
            ex._sleep = lambda s: None
            r = ex.execute('diagnostic_probe', key, {'device_keys': [key], 'samples': 2, 'interval_s': 2})
            self.assertEqual(r['state'], 'VERIFIED', r)
            self.assertEqual(len(r['result']['reads']), 2)
            for args in c.android.runs:
                self.assertIn(tuple(args[3:]), __import__('src.runtime.diagnostics', fromlist=['x']).ANDROID_READS)
            names = {e['name'] for e in ex.timeline().rows()}
            self.assertIn('uptime', names)
            self.assertIn('link', names)

    def test_probe_bounds(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            c, key = ctx(tmp)
            ex = Executor(c)
            r = ex.execute('diagnostic_probe', key, {'device_keys': [key], 'samples': 5, 'interval_s': 30})
            self.assertEqual(r['state'], 'BLOCKED')
            r = ex.execute('diagnostic_probe', key, {'device_keys': ['nope']})
            self.assertEqual(r['state'], 'BLOCKED')

    def test_read_facts_receipts_feed_the_timeline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            c, key = ctx(tmp)
            ex = Executor(c)
            ex.execute('read_facts', key, {})
            c.android._handles = {}
            ex.execute('read_facts', key, {})
            link = [e['value'] for e in ex.timeline().rows(key) if e['name'] == 'link']
            self.assertEqual(link, ['up', 'lost'])
            a = hypotheses.analyze(ex.timeline().rows(), key)
            self.assertEqual(a['verdict'], 'HYPOTHESES')
            self.assertGreaterEqual(len(a['hypotheses']), 1)


if __name__ == '__main__':
    unittest.main()
