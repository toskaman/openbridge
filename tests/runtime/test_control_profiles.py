"""Custom control profiles (SIMULATED_VERIFIED: FakeCompanion, tmp journal)."""
import tempfile
import unittest

from src.fabric.session import SessionJournal
from src.runtime import control_profiles as CP
from src.runtime.api_v2 import get, post, remote_controls
from tests.runtime.test_remote_controls import FakeCompanion, KEY
from tests.runtime.test_routing import Clock, world

VOL_UP = {'label': 'Volume +', 'skill_id': 'tv_volume_step', 'device': 'Android TV', 'params': {'direction': 'up'}}
VOL_DOWN = {'label': 'Volume -', 'skill_id': 'tv_volume_step', 'device': 'Android TV', 'params': {'direction': 'down'}}
SCAN = {'label': 'Scan', 'skill_id': 'ble_scan_room', 'device': 'Android TV', 'params': {'seconds': 5}}


class ControlProfiles(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-watch', KEY, 'h-ph-1', {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.server.session_journal = SessionJournal(tempfile.mkdtemp() + '/s.json')

    def save(self, name='Movie night', buttons=(VOL_UP, VOL_DOWN), pid=None):
        body = {'relay_id': 'r-watch', 'name': name, 'buttons': list(buttons)}
        if pid:
            body['profile_id'] = pid
        return post(self.server, '/api/v2/control_profiles/save', body)

    def test_save_list_update_delete(self):
        code, body = self.save()
        self.assertEqual(code, 200, body)
        pid = body['profile']['id']
        self.assertEqual(self.companion.ops, [])                     # saving installs nothing
        code, st = get(self.server, '/api/v2/control_profiles', '')
        self.assertEqual(code, 200)
        prof = st['screens']['r-watch']['profiles'][0]
        self.assertEqual((prof['name'], len(prof['buttons'])), ('Movie night', 2))
        self.assertEqual(st['max_buttons'], 12)
        self.assertNotIn('pc_run', st['bindable_skills'])
        code, body = self.save('Film', [VOL_UP], pid)
        self.assertEqual((code, body['profile']['name'], len(body['profile']['buttons'])), (200, 'Film', 1))
        code, _ = post(self.server, '/api/v2/control_profiles/delete', {'relay_id': 'r-watch', 'profile_id': pid})
        self.assertEqual(code, 200)
        _, st = get(self.server, '/api/v2/control_profiles', '')
        self.assertNotIn('r-watch', st['screens'])

    def test_apply_resolves_device_label_and_needs_consent(self):
        _, body = self.save()
        pid = body['profile']['id']
        code, _ = post(self.server, '/api/v2/control_profiles/apply', {'relay_id': 'r-watch', 'profile_id': pid})
        self.assertEqual(code, 400)
        self.assertEqual(self.companion.controls, [])
        code, body = post(self.server, '/api/v2/control_profiles/apply', {'relay_id': 'r-watch', 'profile_id': pid, 'consent': True})
        self.assertEqual(code, 200, body)
        self.assertEqual([c['label'] for c in self.companion.controls], ['Volume +', 'Volume -'])   # order kept
        grants = remote_controls(self.server).grants['r-watch']
        self.assertEqual({g['target'] for g in grants.values()}, {self.keys['tv']})
        _, st = get(self.server, '/api/v2/control_profiles', '')
        scr = st['screens']['r-watch']
        self.assertEqual(scr['active'], pid)
        self.assertEqual(scr['applied']['digest'], scr['profiles'][0]['digest'])
        self.assertEqual([b['label'] for b in scr['live']], ['Volume +', 'Volume -'])

    def test_unknown_device_is_refused_at_send_time(self):
        lost = dict(VOL_UP, device='Kitchen TV')
        _, body = self.save('Kitchen', [lost])
        code, body = post(self.server, '/api/v2/control_profiles/apply',
                          {'relay_id': 'r-watch', 'profile_id': body['profile']['id'], 'consent': True})
        self.assertEqual(code, 409)
        self.assertIn('Kitchen TV', body['error'])
        self.assertEqual(self.companion.controls, [])

    def test_validation(self):
        bad = [
            [dict(VOL_UP, skill_id='pc_run', params={'command': 'dir'})],          # never a one-tap button
            [dict(VOL_UP, params={'direction': 'sideways'})],                     # schema
            [VOL_UP, dict(VOL_DOWN, label='volume +')],                           # duplicate text
            [dict(VOL_UP, label='')],
            [dict(VOL_UP, label='x' * 41)],
            [dict(VOL_UP, device=None)],                                          # targeted action without a device
            [dict(VOL_UP, label='V%d' % i) for i in range(13)],                  # more than a screen shows
        ]
        for buttons in bad:
            code, _ = self.save('Bad', buttons)
            self.assertEqual(code, 400, buttons[0])
        code, _ = self.save('', [VOL_UP])
        self.assertEqual(code, 400)
        self.save('Same')
        code, body = self.save('same', [VOL_UP])
        self.assertEqual(code, 400)
        self.assertIn('already exists', body['error'])

    def test_untargeted_button_drops_device(self):
        code, body = self.save('BLE', [SCAN])
        self.assertEqual(code, 200, body)
        self.assertIsNone(body['profile']['buttons'][0]['device'])

    def test_empty_profile_and_clear(self):
        code, body = self.save('Empty', [])
        self.assertEqual(code, 200)
        _, b2 = self.save()
        post(self.server, '/api/v2/control_profiles/apply', {'relay_id': 'r-watch', 'profile_id': b2['profile']['id'], 'consent': True})
        self.assertEqual(len(self.companion.controls), 2)
        code, _ = post(self.server, '/api/v2/control_profiles/clear', {'relay_id': 'r-watch'})
        self.assertEqual(code, 400)
        code, _ = post(self.server, '/api/v2/control_profiles/clear', {'relay_id': 'r-watch', 'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(self.companion.controls, [])
        _, st = get(self.server, '/api/v2/control_profiles', '')
        self.assertIsNone(st['screens']['r-watch']['active'])
        self.assertEqual(len(st['screens']['r-watch']['profiles']), 2)    # profiles survive a clear

    def test_capture_what_is_on_screen(self):
        rc = remote_controls(self.server)
        rc.set_controls({'relay_id': 'r-watch', 'consent': True, 'controls': [
            {'label': 'Louder', 'skill_id': 'tv_volume_step', 'target': self.keys['tv'], 'params': {'direction': 'up'}}]})
        code, body = post(self.server, '/api/v2/control_profiles/capture', {'relay_id': 'r-watch', 'name': 'From AI'})
        self.assertEqual(code, 200, body)
        b = body['profile']['buttons'][0]
        self.assertEqual((b['label'], b['device'], b['device_key']), ('Louder', 'Android TV', self.keys['tv']))
        code, body = post(self.server, '/api/v2/control_profiles/capture', {'relay_id': 'r-ph', 'name': 'Nothing'})
        self.assertEqual(code, 400)

    def test_restore_active_profile_after_restart(self):
        _, body = self.save()
        post(self.server, '/api/v2/control_profiles/apply', {'relay_id': 'r-watch', 'profile_id': body['profile']['id'], 'consent': True})
        rc = remote_controls(self.server)
        rc.grants.pop('r-watch')                       # fresh PC boot: no grants in memory
        self.companion.controls = []                   # Companion restart wiped its screen
        self.assertEqual(CP.pending(self.server), ['r-watch'])
        self.assertEqual(CP.restore_active(self.server, rc, 'r-watch'), body['profile']['id'])
        self.assertEqual([c['label'] for c in self.companion.controls], ['Volume +', 'Volume -'])
        self.assertIsNone(CP.restore_active(self.server, rc, 'r-watch'))   # already has buttons: untouched

    def test_profile_limit(self):
        for i in range(CP.MAX_PROFILES):
            self.assertEqual(self.save('P%d' % i, [VOL_UP])[0], 200)
        code, body = self.save('One more', [VOL_UP])
        self.assertEqual(code, 400)


if __name__ == '__main__':
    unittest.main()
