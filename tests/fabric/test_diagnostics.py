"""Campaign Two S4.5: Universal Device Diagnostics. No network, no ADB, no
hardware, no live model: every bundle below is an in-memory observed-facts
fixture and every proposer is the deterministic stub or a fake chat."""
import json
import unittest

from src.fabric.diagnostics import (
    QUESTIONS, LIMIT, RECOMMENDATIONS, DiagnosticError, DeterministicStubProposer,
    MetaProposer, analyze, diagnose,
)


def fact(name, value, source='ADB', unit=None, confidence='measured'):
    return {'name': name, 'value': value, 'unit': unit, 'source': source,
            'observed_at': '2026-11-01T00:00:00+00:00', 'confidence': confidence}


def dev(oid, category, label, *facts):
    return {'opaque_id': oid, 'category': category, 'label': label, 'facts': list(facts)}


def fake_chat_factory(bodies):
    calls = []

    def chat(payload):
        calls.append(payload)
        body = bodies[min(len(calls) - 1, len(bodies) - 1)]
        return {'model': 'meta-1', 'prompt_eval_count': 10, 'eval_count': 5,
                'message': {'role': 'assistant', 'content': json.dumps(body)}}

    chat.calls = calls
    return chat


class DiagnosticsContractTests(unittest.TestCase):
    def test_seven_why_questions(self):
        self.assertEqual(set(QUESTIONS), {'battery_drain', 'best_pc_for_dev', 'strongest_connectivity',
                                          'tv_control_loss', 'relay_unavailable', 'watch_sleep_drops',
                                          'what_to_install'})

    def test_unknown_question_rejected(self):
        bundle = {'devices': [dev('d1', 'phone', 'Phone', fact('battery_percent', 50))]}
        with self.assertRaises(DiagnosticError):
            diagnose('why_is_the_sky_blue', bundle, DeterministicStubProposer())

    def test_unknown_fact_rejected(self):
        bundle = {'devices': [dev('d1', 'phone', 'Phone', fact('benchmark_score', 9999))]}
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', bundle, DeterministicStubProposer())

    def test_empty_bundle_rejected(self):
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', {'devices': []}, DeterministicStubProposer())

    def test_recommendations_are_read_only_or_owner_action(self):
        for rid, rec in RECOMMENDATIONS.items():
            self.assertIn(rec['kind'], ('read_only', 'owner_action'), rid)
            self.assertTrue(rec['title'] and rec['owner_action'], rid)


class BatteryDrainTests(unittest.TestCase):
    def test_sufficient_telemetry_explains_from_observed_facts(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel',
                                       fact('battery_percent', 18),
                                       fact('battery_charging', False),
                                       fact('battery_discharge_pct_per_hour', 8.0),
                                       fact('top_consumer', 'Maps'))]}
        report = diagnose('battery_drain', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'high')
        self.assertIn('8.0', report['explanation'])
        self.assertIn('Maps', report['explanation'])
        self.assertIn('phone-1#battery_discharge_pct_per_hour', report['evidence_refs'])
        self.assertIn('phone-1#top_consumer', report['evidence_refs'])
        self.assertEqual(report['limitation'], LIMIT)
        ids = [r['id'] for r in report['recommendations']]
        self.assertIn('check_top_consumer', ids)
        self.assertIn('plug_in_charger', ids)  # 18% observed

    def test_insufficient_telemetry_names_missing_measurements(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel', fact('battery_percent', 60))]}
        report = diagnose('battery_drain', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'low')
        self.assertTrue(any('battery_discharge_pct_per_hour' in m for m in report['missing']))
        bundle2 = {'devices': [dev('phone-1', 'phone', 'Pixel',
                                        fact('os', 'Android 15', confidence='measured'))]}
        report2 = diagnose('battery_drain', bundle2, DeterministicStubProposer())
        self.assertEqual(report2['confidence'], 'insufficient')
        joined = ' '.join(report2['missing'])
        self.assertIn('battery_discharge_pct_per_hour', joined)
        self.assertIn('top_consumer', joined)

    def test_charging_is_observed_not_draining(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel',
                                       fact('battery_percent', 40), fact('battery_charging', True))]}
        report = diagnose('battery_drain', bundle, DeterministicStubProposer())
        self.assertIn('charging', report['explanation'])
        self.assertEqual(report['recommendations'], [])


class BestPcTests(unittest.TestCase):
    def test_ranks_on_observed_metrics_only(self):
        bundle = {'devices': [
            dev('pc-a', 'computer', 'Tower', fact('cpu_threads', 16), fact('ram_gb', 32),
                fact('disk_free_gb', 120)),
            dev('pc-b', 'computer', 'Laptop', fact('cpu_threads', 4), fact('ram_gb', 8),
                fact('disk_free_gb', 60)),
            dev('pc-c', 'computer', 'OldBox'),  # unmeasured: ranked last, never filled in
        ]}
        report = diagnose('best_pc_for_dev', bundle, DeterministicStubProposer())
        self.assertEqual(report['target'], 'pc-a')
        self.assertIn('Tower', report['explanation'])
        self.assertIn('16', report['explanation'])
        self.assertTrue(any('OldBox' in m for m in report['missing']))
        self.assertNotIn('pc-c#cpu_threads', report['evidence_refs'])

    def test_no_metrics_anywhere_is_insufficient(self):
        bundle = {'devices': [dev('pc-a', 'computer', 'Tower'), dev('pc-b', 'computer', 'Laptop')]}
        report = diagnose('best_pc_for_dev', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'insufficient')
        self.assertTrue(any('cpu_threads' in m for m in report['missing']))

    def test_low_disk_suggests_cleanup(self):
        bundle = {'devices': [dev('pc-a', 'computer', 'Tower', fact('cpu_threads', 8),
                                       fact('ram_gb', 16), fact('disk_free_gb', 4))]}
        report = diagnose('best_pc_for_dev', bundle, DeterministicStubProposer())
        ids = [r['id'] for r in report['recommendations']]
        self.assertIn('free_disk_space', ids)


class ConnectivityTests(unittest.TestCase):
    def test_strongest_link_wins_with_evidence(self):
        bundle = {'devices': [
            dev('phone-1', 'phone', 'Pixel', fact('wifi_rssi_dbm', -55),
                fact('rtt_ms', 12), fact('wifi_band', '5GHz')),
            dev('tv-1', 'tv', 'Living TV', fact('wifi_rssi_dbm', -72),
                fact('rtt_ms', 40), fact('wifi_band', '2.4GHz')),
        ]}
        report = diagnose('strongest_connectivity', bundle, DeterministicStubProposer())
        self.assertEqual(report['target'], 'phone-1')
        self.assertEqual(report['confidence'], 'high')
        self.assertIn('-55', report['explanation'])
        self.assertIn('phone-1#wifi_rssi_dbm', report['evidence_refs'])

    def test_unmeasured_devices_are_named_missing(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel', fact('wifi_rssi_dbm', -80))]}
        report = diagnose('strongest_connectivity', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'medium')
        ids = [r['id'] for r in report['recommendations']]
        self.assertIn('move_closer_to_router', ids)  # -80 dBm observed


class TvControlLossTests(unittest.TestCase):
    def test_lost_authorization_is_named_with_guide(self):
        bundle = {'devices': [dev('tv-1', 'tv', 'Living TV', fact('network_reachable', True),
                                       fact('adb_authorized', False), fact('tv_power', 'on'))]}
        report = diagnose('tv_control_loss', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'high')
        self.assertIn('authorization', report['explanation'])
        guides = [r.get('guide') for r in report['recommendations']]
        self.assertIn('tv_debug_prompt', guides)

    def test_unknown_power_is_named_missing(self):
        bundle = {'devices': [dev('tv-1', 'tv', 'Living TV', fact('network_reachable', False))]}
        report = diagnose('tv_control_loss', bundle, DeterministicStubProposer())
        self.assertTrue(any('tv_power' in m for m in report['missing']))
        self.assertIn('not reachable', report['explanation'])

    def test_no_tv_facts_is_insufficient(self):
        bundle = {'devices': [dev('tv-1', 'tv', 'Living TV', fact('os', 'Android TV 12'))]}
        report = diagnose('tv_control_loss', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'insufficient')
        joined = ' '.join(report['missing'])
        self.assertIn('network_reachable', joined)
        self.assertIn('adb_authorized', joined)


class RelayUnavailableTests(unittest.TestCase):
    def test_first_failing_gate_explains(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel',
                                       fact('relay_owner_enabled', False),
                                       fact('relay_permission', True),
                                       fact('companion_running', True))]}
        report = diagnose('relay_unavailable', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'high')
        self.assertIn('paused', report['explanation'])
        ids = [r['id'] for r in report['recommendations']]
        self.assertEqual(ids, ['resume_scans'])
        self.assertTrue(any('bluetooth_on' in m for m in report['missing']))

    def test_no_relay_facts_is_insufficient(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel', fact('battery_percent', 90))]}
        report = diagnose('relay_unavailable', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'insufficient')
        joined = ' '.join(report['missing'])
        self.assertIn('relay_owner_enabled', joined)
        self.assertIn('companion_running', joined)


class WatchSleepTests(unittest.TestCase):
    def test_gap_and_battery_explain(self):
        bundle = {'devices': [dev('watch-1', 'watch', 'Watch',
                                       fact('overnight_gap_minutes', 95),
                                       fact('watch_battery_percent', 22),
                                       fact('watch_ble_connected', False),
                                       fact('watch_wifi_connected', False))]}
        report = diagnose('watch_sleep_drops', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'high')
        self.assertIn('95', report['explanation'])
        ids = [r['id'] for r in report['recommendations']]
        self.assertIn('charge_watch_overnight', ids)
        self.assertIn('keep_phone_nearby', ids)

    def test_no_night_data_names_overnight_samples(self):
        bundle = {'devices': [dev('watch-1', 'watch', 'Watch', fact('os', 'Wear OS 5'))]}
        report = diagnose('watch_sleep_drops', bundle, DeterministicStubProposer())
        self.assertEqual(report['confidence'], 'insufficient')
        self.assertTrue(any('overnight_gap_minutes' in m for m in report['missing']))


class WhatToInstallTests(unittest.TestCase):
    def test_blocked_reason_cited(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel',
                                       fact('companion_installed', False),
                                       fact('install_blocked_reason', 'INSTALL_FAILED_USER_RESTRICTED'))]}
        report = diagnose('what_to_install', bundle, DeterministicStubProposer())
        self.assertIn('INSTALL_FAILED_USER_RESTRICTED', report['explanation'])
        ids = [r['id'] for r in report['recommendations']]
        self.assertEqual(ids, ['check_install_prompt'])

    def test_installed_devices_need_nothing(self):
        bundle = {'devices': [dev('tv-1', 'tv', 'Living TV', fact('companion_installed', True))]}
        report = diagnose('what_to_install', bundle, DeterministicStubProposer())
        self.assertIn('already installed', report['explanation'])
        self.assertEqual(report['recommendations'], [])

    def test_missing_sdk_and_storage_named(self):
        bundle = {'devices': [dev('phone-1', 'phone', 'Pixel',
                                       fact('companion_installed', False))]}
        report = diagnose('what_to_install', bundle, DeterministicStubProposer())
        joined = ' '.join(report['missing'])
        self.assertIn('sdk', joined)
        self.assertIn('storage_free_gb', joined)


BATTERY_BUNDLE = {'devices': [dev('phone-1', 'phone', 'Pixel',
                                       fact('battery_percent', 18),
                                       fact('battery_charging', False),
                                       fact('battery_discharge_pct_per_hour', 8.0),
                                       fact('top_consumer', 'Maps'))]}


class ProposerValidationTests(unittest.TestCase):
    def test_stub_is_deterministic(self):
        first = diagnose('battery_drain', BATTERY_BUNDLE, DeterministicStubProposer())
        second = diagnose('battery_drain', BATTERY_BUNDLE, DeterministicStubProposer())
        self.assertEqual(first, second)
        self.assertTrue(first['model_run_id'].startswith('mr-'))

    def test_meta_proposer_accepts_grounded_output(self):
        body = {'explanation': 'Pixel is draining at 8.0 percent per hour while unplugged.',
                'recommendations': ['check_top_consumer'],
                'evidence_refs': ['phone-1#battery_discharge_pct_per_hour'],
                'uncertainty': LIMIT}
        report = diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(fake_chat_factory([body])))
        self.assertEqual(report['model'], 'meta-1')
        self.assertEqual([r['id'] for r in report['recommendations']], ['check_top_consumer'])

    def test_meta_proposer_rejects_invented_number(self):
        body = {'explanation': 'Pixel is draining at 25.5 percent per hour while unplugged.',
                'recommendations': ['check_top_consumer'],
                'evidence_refs': ['phone-1#battery_discharge_pct_per_hour'],
                'uncertainty': LIMIT}
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(fake_chat_factory([body])))

    def test_meta_proposer_rejects_unoffered_recommendation(self):
        body = {'explanation': 'Pixel is draining at 8.0 percent per hour while unplugged.',
                'recommendations': ['flash_firmware'],
                'evidence_refs': ['phone-1#battery_discharge_pct_per_hour'],
                'uncertainty': LIMIT}
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(fake_chat_factory([body])))

    def test_meta_proposer_rejects_unknown_evidence(self):
        body = {'explanation': 'Pixel is draining at 8.0 percent per hour while unplugged.',
                'recommendations': ['check_top_consumer'],
                'evidence_refs': ['phone-1#benchmark_score'],
                'uncertainty': LIMIT}
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(fake_chat_factory([body])))

    def test_meta_proposer_rejects_missing_citation_and_policy_text(self):
        no_cite = {'explanation': 'Pixel is draining at 8.0 percent per hour while unplugged.',
                   'recommendations': ['check_top_consumer'], 'evidence_refs': [],
                   'uncertainty': LIMIT}
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(fake_chat_factory([no_cite])))
        no_policy = {'explanation': 'Pixel is draining at 8.0 percent per hour while unplugged.',
                     'recommendations': ['check_top_consumer'],
                     'evidence_refs': ['phone-1#battery_discharge_pct_per_hour'],
                     'uncertainty': 'trust me'}
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(fake_chat_factory([no_policy])))

    def test_meta_proposer_rejects_unreadable_output(self):
        chat = lambda payload: {'model': 'meta-1', 'message': {'content': 'not json {'}}  # noqa: E731
        with self.assertRaises(DiagnosticError):
            diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(chat))

    def test_meta_proposer_sees_only_grounded_context(self):
        body = {'explanation': 'Pixel is draining at 8.0 percent per hour while unplugged.',
                'recommendations': ['check_top_consumer'],
                'evidence_refs': ['phone-1#battery_discharge_pct_per_hour'],
                'uncertainty': LIMIT}
        chat = fake_chat_factory([body])
        diagnose('battery_drain', BATTERY_BUNDLE, MetaProposer(chat))
        user_content = chat.calls[0]['messages'][1]['content']
        self.assertEqual(set(user_content), {'question', 'findings', 'missing', 'confidence',
                                             'candidates', 'evidence'})
        self.assertNotIn('benchmark_score', json.dumps(user_content))


if __name__ == '__main__':
    unittest.main()
