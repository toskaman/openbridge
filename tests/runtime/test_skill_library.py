"""Skill library: AI-created features saved as recipes that run with no AI model, through the normal gate."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.runtime import skill_library as SL


class FakeExecutor:
    def __init__(self, fail_on=()):
        self.calls, self.fail_on = [], set(fail_on)

    def execute(self, primitive, device, params, consent=False):
        self.calls.append((primitive, device, dict(params), consent))
        ok = device not in self.fail_on
        return {'state': 'VERIFIED' if ok else 'FAILED', 'verified': ok, 'transaction_id': 'tx-%d' % len(self.calls),
                'errors': [] if ok else ['read-back mismatch']}


CINEMA = {'name': 'Cinema mode', 'description': 'Dim the lights when the TV plays',
          'trigger': {'kind': 'state', 'device': 'dev-tv', 'state': 'playing'},
          'steps': [{'device': 'dev-light', 'primitive': 'ha_set', 'params': {'action': 'set_brightness', 'value': 20}},
                    {'device': 'dev-plug', 'primitive': 'ha_set', 'params': {'action': 'turn_off'}}]}
MORNING = {'name': 'Morning coffee', 'trigger': {'kind': 'time', 'at': '07:15', 'days': [0, 1, 2, 3, 4]},
           'steps': [{'device': 'dev-coffee', 'primitive': 'ha_set', 'params': {'action': 'turn_on'}}]}
BUTTON = {'name': 'Leaving home', 'trigger': {'kind': 'manual'},
          'steps': [{'device': 'dev-light', 'primitive': 'ha_set', 'params': {'action': 'turn_off'}},
                    {'device': 'dev-vacuum', 'primitive': 'tuya_command', 'params': {'command': 'start'}}]}


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / 'lib.json'
        self.clock, self.ex = Clock(), FakeExecutor()
        self.lib = SL.Library(self.ex, self.path, clock=self.clock)


class Validation(Base):
    def test_rejects_unsafe_or_malformed_recipes(self):
        bad = [
            dict(BUTTON, steps=[{'device': 'pc', 'primitive': 'pc_job', 'params': {'cmd': 'format c:'}}]),
            dict(BUTTON, steps=[]),
            dict(BUTTON, steps=[BUTTON['steps'][0]] * 9),
            dict(BUTTON, trigger={'kind': 'webhook'}),
            dict(MORNING, trigger={'kind': 'time', 'at': '25:00', 'days': [0]}),
            dict(MORNING, trigger={'kind': 'time', 'at': '07:00', 'days': [7]}),
            dict(CINEMA, steps=[{'device': 'dev-tv', 'primitive': 'ha_set', 'params': {'action': 'turn_off'}}]),
            dict(BUTTON, name=''),
            dict(BUTTON, steps=[{'device': 'dev light!', 'primitive': 'ha_set', 'params': {}}]),
        ]
        for b in bad:
            with self.subTest(b=b), self.assertRaises(SL.SkillError):
                self.lib.add(b, 'ai')
        self.assertEqual(self.lib.recipes, {})


class ApprovalAndRun(Base):
    def test_ai_proposal_needs_approval_then_runs_without_a_model(self):
        r = self.lib.add(BUTTON, 'ai', model='openbridge-intent-qwen1.5b-v2', request='quand je pars, éteins tout')
        self.assertEqual(self.lib.run(r['id'])['result'], 'blocked')
        self.assertEqual(self.ex.calls, [])
        self.lib.approve(r['id'])
        out = self.lib.run(r['id'])
        self.assertEqual(out['result'], 'done')
        self.assertEqual([c[:2] for c in self.ex.calls], [('ha_set', 'dev-light'), ('tuya_command', 'dev-vacuum')])
        self.assertTrue(all(c[3] is True for c in self.ex.calls))        # standing approval = consent per step
        self.assertEqual(r['origin'], {'kind': 'ai', 'model': 'openbridge-intent-qwen1.5b-v2',
                                       'request': 'quand je pars, éteins tout'})

    def test_editing_a_recipe_voids_its_approval(self):
        r = self.lib.add(BUTTON, 'owner')
        self.lib.approve(r['id'])
        r['steps'][1]['params'] = {'command': 'return_to_base'}           # tampered after approval
        self.assertEqual(self.lib.run(r['id'])['result'], 'blocked')
        self.assertEqual(self.ex.calls, [])

    def test_run_stops_at_the_first_unverified_step(self):
        self.ex.fail_on = {'dev-light'}
        r = self.lib.add(BUTTON, 'owner')
        self.lib.approve(r['id'])
        out = self.lib.run(r['id'])
        self.assertEqual((out['result'], len(self.ex.calls)), ('failed', 1))

    def test_disabled_recipe_does_not_run(self):
        r = self.lib.add(BUTTON, 'owner')
        self.lib.approve(r['id'])
        self.lib.set_enabled(r['id'], False)
        self.assertEqual(self.lib.run(r['id'])['reason'], 'disabled')

    def test_library_survives_a_restart(self):
        r = self.lib.add(BUTTON, 'owner')
        self.lib.approve(r['id'])
        again = SL.Library(self.ex, self.path, clock=self.clock)
        self.assertTrue(again.is_approved(again.recipes[r['id']]))
        self.assertEqual(again.run(r['id'])['result'], 'done')


class Triggers(Base):
    def test_state_trigger_fires_on_the_edge_only(self):
        r = self.lib.add(CINEMA, 'suggestion')
        self.lib.approve(r['id'])
        self.assertEqual(self.lib.tick({'dev-tv': 'playing'}), [])         # baseline, never a trigger
        self.assertEqual(self.lib.tick({'dev-tv': 'playing'}), [])         # no change
        self.lib.tick({'dev-tv': 'paused'})
        self.clock.t += 60
        fired = self.lib.tick({'dev-tv': 'playing'})
        self.assertEqual([f['result'] for f in fired], ['done'])
        self.assertEqual(len(self.ex.calls), 2)

    def test_cooldown_and_chain_guard(self):
        r = self.lib.add(CINEMA, 'suggestion')
        self.lib.approve(r['id'])
        self.lib.tick({'dev-tv': 'off'})
        self.clock.t += 60
        self.assertEqual(self.lib.tick({'dev-tv': 'playing'})[0]['result'], 'done')
        self.lib.tick({'dev-tv': 'paused'})
        self.clock.t += 5
        self.assertEqual(self.lib.tick({'dev-tv': 'playing'})[0]['reason'], 'cooldown')
        # A device that a skill just changed cannot trigger another skill right away (no ping-pong).
        other = self.lib.add(dict(CINEMA, name='Plug follows', trigger={'kind': 'state', 'device': 'dev-plug', 'state': 'off'},
                                  steps=[{'device': 'dev-coffee', 'primitive': 'ha_set', 'params': {'action': 'turn_off'}}]), 'owner')
        self.lib.approve(other['id'])
        self.lib.tick({'dev-plug': 'on'})
        self.clock.t += 60
        self.lib._caused['dev-plug'] = self.clock.t - 2
        self.assertEqual(self.lib.tick({'dev-plug': 'off'})[0]['reason'], 'chain guard')

    def test_time_trigger_runs_once_per_scheduled_minute(self):
        r = self.lib.add(MORNING, 'ai')
        self.lib.approve(r['id'])
        monday_0715 = time.struct_time((2026, 11, 23, 7, 15, 0, 0, 327, -1))
        sunday_0715 = time.struct_time((2026, 11, 22, 7, 15, 0, 6, 326, -1))
        self.assertEqual([x['result'] for x in self.lib.run_due(monday_0715)], ['done'])
        self.assertEqual(self.lib.run_due(monday_0715), [])                # same minute: not twice
        self.assertEqual(self.lib.run_due(sunday_0715), [])                # not a scheduled day

    def test_suggestion_becomes_a_recipe(self):
        idea = {'title': 'Cinema mode', 'why': 'TV and lights are proven',
                'when': {'device': 'dev-tv', 'label': 'TV', 'state': 'playing', 'state_observed': True},
                'then': {'device': 'dev-light', 'label': 'Lamp', 'primitive': 'ha_set',
                         'params': {'action': 'set_brightness', 'value': 20}}, 'confidence': 'high'}
        r = self.lib.from_suggestion(idea)
        self.assertEqual((r['origin']['kind'], r['steps'][0]['primitive'], r['approved']), ('suggestion', 'ha_set', None))
        self.assertEqual(r['steps'][0]['params'], {'action': 'set_brightness', 'value': 20})

    def test_suggestion_rejects_foreign_shapes(self):
        bad = [{'title': 'x'}, {'when': {}, 'then': {}},
               {'when': {'device': 'd', 'state': 's'},
                'then': {'device': 'd2', 'primitive': 'pc_job', 'params': {}}},
               'not an idea', None, []]
        for idea in bad:
            with self.assertRaises(SL.SkillError):
                self.lib.from_suggestion(idea)


class Sharing(Base):
    def test_export_import_roundtrip_never_carries_approval(self):
        r = self.lib.add(BUTTON, 'ai', model='m', request='leaving')
        self.lib.approve(r['id'])
        reg = SimpleNamespace(devices={'dev-light': {'category': 'light', 'label': 'Living room'},
                                       'dev-vacuum': {'category': 'vacuum', 'label': 'Robot'}})
        bundle = self.lib.export(registry=reg)
        self.assertEqual(bundle['devices']['dev-light'], {'category': 'light', 'label': 'Living room'})
        self.assertNotIn('approved', bundle['skills'][0])
        # Same install: trusted; still unapproved.
        res = self.lib.import_bundle(bundle)
        self.assertTrue(res['trusted'])
        self.assertIsNone(self.lib.recipes[res['imported'][0]]['approved'])
        # Another install: foreign, devices remapped by the owner.
        other = SL.Library(FakeExecutor(), Path(self.dir.name) / 'other.json', clock=self.clock)
        res2 = other.import_bundle(bundle, device_map={'dev-light': 'their-light'})
        self.assertFalse(res2['trusted'])
        imported = other.recipes[res2['imported'][0]]
        self.assertEqual(imported['steps'][0]['device'], 'their-light')
        self.assertEqual(res2['unmapped_devices'], ['dev-vacuum'])
        self.assertEqual(imported['origin']['kind'], 'import')

    def test_tampered_bundle_is_foreign_and_unsafe_steps_are_refused(self):
        bundle = self.lib.export(ids=[self.lib.add(BUTTON, 'owner')['id']])
        bundle['skills'][0]['steps'][0]['primitive'] = 'pc_job'
        with self.assertRaises(SL.SkillError):
            self.lib.import_bundle(bundle)
        with self.assertRaises(SL.SkillError):
            self.lib.import_bundle({'format': 'something-else', 'skills': []})

    def test_buttons_for_paired_devices(self):
        r = self.lib.add(BUTTON, 'owner')
        self.lib.add(MORNING, 'owner')
        self.assertEqual(self.lib.buttons(), [])                            # not approved yet
        self.lib.approve(r['id'])
        self.assertEqual(self.lib.buttons(), [{'control_id': 'skill-' + r['id'][6:], 'label': 'Leaving home'}])


if __name__ == '__main__':
    unittest.main()
