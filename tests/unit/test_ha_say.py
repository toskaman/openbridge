"""`openbridge ha say`: entity matching, and the v3 training data agrees with the skill registry."""
import sys
import unittest
from pathlib import Path

from src import cli
from src.runtime import skills as S

STATES = [{'entity_id': e, 'attributes': {'friendly_name': n}} for e, n in (
    ('light.kitchen_lights', 'Kitchen Lights'), ('light.bed_light', 'Bed Light'), ('light.ceiling_lights', 'Ceiling Lights'),
    ('media_player.living_room', 'Living Room'), ('media_player.bedroom', 'Bedroom'), ('lock.front_door', 'Front Door'),
    ('climate.ecobee', 'Ecobee'), ('cover.kitchen_window', 'Kitchen Window'), ('cover.garage_door', 'Garage Door'))]


class MatchEntities(unittest.TestCase):
    def m(self, ref, domains, kind='device'):
        return cli._match_entities(STATES, {'kind': kind, 'ref': ref}, domains)

    def test_names_and_rooms(self):
        self.assertEqual(self.m('kitchen light', ('light',)), ['light.kitchen_lights'])
        self.assertEqual(self.m('bedroom lamp', ('light',)), ['light.bed_light'])
        self.assertEqual(self.m('kitchen blinds', ('cover',)), ['cover.kitchen_window'])
        self.assertEqual(self.m('front door', ('lock',)), ['lock.front_door'])

    def test_default_device_of_a_kind(self):
        self.assertEqual(self.m('tv', ('media_player',)), ['media_player.living_room'])
        self.assertEqual(self.m('thermostat', ('climate',)), ['climate.ecobee'])

    def test_category_and_domain_limits(self):
        self.assertEqual(len(self.m('light', ('light',), 'category')), 3)
        self.assertEqual(self.m('kitchen light', ('lock',)), [])     # never crosses domains

    def test_policy_still_refuses_garage(self):
        from src.adapters import home_assistant as HA
        self.assertEqual(HA.actions_for({'entity_id': 'cover.garage_door', 'attributes': {'device_class': 'garage'}}), {})


class TrainingDataMatchesRegistry(unittest.TestCase):
    def test_every_gold_reply_resolves(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dev' / 'ai_training'))
        import home_families as H
        import make_dataset as V2
        train, test = H.build(V2.vary, k_train=2, k_test=1)
        rows = train + test
        self.assertGreater(len(rows), 300)
        for r in rows:
            g = r['reply']
            if g['skill_id']:
                S.resolve(g['skill_id'], g['params'])          # raises on unknown skill or bad params
                self.assertTrue(g['targets'])
            else:
                self.assertEqual(g['confidence'], 0.0)
        dialects = {r['dialect'] for r in rows}
        self.assertEqual(dialects, {'en-US', 'en-GB', 'fr'})

    def test_novel_rows_resolve(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'dev' / 'ai_training'))
        import home_families as H
        n = 0
        for dialect, text, exp in H.HOME_NOVEL:
            if exp[0] != 'skill':
                continue
            _, sid, params, ref = exp
            S.resolve(sid, params)               # raises on unknown skill or bad params
            self.assertTrue(ref)
            n += 1
        self.assertGreater(n, 20)


if __name__ == '__main__':
    unittest.main()
