"""Campaign Two §4.2 control-surface migration (SIMULATED_VERIFIED: FakeCompanions, fake device runners).

Owner request: "Remove the volume controls from my watch and put them on my TV."
"""
import copy
import tempfile
import unittest
from types import SimpleNamespace

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.fabric.registry import Registry
from src.fabric.relay import RelayManager
from src.fabric.session import SessionJournal
from src.runtime import migrate as M
from src.runtime.api_v2 import executor, post, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.relay_health import RelayLedger
from tests.runtime.test_remote_controls import FakeCompanion, KEY
from tests.runtime.test_routing import Clock

KEY2 = R.derive_key('111111', 'a', 'b')

TEXT = 'Remove the volume controls from my watch and put them on my TV.'


def world(clock):
    reg = Registry()
    keys = {}
    for name, cat, serial in (('Android TV', 'tv', 'tv-1'), ('SM-L310', 'watch', 'watch-1')):
        k = reg.upsert([Identifier('android_serial', serial, True)], category=cat, label=name,
                       observations=[DeviceObservation('model', name, 'ADB', 'WIFI', now(), True)])
        reg.devices[k]['handles'] = {'WIFI': 'h-' + serial}
        reg.link(Link('pc', k, 'WIFI', ('observe', 'read', 'control'), 'ADB:device'))
        keys[cat] = k
    relays = RelayManager(transport=lambda relay, msg: {})
    relays.enroll('r-watch', KEY, 'h-watch-1',
                  {'capabilities': ['remote_controls'],
                   'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
    relays.enroll('r-tv', KEY2, 'h-tv-1',
                  {'capabilities': ['remote_controls'],
                   'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
    server = SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(), relays=relays,
                             relay_ledger=RelayLedger(clock=clock),
                             session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'),
                             fabric_salt=b't', runtime_executor=None, skill_router=None,
                             remote_controls=None)
    return server, keys


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.watch_comp = FakeCompanion()
        self.watch_comp.clock = self.clock
        self.tv_comp = FakeCompanion(key=KEY2)
        self.tv_comp.clock = self.clock
        self.server.relays.relays['r-watch']['send'] = self.watch_comp
        self.server.relays.relays['r-tv']['send'] = self.tv_comp
        self.calls = []

        def fake(self_, key, params):
            self.calls.append((key, params))
            return 'EXECUTED', None, None, True, {}

        ex = executor(self.server)
        ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake)
        router(self.server).clock = self.clock
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None
        tv = self.keys['tv']
        self.rc.set_controls({'relay_id': 'r-watch', 'controls': [
            {'label': 'TV volume +', 'skill_id': 'tv_volume_step', 'target': tv, 'params': {'direction': 'up'}},
            {'label': 'TV volume -', 'skill_id': 'tv_volume_step', 'target': tv, 'params': {'direction': 'down'}},
            {'label': 'YouTube', 'skill_id': 'app_launch', 'target': tv,
             'params': {'package': 'com.google.android.youtube.tv'}}], 'consent': True})
        self.rc.set_controls({'relay_id': 'r-tv', 'controls': [
            {'label': 'Chrome', 'skill_id': 'app_launch', 'target': tv,
             'params': {'package': 'com.android.chrome'}}], 'consent': True})

    def labels(self, rid):
        return sorted(g['label'] for g in (self.rc.grants.get(rid) or {}).values())

    def ids(self, rid):
        return {g['label']: cid for cid, g in (self.rc.grants.get(rid) or {}).items()}

    def perms_snapshot(self):
        relays = self.server.relays.relays
        return (copy.deepcopy({rid: r['permissions'] for rid, r in relays.items()}),
                sorted((l['parent'], l['child'], l['transport'], tuple(sorted(l['grants'])))
                       for l in self.server.fabric_snapshot['links']))

    def propose_volumes(self):
        return M.propose(self.server, TEXT)


class Propose(Base):
    def test_canonical_request_resolves_controls_bindings_and_interfaces(self):
        out = self.propose_volumes()
        self.assertEqual(out['outcome'], 'proposal')
        p = out['proposal']
        self.assertEqual(p['source']['relay_id'], 'r-watch')
        self.assertEqual(p['source']['category'], 'watch')
        self.assertEqual(p['destination']['relay_id'], 'r-tv')
        self.assertEqual(sorted(c['label'] for c in p['controls']), ['TV volume +', 'TV volume -'])
        for c in p['controls']:
            self.assertEqual(c['skill_id'], 'tv_volume_step')
            self.assertEqual(c['target'], self.keys['tv'])
            self.assertIn(c['params']['direction'], ('up', 'down'))
        self.assertTrue(p['target_support']['supported'])
        self.assertFalse(p['permission_delta']['new_permissions_required'])
        disp = p['old_grant_disposition']
        self.assertEqual(disp['action'], 'revoke_source_controls')
        self.assertEqual(len(disp['revoked_control_ids']), 2)
        self.assertTrue(disp['device_permissions_untouched'])
        self.assertTrue(disp['relay_permissions_untouched'])
        self.assertTrue(p['rollback']['eligible'])
        self.assertTrue(p['consent_required'])

    def test_move_to_variant_parses(self):
        out = M.propose(self.server, 'Move the volume controls from my watch to my TV.')
        self.assertEqual(out['outcome'], 'proposal')
        self.assertEqual(out['proposal']['source']['relay_id'], 'r-watch')
        self.assertEqual(out['proposal']['destination']['relay_id'], 'r-tv')

    def test_explicit_kwargs_override_text(self):
        out = M.propose(self.server, 'hello?', source='r-watch', target='r-tv', match='volume')
        self.assertEqual(out['outcome'], 'proposal')

    def test_permission_delta_reports_missing_grant_but_still_proposes(self):
        for l in self.server.fabric_snapshot['links']:
            if l['child'] == self.keys['tv']:
                l['grants'] = ['observe']
        out = self.propose_volumes()
        self.assertEqual(out['outcome'], 'proposal')
        delta = out['proposal']['permission_delta']
        self.assertTrue(delta['new_permissions_required'])
        self.assertEqual(delta['missing'][0]['missing_grant'], 'control')
        self.assertEqual(delta['missing'][0]['target'], self.keys['tv'])


class Ambiguous(Base):
    def test_missing_pieces_ask_for_clarification(self):
        for text in ('move the volume controls',
                     'Remove the volume controls from my watch',
                     'Put the volume controls on my TV',
                     'hello?'):
            out = M.propose(self.server, text)
            self.assertEqual(out['outcome'], 'needs_clarification', text)
            self.assertIn('clarifying_question', out)
        self.assertIn('destination interface',
                      M.propose(self.server, 'Remove the volume controls from my watch')['clarifying_question'])
        self.assertIn('source interface',
                      M.propose(self.server, 'Put the volume controls on my TV')['clarifying_question'])

    def test_two_watches_ask_which_source(self):
        reg = self.server.fabric_registry
        w2 = reg.upsert([Identifier('android_serial', 'watch-2', True)], category='watch', label='SM-L320',
                        observations=[DeviceObservation('model', 'SM-L320', 'ADB', 'WIFI', now(), True)])
        reg.devices[w2]['handles'] = {'WIFI': 'h-watch-2'}
        reg.link(Link('pc', w2, 'WIFI', ('observe', 'read', 'control'), 'ADB:device'))
        self.server.fabric_snapshot = reg.snapshot()
        self.server.relays.enroll('r-watch2', R.derive_key('222222', 'c', 'd'), 'h-watch-2',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        out = self.propose_volumes()
        self.assertEqual(out['outcome'], 'needs_clarification')
        self.assertEqual(len(out['candidates']), 2)
        # Naming the relay id disambiguates.
        out = M.propose(self.server, 'Remove the volume controls from r-watch and put them on my TV.')
        self.assertEqual(out['outcome'], 'proposal')

    def test_unknown_or_impossible_inputs_refuse(self):
        out = M.propose(self.server, 'Remove the volume controls from my fridge and put them on my TV.')
        self.assertEqual(out['outcome'], 'refusal')
        out = M.propose(self.server, 'Remove the bass boosters from my watch and put them on my TV.')
        self.assertEqual(out['outcome'], 'refusal')
        self.assertIn('YouTube', out['reason'])
        out = M.propose(self.server, 'Remove the volume controls from my watch and put them on my watch.')
        self.assertEqual(out['outcome'], 'refusal')

    def test_target_support_refusals(self):
        self.server.relays.relays['r-tv']['capabilities'] = {'ble_scan'}
        out = self.propose_volumes()
        self.assertEqual(out['outcome'], 'refusal')
        self.assertIn('no remote controls', out['reason'])

    def test_full_destination_refuses(self):
        tv = self.keys['tv']
        many = [{'label': 'C%d' % i, 'skill_id': 'device_facts', 'target': tv, 'params': {}} for i in range(11)]
        self.rc.set_controls({'relay_id': 'r-tv', 'controls': many, 'consent': True})
        out = self.propose_volumes()
        self.assertEqual(out['outcome'], 'refusal')
        self.assertIn('exceed the 12 limit', out['reason'])


class Apply(Base):
    def test_apply_moves_controls_and_keeps_unrelated_ones(self):
        p = self.propose_volumes()['proposal']
        before = self.perms_snapshot()
        receipt = M.apply(self.server, p, True)
        self.assertTrue(receipt['migration_id'].startswith('mig-'))
        self.assertEqual(self.labels('r-watch'), ['YouTube'])
        self.assertEqual(self.labels('r-tv'), ['Chrome', 'TV volume +', 'TV volume -'])
        self.assertGreater(receipt['source_generation_after'], receipt['source_generation_before'])
        self.assertGreater(receipt['destination_generation_after'], receipt['destination_generation_before'])
        self.assertEqual(self.perms_snapshot(), before)
        # Device UIs were replaced wholesale (labels only reach the device).
        self.assertEqual(sorted(c['label'] for c in self.watch_comp.controls), ['YouTube'])
        self.assertEqual(sorted(c['label'] for c in self.tv_comp.controls),
                         ['Chrome', 'TV volume +', 'TV volume -'])

    def test_stale_source_controls_are_never_actionable_after_revocation(self):
        p = self.propose_volumes()['proposal']
        old_ids = list(p['old_grant_disposition']['revoked_control_ids'])
        old_watch_cids = set(self.ids('r-watch').values())
        M.apply(self.server, p, True)
        self.assertFalse(set(old_ids) & set(self.ids('r-watch').values()))
        self.assertFalse(old_watch_cids & set(self.ids('r-watch').values()))
        # A stale device UI that missed the update still holds the old ids.
        for i, cid in enumerate(old_ids):
            self.watch_comp.queue.append({'request_id': '%032x' % (500 + i), 'control_id': cid,
                                          'pressed_at': int(self.clock.t * 1000)})
        self.assertEqual(self.rc.poll_once(), 0)
        self.assertEqual(self.calls, [])
        # Even a drained request that reaches dispatch after the grant died answers REVOKED.
        self.watch_comp.pending['b' * 32] = True  # drained by get_requests before the re-grant landed
        entry = self.rc.process('r-watch', {'request_id': 'b' * 32, 'control_id': old_ids[0],
                                            'pressed_at': int(self.clock.t * 1000)})
        self.assertEqual(entry['state'], 'REVOKED')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.watch_comp.results[-1]['state'], 'REVOKED')
        self.assertIn('no longer authorized', self.watch_comp.results[-1]['text'])
        # The migrated bindings work on the destination; the kept one on the source.
        self.tv_comp.press(self.ids('r-tv')['TV volume +'])
        self.assertEqual(self.rc.poll_once(), 1)
        self.assertEqual(self.calls, [(self.keys['tv'], {'action': 'key', 'args': {'key': 'volume_up'}})])
        self.clock.t += 1
        self.watch_comp.press(self.ids('r-watch')['YouTube'])
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[1][1]['action'], 'launch_app')

    def test_removing_a_control_revokes_no_unrelated_permission(self):
        before = self.perms_snapshot()
        M.apply(self.server, self.propose_volumes()['proposal'], True)
        self.assertEqual(self.perms_snapshot(), before)
        for rid in ('r-watch', 'r-tv'):
            self.assertTrue(self.server.relays.relays[rid]['permissions']['BLUETOOTH_SCAN'])
            self.assertTrue(self.server.relays.relays[rid]['permissions']['owner_enabled'])
        tv_links = [l for l in self.server.fabric_snapshot['links'] if l['child'] == self.keys['tv']]
        self.assertEqual(sorted(tv_links[0]['grants']), ['control', 'observe', 'read'])
        # Unrelated controls on both relays still dispatch (functional proof).
        self.watch_comp.press(self.ids('r-watch')['YouTube'])
        self.clock.t += 1
        self.tv_comp.press(self.ids('r-tv')['Chrome'])
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 2)

    def test_apply_needs_consent_and_a_fresh_proposal(self):
        p = self.propose_volumes()['proposal']
        with self.assertRaises(M.MigrationError) as e:
            M.apply(self.server, p, False)
        self.assertEqual(e.exception.status, 400)
        with self.assertRaises(M.MigrationError) as e:
            M.apply(self.server, {}, True)
        self.assertEqual(e.exception.status, 400)
        # The owner re-grants the source after the proposal: the world changed.
        tv = self.keys['tv']
        self.rc.set_controls({'relay_id': 'r-watch', 'controls': [
            {'label': 'TV volume +', 'skill_id': 'tv_volume_step', 'target': tv, 'params': {'direction': 'up'}}],
            'consent': True})
        with self.assertRaises(M.MigrationError) as e:
            M.apply(self.server, p, True)
        self.assertEqual(e.exception.status, 409)
        self.assertEqual(self.labels('r-tv'), ['Chrome'])  # destination untouched


class Rollback(Base):
    def test_rollback_restores_source_and_prunes_destination(self):
        before = self.perms_snapshot()
        receipt = M.apply(self.server, self.propose_volumes()['proposal'], True)
        # The owner adds a control on the destination after the migration.
        tv = self.keys['tv']
        dst = [{'label': g['label'], 'skill_id': g['skill_id'], 'target': g.get('target'),
                'params': dict(g.get('params') or {})}
               for _, g in sorted(self.rc.grants['r-tv'].items())]
        self.rc.set_controls({'relay_id': 'r-tv', 'controls': dst + [
            {'label': 'New', 'skill_id': 'app_launch', 'target': tv,
             'params': {'package': 'com.example.new'}}], 'consent': True})
        res = M.rollback(self.server, receipt, True)
        self.assertTrue(res['rolled_back'])
        self.assertEqual(res['migration_id'], receipt['migration_id'])
        self.assertEqual(self.labels('r-watch'), ['TV volume +', 'TV volume -', 'YouTube'])
        self.assertEqual(self.labels('r-tv'), ['Chrome', 'New'])  # migrated pruned, owner change kept
        self.assertEqual(self.perms_snapshot(), before)
        # Restored controls are actionable again.
        self.watch_comp.press(self.ids('r-watch')['TV volume -'])
        self.rc.poll_once()
        self.assertEqual(self.calls, [(self.keys['tv'], {'action': 'key', 'args': {'key': 'volume_down'}})])
        # Idempotent: a second rollback is a safe no-op.
        M.rollback(self.server, receipt, True)
        self.assertEqual(self.labels('r-watch'), ['TV volume +', 'TV volume -', 'YouTube'])
        self.assertEqual(self.labels('r-tv'), ['Chrome', 'New'])

    def test_rollback_needs_consent_and_a_valid_receipt(self):
        receipt = M.apply(self.server, self.propose_volumes()['proposal'], True)
        with self.assertRaises(M.MigrationError) as e:
            M.rollback(self.server, receipt, False)
        self.assertEqual(e.exception.status, 400)
        with self.assertRaises(M.MigrationError) as e:
            M.rollback(self.server, {'schema_version': 999}, True)
        self.assertEqual(e.exception.status, 400)

    def test_rollback_after_destination_revoke_still_restores_source(self):
        receipt = M.apply(self.server, self.propose_volumes()['proposal'], True)
        self.server.relays.revoke('r-tv')
        res = M.rollback(self.server, receipt, True)
        self.assertTrue(any('gone' in n for n in res['notes']))
        self.assertEqual(self.labels('r-watch'), ['TV volume +', 'TV volume -', 'YouTube'])


class HttpApi(Base):
    def test_propose_apply_rollback_over_api(self):
        status, out = post(self.server, '/api/v2/migrate/propose', {'text': TEXT})
        self.assertEqual(status, 200)
        self.assertEqual(out['outcome'], 'proposal')
        status, out = post(self.server, '/api/v2/migrate/propose', {'text': 'hello?'})
        self.assertEqual((status, out['outcome']), (200, 'needs_clarification'))
        status, receipt = post(self.server, '/api/v2/migrate/apply',
                               {'proposal': post(self.server, '/api/v2/migrate/propose', {'text': TEXT})[1]['proposal'],
                                'consent': True})
        self.assertEqual(status, 200)
        self.assertIn('migration_id', receipt)
        self.assertEqual(self.labels('r-tv'), ['Chrome', 'TV volume +', 'TV volume -'])
        status, res = post(self.server, '/api/v2/migrate/rollback', {'receipt': receipt, 'consent': True})
        self.assertEqual(status, 200)
        self.assertTrue(res['rolled_back'])

    def test_api_rejects_bad_calls(self):
        self.assertEqual(post(self.server, '/api/v2/migrate/nope', {})[0], 404)
        status, body = post(self.server, '/api/v2/migrate/apply', {'proposal': {}})
        self.assertEqual(status, 400)
        self.assertIn('error', body)


if __name__ == '__main__':
    unittest.main()
