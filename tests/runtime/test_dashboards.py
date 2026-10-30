"""§8 watch dashboards: generate/patch/save/restore relay control sets.

SIMULATED_VERIFIED: FakeCompanion mirrors RelayServer.java; no devices.
Live watch proof is owner-gated (watch offline, pairing needs owner-tapped code).
"""
import tempfile
import unittest

from src.fabric import relay as R
from src.runtime.api_v2 import executor, remote_controls
from src.runtime import dashboards as D
from src.runtime.remote_controls import RemoteControlError
from src.runtime.state_store import StateStore
from tests.runtime.test_remote_controls import FakeCompanion, KEY
from tests.runtime.test_routing import Clock, world


class Dashboards(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-watch', KEY, 'h-ph-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None
        self.store = D.DashStore(StateStore.for_server(self.server))

    def labels(self):
        return [c['label'] for c in self.companion.controls]

    def test_create_vacuum_dashboard(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        self.assertEqual(self.labels(), ['Vacuum start', 'Vacuum pause', 'Return to dock', 'Find me'])
        skills = {c['skill_id'] for c in self.rc.grants['r-watch'].values()}
        self.assertEqual(skills, {'vacuum_command'})

    def test_create_tv_dashboard(self):
        D.create(self.rc, 'r-watch', 'tv', 'tv-key')
        self.assertEqual(self.labels(), ['Volume +', 'Volume -', 'YouTube'])

    def test_unknown_area_rejected(self):
        with self.assertRaises(D.DashboardError):
            D.create(self.rc, 'r-watch', 'toaster', 'x')

    def test_area_labels_fit_companion_limits(self):
        for area in D.AREAS:
            for c in D.AREAS[area]('k'):
                self.assertTrue(0 < len(c['label']) <= 40, c['label'])
                self.assertIn('skill_id', c)

    def test_patch_add_and_remove(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        D.patch(self.rc, 'r-watch',
                add=[{'label': 'Volume +', 'skill_id': 'tv_volume_step',
                      'target': 'tv-key', 'params': {'direction': 'up'}}])
        self.assertIn('Volume +', self.labels())
        D.patch(self.rc, 'r-watch', remove=['Vacuum pause'])
        self.assertNotIn('Vacuum pause', self.labels())
        self.assertIn('Return to dock', self.labels())

    def test_patch_remove_unknown_is_an_error_not_silent(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        before = self.labels()
        with self.assertRaises(D.DashboardError):
            D.patch(self.rc, 'r-watch', remove=['Nope button'])
        self.assertEqual(self.labels(), before)

    def test_patch_add_invalid_propagates(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        with self.assertRaises(RemoteControlError):
            D.patch(self.rc, 'r-watch',
                    add=[{'label': 'Bad', 'skill_id': 'nope', 'params': {}}])

    def test_save_list_load_delete_round_trip(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        D.patch(self.rc, 'r-watch', remove=['Find me'])
        self.store.save('r-watch', 'evening', D.defs(self.rc, 'r-watch'))
        self.assertEqual(self.store.list(), ['evening'])
        D.create(self.rc, 'r-watch', 'tv', 'tv-key')
        self.assertEqual(self.labels(), ['Volume +', 'Volume -', 'YouTube'])
        D.load(self.store, self.rc, 'evening')
        self.assertEqual(self.labels(), ['Vacuum start', 'Vacuum pause', 'Return to dock'])
        self.store.delete('evening')
        self.assertEqual(self.store.list(), [])

    def test_save_validates_name_and_defs(self):
        with self.assertRaises(D.DashboardError):
            self.store.save('r-watch', 'bad name!', [])
        with self.assertRaises(D.DashboardError):
            self.store.save('r-watch', 'ok', [])

    def test_load_unknown_rejected(self):
        with self.assertRaises(D.DashboardError):
            D.load(self.store, self.rc, 'ghost')

    def test_restore_on_reconnect_reinstalls_last(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        self.store.save('r-watch', 'evening', D.defs(self.rc, 'r-watch'))
        self.rc.grants.pop('r-watch')  # server reboot forgot the in-memory grants
        self.assertEqual(D.restore_on_reconnect(self.rc, self.store, 'r-watch'), 'evening')
        self.assertEqual(self.labels(), ['Vacuum start', 'Vacuum pause', 'Return to dock', 'Find me'])

    def test_restore_is_noop_when_grants_present(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        self.store.save('r-watch', 'evening', D.defs(self.rc, 'r-watch'))
        self.assertIsNone(D.restore_on_reconnect(self.rc, self.store, 'r-watch'))

    def test_restore_without_save_is_noop(self):
        self.assertIsNone(D.restore_on_reconnect(self.rc, self.store, 'r-watch'))

    def test_repush_resends_same_ids(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        before = [c['control_id'] for c in self.companion.controls]
        self.companion.controls = []  # app restart wiped the device UI
        self.assertTrue(D.repush_current(self.rc, 'r-watch'))
        self.assertEqual([c['control_id'] for c in self.companion.controls], before)
        self.assertEqual(self.labels(), ['Vacuum start', 'Vacuum pause', 'Return to dock', 'Find me'])

    def test_repush_with_no_grants_is_false(self):
        self.assertFalse(D.repush_current(self.rc, 'r-watch'))

    def test_ensure_controls_repush_restore_or_none(self):
        self.assertIsNone(D.ensure_controls(self.rc, self.store, 'r-watch'))
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        self.assertEqual(D.ensure_controls(self.rc, self.store, 'r-watch'), 'repush')
        self.store.save('r-watch', 'evening', D.defs(self.rc, 'r-watch'))
        self.rc.grants.pop('r-watch')
        self.assertEqual(D.ensure_controls(self.rc, self.store, 'r-watch'), 'restore:evening')

    def test_ensure_controls_never_raises(self):
        class Broken:
            grants = {'r-watch': {'x': 1}}
        self.assertIsNone(D.ensure_controls(Broken(), self.store, 'r-watch'))

    def test_reconnect_repushes_live_grants(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        before = [c['control_id'] for c in self.companion.controls]
        self.companion.controls = []  # app restart wiped the device UI
        self.server.relays.relays['r-watch']['online'] = False
        self.clock.t += 10
        self.rc.poll_once()
        self.assertTrue(self.server.relays.relays['r-watch']['online'])
        self.assertEqual([c['control_id'] for c in self.companion.controls], before)
        self.assertEqual(self.labels(), ['Vacuum start', 'Vacuum pause', 'Return to dock', 'Find me'])

    def test_fresh_boot_restores_saved_dashboard_on_reconnect(self):
        D.create(self.rc, 'r-watch', 'vacuum', 'vacuum-key')
        self.store.save('r-watch', 'evening', D.defs(self.rc, 'r-watch'))
        self.rc.grants.pop('r-watch')  # server reboot
        self.companion.controls = []  # app restart wiped the device UI
        self.server.relays.relays['r-watch']['online'] = False
        self.clock.t += 10
        self.rc.poll_once()
        self.assertEqual(self.labels(), ['Vacuum start', 'Vacuum pause', 'Return to dock', 'Find me'])
        self.assertTrue(self.rc.grants.get('r-watch'))


if __name__ == '__main__':
    unittest.main()
