"""Offline end-to-end of dev/run_g3_smoke.main(): fake HTTP server, fake Meta transport, temp ledger.
No network, no hardware, no spend. Exercises the sealed-spec path and the default mute smoke."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import dev.run_g3_smoke as R
from dev import g3_task as G
from src.substrate import registry as REG

VOL = {'spec_version': 1, 'task_id': 'e2e-volume', 'intent': 'Set the TV media volume to exactly 7.',
       'target_category': 'tv', 'offer': ['setting.set_exact', 'state.read_setting', 'state.audio'],
       'allowed_effects': [{'primitive_id': 'setting.set_exact', 'args': {'setting': 'media_volume', 'value': 7}}],
       'oracle': {'action': 'get', 'args': {'setting': 'media_volume'}, 'field': 'value'}, 'expect': {'value': 7},
       'restore': {'mode': 'owner_action', 'action': 'set', 'args': {'setting': 'media_volume', 'value': '$pre'}}}


class FakeTV:
    def __init__(self):
        self.vol, self.muted, self.revoked, self.calls = 20, False, False, []

    def __call__(self, path, body=None):
        self.calls.append(path)
        if path == '/api/fabric-discover':
            return 200, {'devices': [{'key': 'k1', 'category': 'tv'}],
                         'links': [{'child': 'k1', 'grants': ['observe', 'read', 'control']}]}
        if path.startswith('/api/v2/facts/signed'):
            return 200, {'device_fingerprint': 'fp-0123456789abcdef',
                         'facts': [{'fact_id': 'f-0000000000000001', 'name': 'category', 'value': 'tv', 'source': 'REGISTRY', 'verified': True}]}
        if path == '/api/v2/primitives/catalog':
            return 200, {'primitives': REG.catalog()}
        if path == '/api/v2/manifests/compile':
            return 200, {'manifest_hash': 'sha256:' + 'a' * 64, 'permissions': ['control', 'read'], 'dispatches': 2}
        if path == '/api/v2/manifests/grant':
            return 200, {'grant': {'grant_id': 'g-1'}, 'manifest_hash': 'sha256:' + 'a' * 64}
        if path == '/api/v2/manifests/revoke':
            self.revoked = True; return 200, {'revoked': 'g-1'}
        if path == '/api/v2/manifests/receipts':
            return 200, {'receipts': []}
        if path == '/api/v2/manifests/invoke':
            if self.revoked:
                return 403, {'code': 'GRANT_REVOKED'}
            for st in body['manifest']['steps']:
                if st['primitive_id'] == 'setting.set_exact':
                    self.vol = st['args']['value']
                if st['primitive_id'] == 'input.key' and st['args'] == {'key': 'mute'}:
                    self.muted = not self.muted
            return 200, {'status': 'EXECUTED', 'steps': []}
        if path == '/api/v2/execute':
            p = body['params']
            if p['action'] == 'get':
                return 200, {'state': 'VERIFIED', 'result': {'setting': 'media_volume', 'value': self.vol}, 'transaction_id': 'tx'}
            if p['action'] == 'set':
                self.vol = p['args']['value']; return 200, {'state': 'VERIFIED', 'result': {}, 'transaction_id': 'tx'}
            if p['action'] == 'audio_state':
                return 200, {'state': 'EXECUTED', 'result': {'muted': self.muted, 'readable': True}, 'transaction_id': 'tx'}
        raise AssertionError('unexpected ' + path)


def model_reply(bundle_prompt, chain):
    import re
    dev = re.search(r'opaque:device:[0-9a-f]+', bundle_prompt)[0]
    fact = re.search(r'opaque:fact:[0-9a-f]+', bundle_prompt)[0]
    return json.dumps({'schema_version': 1, 'candidate_id': 'cand-e2e', 'origin': 'meta_generated', 'intent': 'x',
                       'target_opaque_id': dev, 'primitive_chain': chain, 'preconditions': [], 'postconditions': [],
                       'required_grants': ['control', 'read'], 'evidence_refs': [fact]})


class E2E(unittest.TestCase):
    def run_main(self, chain, spec=None, extra=()):
        tv = FakeTV()
        d = tempfile.mkdtemp()
        authz = Path(d) / 'authz.txt'; authz.write_text('test authz', encoding='utf-8')
        argv = ['x', '--base', 'http://127.0.0.1:1', '--observation-id', 'obs-e2e', '--observed-at',
                datetime.now(timezone.utc).isoformat(), '--free-balance-usd', '100', '--authz-file', str(authz),
                '--out', d] + list(extra)
        if spec is not None:
            p = Path(d) / 'spec.json'; p.write_text(json.dumps(spec), encoding='utf-8')
            argv += ['--task-spec', str(p), '--task-sha256', G.spec_sha256(spec)]

        def transport(payload):
            return {'id': 'r1', 'model': 'muse-spark-1.3', 'usage': {'prompt_tokens': 10, 'completion_tokens': 10},
                    'choices': [{'finish_reason': 'stop', 'message': {'content': model_reply(payload['messages'][0]['content'], chain)}}]}
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(R, 'Http', lambda base: tv), \
                mock.patch('src.ai.broker.MetaTransport', lambda key: transport), \
                mock.patch('src.ai.broker.resolve_ledger', lambda explicit=None: Path(d) / 'ledger.sqlite3'), \
                mock.patch('src.fabric.credential_vault.Vault') as V, mock.patch('time.sleep'):
            V.return_value.get.return_value = 'test-key'
            rc = R.main()
        return rc, json.loads((Path(d) / 'G3_SMOKE_TRANSCRIPT.json').read_text(encoding='utf-8')), tv

    def test_sealed_volume_task_success_and_restore(self):
        rc, T, tv = self.run_main([{'primitive_id': 'setting.set_exact', 'input': {'setting': 'media_volume', 'value': 7}},
                                   {'primitive_id': 'state.read_setting', 'input': {'setting': 'media_volume'}}], spec=VOL)
        self.assertEqual((rc, T['status'], T['kind'], tv.vol), (0, 'SUCCESS', 'G3_SEALED_TASK', 20), T.get('predicate'))
        self.assertEqual(T['task_sha256'], G.spec_sha256(VOL))

    def test_plan_outside_sealed_effects_is_killed_before_grant(self):
        rc, T, tv = self.run_main([{'primitive_id': 'setting.set_exact', 'input': {'setting': 'media_volume', 'value': 70}}], spec=VOL)
        self.assertEqual(T['status'], 'KILL')
        self.assertNotIn('/api/v2/manifests/grant', tv.calls)

    def test_default_mute_smoke_still_works(self):
        rc, T, tv = self.run_main([{'primitive_id': 'input.key', 'input': {'key': 'mute'}},
                                   {'primitive_id': 'state.audio', 'input': {}}])
        self.assertEqual((T['status'], T['kind'], tv.muted), ('SUCCESS', 'G3_INTEGRATION_SMOKE', False), T.get('predicate'))


if __name__ == '__main__':
    unittest.main()
