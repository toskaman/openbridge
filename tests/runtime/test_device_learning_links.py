"""Device learning and device links: profiles from receipts, proven-only suggestions, guarded link engine."""
import unittest
from types import SimpleNamespace

from src.runtime.device_learning import Learner, suggest_recipes
from src.runtime.device_links import Links, LinkError


def receipt(key, state='VERIFIED', verified=True, before='off', after='on'):
    return {'device_key': key, 'state': state, 'verified': verified, 'before': before, 'after': after,
            'started_at': '2026-11-22T20:00:00+00:00', 'finished_at': '2026-11-22T20:00:01.500000+00:00',
            'transaction_id': 'tx-1', 'errors': []}


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, prim, key, params, consent=False):
        self.calls.append((prim, key, params, consent))
        return receipt(key)


class LearnerTests(unittest.TestCase):
    def test_profile_and_proven_threshold(self):
        l = Learner(persist=False)
        for _ in range(2):
            l.observe_receipt(receipt('k1'), 'light', 'ha_set:turn_on')
        self.assertFalse(l.proven('k1', 'ha_set:turn_on'))
        l.observe_receipt(receipt('k1'), 'light', 'ha_set:turn_on')
        p = l.action_profile('k1', 'ha_set:turn_on')
        self.assertTrue(p['proven'])
        self.assertEqual((p['runs'], p['verified'], p['latency_p50_s']), (3, 3, 1.5))
        l.observe_receipt(receipt('k1', 'BLOCKED', False), 'light', 'ha_set:turn_on')
        self.assertEqual(l.action_profile('k1', 'ha_set:turn_on')['success_rate'], 1.0)   # refusals are not failures
        for _ in range(3):
            l.observe_receipt(receipt('k1', 'FAILED', False), 'light', 'ha_set:turn_on')
        self.assertFalse(l.proven('k1', 'ha_set:turn_on'))

    def test_suggestions_use_only_proven_capabilities(self):
        l = Learner(persist=False)
        reg = SimpleNamespace(devices={'tv': {'category': 'media_player', 'label': 'TV'}, 'lamp': {'category': 'light', 'label': 'Lamp'}})
        self.assertEqual(suggest_recipes(reg, l), [])
        for _ in range(3):
            l.observe_receipt(receipt('lamp'), 'light', 'ha_set:set_brightness')
        l.observe_receipt(receipt('tv', before='paused', after='playing'), 'media_player', 'ha_command:play')
        ideas = suggest_recipes(reg, l)
        self.assertEqual(ideas[0]['title'], 'Cinema mode')
        self.assertEqual(ideas[0]['confidence'], 'high')


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.ex = FakeExecutor()
        self.links = Links(self.ex, persist=False, clock=lambda: self.now[0])

    def test_validation(self):
        for args in (('a', 'on', 'a', 'ha_set', {}), ('a', 'on', 'b', 'pc_job', {}), ('a', '', 'b', 'ha_set', {})):
            with self.subTest(args=args), self.assertRaises(LinkError):
                self.links.add(*args)

    def test_fires_on_change_only_after_approval_with_guards(self):
        l = self.links.add('tv', 'playing', 'lamp', 'ha_set', {'action': 'set_brightness', 'value': 20}, cooldown_s=30)
        self.assertEqual(self.links.tick({'tv': 'playing'}), [])                       # first snapshot = baseline
        self.links.tick({'tv': 'paused'})
        self.assertEqual(self.links.tick({'tv': 'playing'})[0]['result'], 'SKIPPED_NOT_APPROVED')
        self.links.approve(l['id'])
        self.links.tick({'tv': 'paused'})
        self.now[0] += 1
        self.assertEqual(self.links.tick({'tv': 'playing'})[0]['result'], 'VERIFIED')
        self.assertEqual(self.ex.calls[-1], ('ha_set', 'lamp', {'action': 'set_brightness', 'value': 20}, True))
        self.assertEqual(self.links.tick({'tv': 'playing'}), [])                       # level, not edge: no refire
        self.links.tick({'tv': 'paused'})
        self.now[0] += 5
        self.assertEqual(self.links.tick({'tv': 'playing'})[0]['result'], 'SKIPPED_COOLDOWN')

    def test_no_ping_pong_between_two_links(self):
        a = self.links.add('tv', 'playing', 'lamp', 'ha_set', {'action': 'turn_off'})
        b = self.links.add('lamp', 'off', 'tv', 'ha_command', {'action': 'play'})
        self.links.approve(a['id']); self.links.approve(b['id'])
        self.links.tick({'tv': 'paused', 'lamp': 'on'})
        self.assertEqual(self.links.tick({'tv': 'playing', 'lamp': 'on'})[0]['result'], 'VERIFIED')
        self.now[0] += 2
        ev = self.links.tick({'tv': 'playing', 'lamp': 'off'})                         # the lamp changed because of link a
        self.assertEqual(ev[0]['result'], 'SKIPPED_CHAIN_GUARD')

    def test_hourly_cap(self):
        l = self.links.add('tv', 'playing', 'lamp', 'ha_set', {'action': 'turn_on'}, cooldown_s=5, max_per_hour=2)
        self.links.approve(l['id'])
        self.links.tick({'tv': 'paused'})
        results = []
        for _ in range(3):
            self.now[0] += 20
            results.append(self.links.tick({'tv': 'playing'})[0]['result'])
            self.links.tick({'tv': 'paused'})
        self.assertEqual(results, ['VERIFIED', 'VERIFIED', 'SKIPPED_HOURLY_CAP'])


if __name__ == '__main__':
    unittest.main()
