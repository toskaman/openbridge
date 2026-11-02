"""Flagship C: composed plan -> installable controls bridge (RED first).

Meta proposes (stubbed, never trusted); compose() allows/refuses each step
against live routes; to_controls() compiles ONLY fully-allowed compositions
into a set_controls body — without consent, which the owner adds after
reviewing the preview. No hardware or model calls: FakeRoutes + world().
"""
import json
import unittest

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.runtime import composer as C
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.remote_controls import RemoteControlError
from tests.runtime.test_composer import DEVICES, FakeRoutes, stub_proposer
from tests.runtime.test_remote_controls import FakeCompanion
from tests.runtime.test_routing import Clock, world

KEY = R.derive_key('654321', 'rn', 'pn')


def composed_ok():
    reply = json.dumps({'steps': [
        {'skill_id': 'tv_volume_step', 'target': 'android tv',
         'params': {'direction': 'up'}},
        {'skill_id': 'tv_volume_step', 'target': 'android tv',
         'params': {'direction': 'down'}},
    ]})
    proposal = C.proposal_from_reply(reply)
    return C.compose(proposal, DEVICES, FakeRoutes())


class ToControlsTest(unittest.TestCase):
    def test_happy_path_compiles_controls_without_consent(self):
        body = C.to_controls(composed_ok(), 'r-watch')
        self.assertEqual(body['relay_id'], 'r-watch')
        self.assertNotIn('consent', body)  # owner adds after preview
        self.assertEqual(len(body['controls']), 2)
        c0 = body['controls'][0]
        self.assertEqual(c0['skill_id'], 'tv_volume_step')
        self.assertEqual(c0['target'], 'dev-tv1')  # device key, not label
        self.assertEqual(c0['params'], {'direction': 'up'})
        self.assertTrue(1 <= len(c0['label']) <= 40)
        self.assertEqual(len(body['preview']['steps']), 2)
        self.assertEqual(body['preview']['refused'], [])

    def test_any_refused_step_fails_closed_with_names(self):
        bad = composed_ok()
        bad['steps'][1] = dict(bad['steps'][1], status='refused',
                               reason='no permitted route (link_down)')
        bad['refused'] = 1
        with self.assertRaises(C.ComposerError) as cm:
            C.to_controls(bad, 'r-watch')
        self.assertIn(bad['steps'][1]['id'], str(cm.exception))

    def test_empty_composition_installs_nothing(self):
        with self.assertRaises(C.ComposerError):
            C.to_controls({'steps': [], 'allowed': 0, 'refused': 0}, 'r-watch')

    def test_hand_forged_allowed_skill_rechecked(self):
        forged = {'steps': [{'id': 's1', 'skill_id': 'self_destruct',
                              'target': 'x', 'params': {},
                              'status': 'allowed', 'device_key': 'dev-tv1'}],
                  'allowed': 1, 'refused': 0}
        with self.assertRaises(C.ComposerError):
            C.to_controls(forged, 'r-watch')

    def test_targeted_skill_without_device_key_rejected(self):
        bad = composed_ok()
        bad['steps'][0] = dict(bad['steps'][0], device_key=None)
        with self.assertRaises(C.ComposerError):
            C.to_controls(bad, 'r-watch')

    def test_labels_sanitized_and_bounded(self):
        ok = composed_ok()
        body = C.to_controls(
            ok, 'r-watch',
            label_fn=lambda skill, target: 'Vol+\x00\x1f<script>' + 'y' * 50)
        for c in body['controls']:
            self.assertTrue(1 <= len(c['label']) <= 40)
            self.assertNotIn('\x00', c['label'])
            self.assertNotIn('<', c['label'])

    def test_over_max_controls_rejected(self):
        many = {'steps': [dict(s, id='s%d' % i)
                          for i, s in enumerate([composed_ok()['steps'][0]] * 13)],
                'allowed': 13, 'refused': 0}
        with self.assertRaises(C.ComposerError):
            C.to_controls(many, 'r-watch')

    def test_proposer_text_never_reaches_skill_or_target(self):
        evil_reply = json.dumps({'steps': [
            {'skill_id': 'tv_volume_step; rm -rf /', 'target': 'android tv',
             'params': {'direction': 'up'}},
        ]})
        proposal = C.proposal_from_reply(evil_reply)
        composed = C.compose(proposal, DEVICES, FakeRoutes())
        self.assertEqual(composed['refused'], 1)
        with self.assertRaises(C.ComposerError):
            C.to_controls(composed, 'r-watch')


class InstallRoundTripTest(unittest.TestCase):
    """to_controls output + explicit consent installs via production API."""

    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        reg = self.server.fabric_registry
        w = reg.upsert([Identifier('android_serial', 'watch-1', True)],
                       category='watch', label='SM-L310',
                       observations=[DeviceObservation(
                           'model', 'SM-L310', 'ADB', 'WIFI', now(), True)])
        reg.devices[w]['handles'] = {'WIFI': 'h-watch-1'}
        reg.link(Link('pc', w, 'WIFI', ('observe', 'read', 'control'),
                      'ADB:device'))
        self.server.fabric_snapshot = reg.snapshot()
        self.server.relays.enroll(
            'r-watch', KEY, 'h-watch-1',
            {'capabilities': ['remote_controls'], 'permissions': {}})
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.rc = remote_controls(self.server)
        self.rc._ensure_thread = lambda: None

    def install(self, body):
        # Real caller shape: show preview, then send only the strict
        # set_controls fields with explicit consent.
        send = {k: body[k] for k in ('relay_id', 'controls')}
        send['consent'] = True
        return self.rc.set_controls(send)

    def test_preview_then_consented_install(self):
        body = C.to_controls(composed_ok(), 'r-watch')
        with self.assertRaises(RemoteControlError):
            self.rc.set_controls(body)  # preview key + no consent: must fail
        st = self.install(body)  # explicit owner act after preview
        self.assertEqual(len(st['controls']), 2)

    def test_revoke_clears_installed_controls(self):
        body = C.to_controls(composed_ok(), 'r-watch')
        self.install(body)
        st = self.rc.set_controls(
            {'relay_id': 'r-watch', 'controls': [], 'consent': True})
        self.assertEqual(st['controls'], [])


if __name__ == '__main__':
    unittest.main()
