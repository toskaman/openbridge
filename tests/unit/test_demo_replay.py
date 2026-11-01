"""Campaign Three §5.6 + judge-C W3: demo fallback labels + receipt fidelity.

Proves the replay bundle carries verbatim S5/S5b receipt data (every stage
cites a tracked proof doc whose text contains the quoted values), the
REPLAY/SIMULATED labels are unmissable in the real UI, and the replay view
can issue no live call (read-only GET of the bundle).
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from src.runtime.demo_replay import (
    BUNDLE_ID, REPLAY_LABEL, SIMULATED_LABEL, STAGES, load_bundle,
    serve_bundle, validate_bundle, ReplayError,
)


def repo_text(rel):
    return (ROOT / rel).read_text(encoding='utf-8-sig')


class BundleFidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle()

    def test_identity_and_simulated_playback(self):
        self.assertEqual(self.bundle['bundle_id'], BUNDLE_ID)
        self.assertEqual(self.bundle['evidence_kind'], 'RECORDED_REAL_HARDWARE_RECEIPTS')
        self.assertIs(self.bundle['live_request'], False)
        self.assertEqual(self.bundle['playback'], 'SIMULATED')

    def test_two_scenarios_nine_stages_each(self):
        self.assertEqual(list(self.bundle['stages_order']), list(STAGES))
        self.assertEqual(len(self.bundle['scenarios']), 2)
        for scenario in self.bundle['scenarios']:
            self.assertEqual(set(scenario['stages']), set(STAGES))
            self.assertTrue(scenario['honest_limits'])

    def test_every_stage_cites_a_tracked_doc(self):
        for scenario in self.bundle['scenarios']:
            for stage_id, stage in scenario['stages'].items():
                source = stage['source'].split(' (')[0]
                self.assertTrue((ROOT / source).is_file(),
                                '%s/%s cites missing %s' % (scenario['scenario_id'], stage_id, source))

    def test_intent_text_matches_frozen_spec(self):
        freeze = repo_text('docs/benchmark/S5_UI_FREEZE.md')
        intents = [s['stages']['intent']['facts'][0][1] for s in self.bundle['scenarios']]
        self.assertIn('Create a control panel on my TV so I can operate my robot vacuum.', intents)
        self.assertIn('Put TV volume controls and a vacuum find-me button on one panel.', intents)
        for intent in intents:
            self.assertIn(intent, freeze)

    def test_s5_receipt_values_match_proof_doc(self):
        proof = ' '.join(repo_text('docs/evidence/s5-tv-panel-31oct.md').split())
        text = json.dumps(self.bundle)
        for want in ('tx-ab731d7b885b5e1a', 'relay-dabd2a796665',
                     '7e39303524c8a032', '0ffdd012f9e02118',
                     'This control is no longer authorized',
                     'QUICK CONTROLS hold to send',
                     'num_gpu=28', 'touch.down_ms'):
            self.assertIn(want, proof, 'proof doc lost: %s' % want)
            self.assertIn(want, text, 'bundle lost: %s' % want)

    def test_s5b_receipt_values_match_proof_doc(self):
        proof = repo_text('docs/evidence/s5b-safe-seek-31oct.md')
        text = json.dumps(self.bundle)
        for want in ('tx-4a96f8f626a1adc5', 'EXECUTED_UNVERIFIED',
                     'RemoteControlError: This control is no longer authorized',
                     '1290, 595', 'relay_revoke'):
            self.assertIn(want, proof, 'proof doc lost: %s' % want)
            self.assertIn(want, text, 'bundle lost: %s' % want)

    def test_honest_limits_preserved_verbatim(self):
        text = json.dumps(self.bundle)
        for want in ('NOT a manual tap', 'already docked', 'motion NOT observed',
                     'EXECUTED_UNVERIFIED', 'nothing to undo'):
            self.assertIn(want, text)

    def test_tampered_bundle_rejected(self):
        bad = json.loads(json.dumps(self.bundle))
        bad['playback'] = 'LIVE'
        with self.assertRaises(ReplayError):
            validate_bundle(bad)
        bad = json.loads(json.dumps(self.bundle))
        bad['live_request'] = True
        with self.assertRaises(ReplayError):
            validate_bundle(bad)
        bad = json.loads(json.dumps(self.bundle))
        del bad['scenarios'][0]['stages']['revoke']
        with self.assertRaises(ReplayError):
            validate_bundle(bad)

    def test_serve_bundle_payload_shape(self):
        code, body = serve_bundle()
        self.assertEqual(code, 200)
        self.assertEqual(body['playback'], 'SIMULATED')
        self.assertIs(body['live_request'], False)
        self.assertEqual(body['bundle']['bundle_id'], BUNDLE_ID)
        code, body = serve_bundle(path=ROOT / 'docs' / 'missing.json')
        self.assertEqual(code, 404)


class ReplayLabelsInRealUI(unittest.TestCase):
    def test_replay_view_mounted_in_real_ui(self):
        index = repo_text('src/ui/index.html')
        self.assertIn('data-view="replay"', index)
        self.assertIn('/replay.js', index)
        self.assertIn('#/replay', index)
        shell = repo_text('src/ui/shell.js')
        self.assertIn('replay', shell)
        self.assertIn('renderReplay', shell)
        css = repo_text('src/ui/style.css')
        self.assertIn('.replay-banner', css)
        self.assertIn('.replay-stage', css)
        server = repo_text('src/server.py')
        self.assertIn('/replay.js', server)
        self.assertIn('/api/demo-replay', server)

    def test_labels_unmissable_in_replay_script(self):
        js = repo_text('src/ui/replay.js')
        self.assertIn(REPLAY_LABEL, js)
        self.assertIn(SIMULATED_LABEL, js)
        for stage in STAGES:
            self.assertIn("'%s'" % stage, js)
        self.assertIn('/api/demo-replay', js)

    def test_receipts_come_from_bundle_not_hardcoded(self):
        js = repo_text('src/ui/replay.js')
        for leaked in ('tx-ab731d7b885b5e1a', 'tx-4a96f8f626a1adc5',
                       'relay-dabd2a796665', '7e39303524c8a032'):
            self.assertNotIn(leaked, js)

    def test_replay_view_cannot_issue_live_calls(self):
        js = repo_text('src/ui/replay.js')
        for forbidden in ('postJson', 'POST', '/api/recommend',
                          '/api/agent-execute', '/api/agent-plan',
                          'set_controls', 'XMLHttpRequest'):
            self.assertNotIn(forbidden, js)


if __name__ == '__main__':
    unittest.main()
