"""Skill service: the library alive in the server (SIMULATED: fake HA states, fake receipts, FakeCompanion).

Covers SKILLS.md wiring: state ticks from device states, schedules, the
/api/v2/library routes, and skill buttons on paired Companions.
"""
import unittest

from src.runtime import api_v2
from src.runtime.api_v2 import executor, remote_controls
from src.runtime.primitives import Executor
from src.runtime.remote_controls import RemoteControlError
from src.runtime.skill_service import SkillService
from tests.runtime.test_remote_controls import FakeCompanion, KEY
from tests.runtime.test_routing import Clock, world


def recipe(trigger, steps):
    return {'name': 'Test skill', 'description': '', 'trigger': trigger, 'steps': steps}


MANUAL = {'kind': 'manual'}


class FakeHA:
    def __init__(self, states):
        self._states = states

    def states(self):
        return self._states


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.calls = []
        ex = executor(self.server)

        def fake(name):
            def run(self_, key, params):
                self.calls.append((name, key, params))
                return 'VERIFIED', None, {'ok': True}, True, {'ok': True}
            return run

        ex.RUNNERS = dict(Executor.RUNNERS, ha_set=fake('ha_set'), ha_command=fake('ha_command'))
        self.svc = SkillService(self.server, persist=False, clock=self.clock)
        self.server.skill_service = self.svc

    def tearDown(self):
        self.svc.close()

    def test_no_source_no_fire(self):
        out = self.svc.poll_once()
        self.assertEqual((out['fired'], out['due']), ([], []))
        self.assertEqual(self.calls, [])

    def test_ha_down_never_raises(self):
        class Down:
            def states(self):
                raise OSError('gone')
        self.server.fabric_adapters = lambda p=None: {'home_assistant': Down()}
        out = self.svc.poll_once()
        self.assertEqual((out['fired'], out['due']), ([], []))
        self.assertIn('gone', self.svc.last_error)

    def test_state_edge_fires_approved_skill(self):
        tv = self.keys['tv']
        self.server.fabric_registry.devices[tv]['ha_entity'] = 'media_player.tv'
        ha = FakeHA([{'entity_id': 'media_player.tv', 'state': 'idle'}])
        self.server.fabric_adapters = lambda p=None: {'home_assistant': ha}
        ph = self.keys['phone']
        r = self.svc.lib.add(recipe({'kind': 'state', 'device': tv, 'state': 'playing'},
                                    [{'device': ph, 'primitive': 'ha_command',
                                      'params': {'action': 'pause'}}]))
        self.svc.poll_once()                      # baseline snapshot: never a trigger
        self.assertEqual(self.calls, [])
        ha._states = [{'entity_id': 'media_player.tv', 'state': 'playing'}]
        out = self.svc.poll_once()                # not approved yet: blocked, honestly reported
        self.assertEqual(out['fired'][0]['result'], 'blocked')
        self.assertEqual(self.calls, [])
        self.svc.lib.approve(r['id'])
        ha._states = [{'entity_id': 'media_player.tv', 'state': 'idle'}]
        self.svc.poll_once()
        ha._states = [{'entity_id': 'media_player.tv', 'state': 'playing'}]
        out = self.svc.poll_once()
        self.assertEqual(out['fired'][0]['result'], 'done')
        self.assertEqual(self.calls, [('ha_command', ph, {'action': 'pause'})])
        kinds = [e['kind'] for e in executor(self.server).events_since(0)]
        self.assertIn('skill_fired', kinds)

    def test_schedule_runs_due(self):
        import time as _t
        tv = self.keys['tv']
        lt = _t.localtime(self.clock.t)
        at = '%02d:%02d' % (lt.tm_hour, lt.tm_min)
        r = self.svc.lib.add(recipe({'kind': 'time', 'at': at, 'days': [lt.tm_wday]},
                                    [{'device': tv, 'primitive': 'ha_set', 'params': {'action': 'turn_off'}}]))
        self.svc.lib.approve(r['id'])
        out = self.svc.poll_once()
        self.assertEqual(len(out['due']), 1)
        self.assertEqual(out['due'][0]['result'], 'done')
        out = self.svc.poll_once()                # at most once per scheduled minute
        self.assertEqual(out['due'], [])


class LibraryRoutes(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, ha_set=lambda s, k, p: ('VERIFIED', None, {}, True, {}))
        self.svc = SkillService(self.server, persist=False, clock=self.clock)
        self.server.skill_service = self.svc

    def tearDown(self):
        self.svc.close()

    def add_manual(self):
        return self.svc.lib.add(recipe(MANUAL, [{'device': self.keys['tv'], 'primitive': 'ha_set',
                                                'params': {'action': 'turn_off'}}]))

    def test_get_library(self):
        self.add_manual()
        code, body = api_v2.get(self.server, '/api/v2/library', '')
        self.assertEqual(code, 200)
        self.assertEqual(len(body['skills']), 1)
        self.assertEqual(body['buttons'], [])     # not approved: no button

    def test_consent_required(self):
        r = self.add_manual()
        for path in ('/api/v2/library/approve', '/api/v2/library/run', '/api/v2/library/remove'):
            code, _ = api_v2.post(self.server, path, {'id': r['id']})
            self.assertEqual(code, 400)
        code, _ = api_v2.post(self.server, '/api/v2/library/enable', {'id': r['id'], 'enabled': False})
        self.assertEqual(code, 400)

    def test_approve_run_disable_remove(self):
        r = self.add_manual()
        code, _ = api_v2.post(self.server, '/api/v2/library/approve', {'id': r['id'], 'consent': True})
        self.assertEqual(code, 200)
        code, body = api_v2.get(self.server, '/api/v2/library', '')
        self.assertEqual(len(body['buttons']), 1)
        code, body = api_v2.post(self.server, '/api/v2/library/run', {'id': r['id'], 'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(body['run']['result'], 'done')
        code, body = api_v2.post(self.server, '/api/v2/library/enable',
                                 {'id': r['id'], 'enabled': False, 'consent': True})
        self.assertEqual((code, body['enabled']), (200, False))
        code, body = api_v2.post(self.server, '/api/v2/library/run', {'id': r['id'], 'consent': True})
        self.assertEqual(body['run']['result'], 'blocked')
        code, body = api_v2.post(self.server, '/api/v2/library/remove', {'id': r['id'], 'consent': True})
        self.assertEqual((code, body['removed']), (200, r['id']))

    def test_unknown_skill_is_404(self):
        code, _ = api_v2.post(self.server, '/api/v2/library/approve', {'id': 'skill-deadbeef', 'consent': True})
        self.assertEqual(code, 404)


class SkillButtons(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        ex = executor(self.server)
        self.calls = []

        def fake(name):
            def run(self_, key, params):
                self.calls.append((name, key, params))
                return 'VERIFIED', None, {'ok': True}, True, {'ok': True}
            return run

        ex.RUNNERS = dict(Executor.RUNNERS, ha_set=fake('ha_set'))
        self.svc = SkillService(self.server, persist=False, clock=self.clock)
        self.server.skill_service = self.svc
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-watch', KEY, 'h-watch-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None

    def tearDown(self):
        self.svc.close()

    def approved_manual(self):
        r = self.svc.lib.add(recipe(MANUAL, [{'device': self.keys['tv'], 'primitive': 'ha_set',
                                             'params': {'action': 'turn_off'}}]))
        self.svc.lib.approve(r['id'])
        return r

    def test_press_runs_skill_once(self):
        r = self.approved_manual()
        st = self.rc.set_skill_controls({'relay_id': 'r-watch', 'recipe_ids': [r['id']], 'consent': True})
        self.assertEqual(st['controls'][0]['control_id'], r['id'])
        self.assertEqual(self.companion.controls, [{'control_id': r['id'], 'label': 'Test skill'}])
        rid = self.companion.press(r['id'])
        self.assertEqual(self.rc.poll_once(), 1)
        self.assertEqual(self.calls, [('ha_set', self.keys['tv'], {'action': 'turn_off'})])
        self.assertIn('done, verified', self.companion.results[-1]['text'])
        self.clock.t += 2
        self.companion.press(r['id'], request_id=rid)     # re-sent press: never twice
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 1)
        self.assertIn('already done', self.companion.results[-1]['text'])

    def test_disable_stops_button(self):
        r = self.approved_manual()
        self.rc.set_skill_controls({'relay_id': 'r-watch', 'recipe_ids': [r['id']], 'consent': True})
        self.svc.lib.set_enabled(r['id'], False)
        self.companion.press(r['id'])
        self.rc.poll_once()
        self.assertEqual(self.calls, [])
        self.assertIn('disabled', self.companion.results[-1]['text'].lower())

    def test_grant_validation(self):
        r = self.approved_manual()
        with self.assertRaises(RemoteControlError):
            self.rc.set_skill_controls({'relay_id': 'r-watch', 'recipe_ids': [r['id']]})   # no consent
        with self.assertRaises(RemoteControlError):
            self.rc.set_skill_controls({'relay_id': 'r-watch', 'recipe_ids': ['skill-deadbeef'], 'consent': True})
        pending = self.svc.lib.add(recipe(MANUAL, [{'device': self.keys['tv'], 'primitive': 'ha_set',
                                                   'params': {'action': 'turn_off'}}]))
        with self.assertRaises(RemoteControlError):
            self.rc.set_skill_controls({'relay_id': 'r-watch', 'recipe_ids': [pending['id']], 'consent': True})
        auto = self.svc.lib.add(recipe({'kind': 'state', 'device': self.keys['tv'], 'state': 'playing'},
                                       [{'device': self.keys['phone'], 'primitive': 'ha_set',
                                         'params': {'action': 'turn_off'}}]))
        self.svc.lib.approve(auto['id'])
        with self.assertRaises(RemoteControlError):
            self.rc.set_skill_controls({'relay_id': 'r-watch', 'recipe_ids': [auto['id']], 'consent': True})

    def test_http_grant_route(self):
        r = self.approved_manual()
        code, body = api_v2.post(self.server, '/api/v2/remote_controls/skills',
                                 {'relay_id': 'r-watch', 'recipe_ids': [r['id']], 'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(body['controls'][0]['control_id'], r['id'])


if __name__ == '__main__':
    unittest.main()
