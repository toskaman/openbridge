"""ON §5 simulated Meta-generated UI pipeline (SIMULATED_VERIFIED: FakeCompanion + fake runners).

Full chain on REAL production modules with a deterministic FAKE model transport
(model_run_id 'sim-*', never a real inference): fake model UI -> v4_ui.validate_patch
-> dashboards.install_patch -> install on simulated TV relay -> press -> exactly one
simulated-vacuum dispatch -> independent read-back -> revoke -> deny -> reconnect
without duplication -> expired press fails closed -> cleanup. No hardware, no model.
"""
import unittest

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.forge import v4_schemas as S
from src.forge import v4_ui
from src.runtime import dashboards as D
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.remote_controls import REQUEST_TTL_S, RemoteControlError
from tests.runtime.test_remote_controls import KEY, FakeCompanion
from tests.runtime.test_routing import Clock, world


class FakeModelTransport:
    """Deterministic stand-in for a Meta model (SIMULATED)."""
    RUN_ID = 'sim-deterministic-1'

    def propose(self, intent):
        assert 'vacuum' in intent
        return {'schema_version': S.SCHEMA_VERSION, 'patch_id': 'sim-patch-1',
                'target_opaque_id': 'sim-target-1', 'origin': 'meta_generated',
                'model_run_id': self.RUN_ID,
                'widgets': [{'widget_id': 'w-dock', 'kind': 'button', 'label': 'Dock vacuum',
                             'binding_primitive': 'vacuum_command', 'params': {'command': 'dock'}}]}


class SimChain(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        reg = self.server.fabric_registry
        vk = reg.upsert([Identifier('tuya_device_id', 'vac-1', True)], category='vacuum', label='Vacuum',
                        observations=[DeviceObservation('model', 'Vac', 'TUYA_LOCAL', 'LAN', now(), True)])
        reg.link(Link('pc', vk, 'LAN', ('observe', 'read', 'control'), 'TUYA_LOCAL'))
        self.server.fabric_snapshot = reg.snapshot()
        self.keys['vacuum'] = vk
        self.vacuum = {'status': 'cleaning'}          # independent simulated oracle
        self.calls = []

        def tuya(self_, key, params):
            self.calls.append((key, dict(params)))
            if params.get('command') == 'dock':
                self.vacuum['status'] = 'docked'
            return 'EXECUTED', None, 'ok', True, {'command': params.get('command')}

        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, tuya_command=tuya)
        router(self.server).clock = self.clock
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-tv-sim', KEY, 'h-tv-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-tv-sim']['send'] = self.companion
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None
        self.model = FakeModelTransport()
        self.patch = self.model.propose('vacuum panel for the TV')

    def install(self, patch=None, consent=True):
        return D.install_patch(self.rc, 'r-tv-sim', patch or self.patch, self.keys['vacuum'],
                               ('vacuum_command',), consent=consent)

    # ---- §5 acceptance criteria ----

    def test_valid_model_ui_accepted_and_installed(self):
        v4_ui.validate_patch(self.patch, ('vacuum_command',))
        st = self.install()
        cid = st['controls'][0]['control_id']
        self.assertEqual(self.companion.controls, [{'control_id': cid, 'label': 'Dock vacuum'}])

    def test_invalid_model_ui_rejected(self):
        bad = dict(self.patch, widgets=[])
        with self.assertRaises(v4_ui.UIError):
            v4_ui.validate_patch(bad, ('vacuum_command',))
        bad2 = {'schema_version': S.SCHEMA_VERSION, 'patch_id': 'x', 'target_opaque_id': 'y',
                'origin': 'meta_generated', 'model_run_id': 'sim-2',
                'widgets': [{'widget_id': 'w', 'kind': 'button', 'label': 'X',
                             'binding_primitive': 'invented.skill', 'params': {}}]}
        with self.assertRaises(v4_ui.UIError):
            v4_ui.validate_patch(bad2, ('vacuum_command',))

    def test_unsupported_capability_rejected(self):
        other = {'schema_version': S.SCHEMA_VERSION, 'patch_id': 'x', 'target_opaque_id': 'y',
                 'origin': 'meta_generated', 'model_run_id': 'sim-3',
                 'widgets': [{'widget_id': 'w', 'kind': 'button', 'label': 'Vol',
                              'binding_primitive': 'tv_volume_step', 'params': {'direction': 'up'}}]}
        v4_ui.validate_patch(other, ('vacuum_command', 'tv_volume_step'))
        with self.assertRaises(D.DashboardError):
            self.install(patch=other)          # offered allowlist is vacuum-only

    def test_consent_required(self):
        with self.assertRaises(D.DashboardError):
            self.install(consent=False)
        with self.assertRaises(RemoteControlError):
            self.rc.set_controls({'relay_id': 'r-tv-sim', 'controls': [], 'consent': False})

    def test_press_dispatches_exactly_once_with_read_back(self):
        st = self.install()
        cid = st['controls'][0]['control_id']
        self.companion.press(cid)
        self.assertEqual(self.rc.poll_once(), 1)
        self.assertEqual(self.calls, [(self.keys['vacuum'], {'command': 'dock'})])
        self.assertEqual(self.vacuum['status'], 'docked')     # independent oracle
        self.assertEqual(self.rc.poll_once(), 0)              # empty queue: nothing more
        self.assertEqual(len(self.calls), 1)

    def test_resent_request_id_dispatches_once(self):
        st = self.install()
        cid = st['controls'][0]['control_id']
        rid = self.companion.press(cid)
        self.companion.queue.append(dict(self.companion.queue[0], request_id=rid))
        self.companion.queue[0]['request_id'] = rid
        self.assertEqual(self.rc.poll_once(), 2)
        self.assertEqual(len(self.calls), 1)                  # second delivery deduplicated

    def test_revoke_blocks_further_requests(self):
        st = self.install()
        cid = st['controls'][0]['control_id']
        self.rc.set_controls({'relay_id': 'r-tv-sim', 'controls': [], 'consent': True})
        self.assertFalse(self.rc.grants.get('r-tv-sim'))   # revoke clears the grant
        self.companion.press(cid)
        self.companion.queue.append({'request_id': 'r' * 32, 'control_id': cid,
                                     'pressed_at': int(self.clock() * 1000)})
        self.assertEqual(self.rc.poll_once(), 0)
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(RemoteControlError, 'no longer authorized'):
            self.rc.invoke_now('r-tv-sim', cid)

    def test_reconnect_does_not_duplicate(self):
        st = self.install()
        cid = st['controls'][0]['control_id']
        self.companion.press(cid)
        self.assertEqual(self.rc.poll_once(), 1)
        relay = self.server.relays.relays['r-tv-sim']
        relay['online'] = False
        self.assertEqual(self.rc.poll_once(), 0)
        relay['online'] = True
        self.assertEqual(self.rc.poll_once(), 0)
        self.assertEqual(len(self.calls), 1)

    def test_expired_press_fails_closed(self):
        st = self.install()
        cid = st['controls'][0]['control_id']
        self.companion.queue.append({'request_id': 'e' * 32, 'control_id': cid,
                                     'pressed_at': int((self.clock() - REQUEST_TTL_S - 5) * 1000)})
        self.rc.poll_once()
        self.assertEqual(self.calls, [])

    def test_session_cleanup_complete(self):
        self.install()
        out = executor(self.server).execute('relay_revoke', self.keys['tv'],
                                            {'relay_id': 'r-tv-sim'}, consent=True)
        self.assertEqual(out['state'], 'VERIFIED')
        self.assertNotIn('r-tv-sim', self.server.relays.relays)
        self.rc.close()
        self.assertTrue(self.rc.closed)
        self.assertEqual(self.rc.grants, {})


if __name__ == '__main__':
    unittest.main()
