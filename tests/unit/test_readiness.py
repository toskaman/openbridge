"""Readiness: required statuses, per-feature truth, no fake global READY."""
import unittest

from src.runtime.readiness import STATUSES, collect


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
