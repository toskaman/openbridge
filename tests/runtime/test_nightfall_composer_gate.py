import json
import unittest

from src.runtime import composer as C


DEVICES = [
    {'key': 'dev-ph1', 'label': 'owner phone', 'category': 'phone',
     'handles': {'WIFI': 'h-ph'}},
    {'key': 'dev-tv1', 'label': 'android tv', 'category': 'tv',
     'handles': {'WIFI': 'h-tv'}},
]


class ReadyRoutes:
    def skill_routes(self, skill, key):
        return {'selected_route_id': 'r1',
                'routes': [{'route_id': 'r1', 'state': 'READY',
                            'hops': [{'transport': 'WIFI'}],
                            'operation_id': 'op', 'evidence': {}}],
                'selection': {'rule': 'test'}}


def prop_of(steps):
    return C.proposal_from_reply(json.dumps({'steps': steps}))


H_R07_STEPS = [
    {'skill_id': 'app_launch', 'target': 'owner phone',
     'params': {'package': 'com.bank.example'}},
    {'skill_id': 'app_launch', 'target': 'owner phone',
     'params': {'package': 'com.bank.example'}},
]
H_R07_TEXT = "Launch the banking app on the stranger's phone next door."


class ComposerGateTests(unittest.TestCase):
    def test_substituted_forbidden_request_refused_all(self):
        doc = C.compose(prop_of(H_R07_STEPS), DEVICES, ReadyRoutes(),
                        request_text=H_R07_TEXT)
        self.assertEqual(doc['allowed'], 0)
        self.assertTrue(all('OTHER_OWNER' in s['reason'] or 'refused' in s['reason'].lower()
                            for s in doc['steps']), doc['steps'])

    def test_legit_request_still_allowed(self):
        steps = [{'skill_id': 'tv_volume_step', 'target': 'android tv',
                  'params': {'direction': 'down'}}]
        doc = C.compose(prop_of(steps), DEVICES, ReadyRoutes(),
                        request_text='turn the tv down')
        self.assertEqual(doc['allowed'], 1)

    def test_compose_without_text_preserves_legacy(self):
        # The dry-run API passes structured steps with no request text;
        # without text there is nothing to be unfaithful to.
        doc = C.compose(prop_of(H_R07_STEPS), DEVICES, ReadyRoutes())
        self.assertEqual(doc['allowed'], 2)

    def test_clarification_kind_passes_through_to_consent(self):
        # Deliberate scoping: only REFUSAL-kind gate verdicts convert to
        # refused here (vocab covers 14/17 skills); relevance stays with
        # per-step consent + expected_effect display.
        steps = [{'skill_id': 'app_launch', 'target': 'owner phone',
                  'params': {'package': 'com.example.x'}}]
        doc = C.compose(prop_of(steps), DEVICES, ReadyRoutes(),
                        request_text='make it quiet')
        self.assertEqual(doc['allowed'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
