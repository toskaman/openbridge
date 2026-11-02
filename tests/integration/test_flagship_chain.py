"""Flagship C end-to-end chain (SIMULATED_VERIFIED, no hardware/model calls).

Request: 'I want volume up and down for the television on my wrist'.
The proposer replays a FROZEN genuine Meta reply (fixture
flagship_paraphrase_reply.json — llama3.2:3b-instruct-q4_K_M, temp 0,
02-Nov-2026, 187 chars; provenance: live ablation run, see
flagship-breakthrough/MODEL_ABLATION_RESULTS.md). Everything downstream
is production code over doubles: real Router over world(), production
set_controls/process/revoke, FakeCompanion mirroring RelayServer.java.

Chain: replay -> proposal -> compose (real routes) -> preview ->
consented install on watch relay -> exactly-one press EXECUTED ->
re-press deduped -> revoke -> press denied.
"""
import json
import unittest
from pathlib import Path

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.runtime import composer as C
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from tests.runtime.test_remote_controls import FakeCompanion
from tests.runtime.test_routing import Clock, world

KEY = R.derive_key('654321', 'rn', 'pn')
FIXTURE = (Path(__file__).parent / 'flagship_paraphrase_reply.json'
           ).read_text(encoding='utf-8')


class FlagshipChainTest(unittest.TestCase):
    def test_model_reply_to_revoked_press(self):
        clock = Clock()
        server, keys = world(clock)
        reg = server.fabric_registry
        w = reg.upsert([Identifier('android_serial', 'watch-1', True)],
                       category='watch', label='SM-L310',
                       observations=[DeviceObservation(
                           'model', 'SM-L310', 'ADB', 'WIFI', now(), True)])
        reg.devices[w]['handles'] = {'WIFI': 'h-watch-1'}
        reg.link(Link('pc', w, 'WIFI', ('observe', 'read', 'control'),
                      'ADB:device'))
        server.fabric_snapshot = reg.snapshot()
        devices = [{'key': keys['tv'], 'label': 'android tv',
                    'category': 'tv', 'handles': {'WIFI': 'h-tv'}},
                   {'key': w, 'label': 'Galaxy Watch7', 'category': 'watch',
                    'handles': {'WIFI': 'h-watch-1'}}]

        # 1. frozen genuine model reply -> proposal -> real-route compose
        proposal = C.proposal_from_reply(FIXTURE)
        composed = C.compose(proposal, devices, router(server))
        self.assertEqual(composed['allowed'], 2)
        self.assertEqual(composed['refused'], 0)
        self.assertTrue(all(s['device_key'] == keys['tv']
                            for s in composed['steps']))

        # 2. preview (no consent inside) -> consented install on watch relay
        body = C.to_controls(composed, 'r-watch')
        self.assertEqual(len(body['preview']['steps']), 2)
        server.relays.enroll(
            'r-watch', KEY, 'h-watch-1',
            {'capabilities': ['remote_controls'], 'permissions': {}})
        companion = FakeCompanion()
        companion.clock = clock
        server.relays.relays['r-watch']['send'] = companion
        rc = remote_controls(server)
        rc.clock = clock
        rc._ensure_thread = lambda: None
        router(server).clock = clock
        calls = []
        ex = executor(server)
        def fake_runner(_executor, key, params):
            calls.append((key, params))
            return 'EXECUTED', None, None, True, {}
        ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake_runner)
        st = rc.set_controls({'relay_id': 'r-watch',
                              'controls': body['controls'], 'consent': True})
        self.assertEqual(len(st['controls']), 2)
        cid = st['controls'][0]['control_id']

        # 3. exactly-one press runs once with owner params
        rid = companion.press(cid)
        self.assertEqual(rc.poll_once(), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], keys['tv'])
        self.assertIn('done', companion.results[-1]['text'])
        clock.t += 2
        companion.press(cid, request_id=rid)  # re-sent press deduped
        rc.poll_once()
        self.assertEqual(len(calls), 1)

        # 4. revoke -> subsequent press denied
        rc.set_controls({'relay_id': 'r-watch', 'controls': [],
                         'consent': True})
        companion.press(cid)
        self.assertEqual(rc.poll_once(), 0)
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
