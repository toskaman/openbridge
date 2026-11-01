"""Readiness: required statuses, per-feature truth, no fake global READY."""
import unittest

from src.runtime.readiness import OPTIONAL, REQUIRED, STATUSES, collect, plain_line


def probes_all_ready():
    return {'core': 'READY', 'os': 'READY', 'local_fast': 'READY',
            'local_quality': 'READY', 'cloud': 'READY', 'devices': 'READY',
            'evidence': 'READY', 'storage': 'READY'}


class ReadinessTests(unittest.TestCase):
    def test_status_vocabulary_is_exact(self):
        self.assertEqual(sorted(STATUSES), ['API_UNAVAILABLE', 'AUTH_REQUIRED', 'BLOCKED', 'INCOMPATIBLE',
                                            'INSUFFICIENT_RESOURCES', 'INVALID', 'MISSING', 'MODEL_NOT_FOUND',
                                            'NOT_TESTED', 'PERMISSION_REQUIRED', 'READY'])

    def test_global_ready_only_when_everything_ready(self):
        report = collect(probes_all_ready())
        self.assertEqual(report['global'], 'READY')

    def test_one_missing_blocks_global_but_keeps_per_feature(self):
        probes = probes_all_ready()
        probes['cloud'] = 'MISSING'
        report = collect(probes)
        self.assertNotEqual(report['global'], 'READY')
        self.assertEqual(report['features']['cloud'], 'MISSING')
        self.assertEqual(report['features']['core'], 'READY')

    def test_unknown_probe_value_is_invalid(self):
        report = collect({'core': 'MAYBE'})
        self.assertEqual(report['features']['core'], 'INVALID')
        self.assertNotEqual(report['global'], 'READY')

    def test_report_is_json_safe(self):
        import json
        json.dumps(collect(probes_all_ready()))


class RequiredOptionalSplitTests(unittest.TestCase):
    """Judge-C W2: optional extras (models/cloud/adb) must not block the demo."""

    def test_split_covers_every_doctor_probe_exactly_once(self):
        self.assertEqual(set(REQUIRED) | set(OPTIONAL), set(probes_all_ready()))
        self.assertFalse(set(REQUIRED) & set(OPTIONAL))

    def test_required_ready_despite_optional_missing(self):
        probes = {name: 'READY' for name in REQUIRED}
        probes.update({'local_fast': 'MODEL_NOT_FOUND', 'local_quality': 'MODEL_NOT_FOUND',
                       'cloud': 'MISSING', 'devices': 'MISSING'})
        report = collect(probes, required=REQUIRED)
        self.assertEqual(report['global'], 'READY')
        self.assertEqual(report['overall'], 'BLOCKED')
        self.assertTrue(all(v == 'READY' for v in report['required'].values()))
        self.assertEqual(report['optional']['cloud'], 'MISSING')

    def test_required_failure_blocks(self):
        probes = {name: 'READY' for name in REQUIRED}
        probes.update({name: 'READY' for name in OPTIONAL})
        probes['evidence'] = 'INVALID'
        report = collect(probes, required=REQUIRED)
        self.assertEqual(report['global'], 'BLOCKED')
        self.assertEqual(report['required']['evidence'], 'INVALID')

    def test_unprobed_required_probe_blocks(self):
        report = collect({'core': 'READY'}, required=REQUIRED)
        self.assertEqual(report['global'], 'BLOCKED')
        self.assertEqual(report['required']['os'], 'NOT_TESTED')

    def test_plain_lines_are_plain_language(self):
        self.assertEqual(plain_line('cloud', 'MISSING'), 'Meta cloud key: missing')
        self.assertEqual(plain_line('local_fast', 'MODEL_NOT_FOUND'),
                         'local fast model (Llama 3B): model not installed')
        self.assertEqual(plain_line('mystery_probe', 'SOME_STATUS'),
                         'mystery probe: some status')
