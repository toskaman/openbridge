"""MI capability discovery (§3): Meta explains a verified device with
provenance; a deterministic verifier admits only registered skills,
live peers, and closed-vocabulary needs. Nothing executes."""
import hashlib
import json
import unittest


def _device():
    return {'key': 'dev-tv', 'label': 'Android TV', 'category': 'tv',
            'handles': {'WIFI': 'h-tv'}}


def _peers():
    return [{'key': 'dev-w', 'label': 'Smartwatch', 'category': 'watch',
             'handles': {'USB': 'h-w'}}]


def _docs():
    return [{'source': 'vendor-manual-tv',
             'digest': hashlib.sha256(b'doc').hexdigest(),
             'excerpt': 'The TV supports app launch and volume control.'}]


def _good_report():
    return {
        'summary': 'A linked Android TV. Can launch apps and change volume.',
        'capabilities': [
            {'skill_id': 'app_launch', 'peers': [], 'needs': [],
             'verify': 'observe the app on screen'},
            {'skill_id': 'tv_volume_step', 'peers': ['Smartwatch'],
             'needs': ['permission'], 'verify': 'hear the volume change'}],
        'combinations': [
            {'title': 'Watch remote for the TV',
             'skills': ['app_launch'], 'devices': ['Smartwatch'],
             'needs': ['permission']}],
        'unknowns': ['Bluetooth support is not in telemetry.'],
        'test_plan': ['Launch one app and observe the screen.'],
    }


class VerifyReport(unittest.TestCase):
    def test_grounded_report_accepted(self):
        from src.ai import discovery as disc
        rep = disc.verify_report(_good_report(), _device(), _peers(), _docs(), _docs())
        self.assertEqual(len(rep['capabilities']), 2)
        self.assertEqual(len(rep['combinations']), 1)
        self.assertEqual(rep['dropped'], [])
        self.assertEqual(rep['verified_devices'], ['Android TV', 'Smartwatch'])
        self.assertEqual(rep['doc_digests'], [_docs()[0]['digest']])

    def test_invented_skill_dropped_openly(self):
        from src.ai import discovery as disc
        doc = _good_report()
        doc['capabilities'].append(
            {'skill_id': 'backdoor_install', 'peers': [], 'needs': [],
             'verify': 'none'})
        rep = disc.verify_report(doc, _device(), _peers(), _docs(), _docs())
        self.assertEqual(len(rep['capabilities']), 2)
        self.assertEqual(len(rep['dropped']), 1)
        self.assertIn('backdoor_install', rep['dropped'][0]['reason'])

    def test_ghost_peer_dropped(self):
        from src.ai import discovery as disc
        doc = _good_report()
        doc['capabilities'][0]['peers'] = ['Stranger Phone']
        rep = disc.verify_report(doc, _device(), _peers(), _docs(), _docs())
        self.assertEqual(rep['capabilities'][0]['peers'], [])
        self.assertEqual(len(rep['dropped']), 1)

    def test_open_vocabulary_need_dropped(self):
        from src.ai import discovery as disc
        doc = _good_report()
        doc['capabilities'][0]['needs'] = ['root the device']
        rep = disc.verify_report(doc, _device(), _peers(), _docs(), _docs())
        self.assertEqual(rep['capabilities'][0]['needs'], [])
        self.assertEqual(len(rep['dropped']), 1)

    def test_oversized_summary_rejected(self):
        from src.ai import discovery as disc
        doc = _good_report()
        doc['summary'] = 'x' * 5000
        with self.assertRaises(disc.DiscoveryError):
            disc.verify_report(doc, _device(), _peers(), _docs(), _docs())

    def test_bad_shape_rejected(self):
        from src.ai import discovery as disc
        with self.assertRaises(disc.DiscoveryError):
            disc.verify_report({'summary': 'x'}, _device(), _peers(), _docs(), _docs())

    def test_wrong_audience_skill_dropped(self):
        from src.ai import discovery as disc
        doc = _good_report()
        doc['capabilities'].append(
            {'skill_id': 'pc_run', 'peers': [], 'needs': [],
             'verify': 'none'})
        rep = disc.verify_report(doc, _device(), _peers(), _docs(), _docs())
        self.assertEqual(len(rep['capabilities']), 2)
        self.assertEqual(len(rep['dropped']), 1)
        self.assertIn('not usable', rep['dropped'][0]['reason'])

    def test_no_link_device_drops_all_skills(self):
        from src.ai import discovery as disc
        dev = _device()
        dev['handles'] = {}
        rep = disc.verify_report(_good_report(), dev, _peers(), _docs(), _docs())
        self.assertEqual(rep['capabilities'], [])
        self.assertEqual(len(rep['dropped']), 2)

    def test_decorated_peer_label_matched(self):
        from src.ai import discovery as disc
        doc = _good_report()
        doc['capabilities'][1]['peers'] = ['Smartwatch (watch)']
        doc['combinations'][0]['devices'] = ['Smartwatch (watch)']
        rep = disc.verify_report(doc, _device(), _peers(), _docs(), _docs())
        self.assertEqual(rep['capabilities'][1]['peers'], ['Smartwatch'])
        self.assertEqual(rep['combinations'][0]['devices'], ['Smartwatch'])
        self.assertEqual(rep['dropped'], [])

    def test_genuinely_unknown_paren_label_still_ghost(self):
        from src.ai import discovery as disc
        doc = _good_report()
        doc['capabilities'][0]['peers'] = ['Stranger Phone (phone)']
        rep = disc.verify_report(doc, _device(), _peers(), _docs(), _docs())
        self.assertEqual(rep['capabilities'][0]['peers'], [])
        self.assertEqual(len(rep['dropped']), 1)


class ExplainDevice(unittest.TestCase):
    def test_full_bridge_with_stub_proposer(self):
        from src.ai import discovery as disc
        content = json.dumps(_good_report())
        proposer = lambda prompt: {'model_id': 'stub', 'endpoint': 'stub',
                                   'content': content}
        rep = disc.explain_device(_device(), _peers(), _docs(), proposer)
        self.assertEqual(len(rep['capabilities']), 2)
        self.assertEqual(rep['model_run']['provider'], 'meta')
        self.assertEqual(rep['model_run']['model'], 'stub')
        self.assertIn('reply_sha256', rep)

    def test_malformed_reply_rejected(self):
        from src.ai import discovery as disc
        proposer = lambda prompt: {'model_id': 's', 'endpoint': 's',
                                   'content': '{not json'}
        with self.assertRaises(disc.DiscoveryError):
            disc.explain_device(_device(), _peers(), _docs(), proposer)

    def test_prompt_contains_only_labels_and_docs(self):
        from src.ai import discovery as disc
        p = disc.build_prompt(_device(), _peers(), _docs())
        self.assertIn('Android TV', p)
        self.assertNotIn('dev-tv', p)
        self.assertIn('vendor-manual-tv', p)
        self.assertIn('hypothesis', p.lower())

    def test_prompt_lists_verified_candidates(self):
        from src.ai import discovery as disc
        p = disc.build_prompt(_device(), _peers(), _docs())
        self.assertIn('Candidate skills for THIS device (verified)', p)
        self.assertIn('tv_volume_step', p)

    def test_prompt_glosses_with_registry_plain_and_options(self):
        from src.ai import discovery as disc
        vac = {'key': 'd-v', 'label': 'Aspirateur', 'category': 'vacuum',
               'handles': {'WIFI': 'h'}}
        p = disc.build_prompt(vac, [], [])
        self.assertIn('vacuum_command', p)
        self.assertIn('Tuya', p)
        self.assertIn('options: start', p)
        self.assertNotIn('tv_sleep', p.split('Skills:')[0])

    def test_prompt_demands_enumeration_and_precise_unknowns(self):
        from src.ai import discovery as disc
        p = disc.build_prompt(_device(), _peers(), _docs())
        self.assertIn('never stop after the first', p)
        self.assertIn('ONLY genuine gaps', p)


if __name__ == '__main__':
    unittest.main(verbosity=2)
