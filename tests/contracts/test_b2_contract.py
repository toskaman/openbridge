"""B2 rev 2 contract tests. The fixtures in tests/contracts/b2/ are shared with the UI (Codex Skill Graph tests)."""
import copy
import json
import threading
import unittest
from pathlib import Path

from src.runtime import route_contract as rc

FIX = Path(__file__).with_name('b2')


def load(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


class Fixtures(unittest.TestCase):
    def test_valid_fixtures_pass_schema_and_rules(self):
        names = sorted(p.name for p in FIX.glob('skill_routes_*.json'))
        self.assertGreaterEqual(len(names), 5)
        for n in names:
            self.assertEqual(rc.validate_doc(load(n)), [], n)
        self.assertEqual(rc.schema_errors(load('invoke_request.json'), rc.SCHEMA['$defs']['invoke_request']), [])

    def test_every_invalid_fixture_fails_for_the_stated_reason(self):
        manifest = load('invalid/manifest.json')
        self.assertEqual(set(manifest), {p.name for p in (FIX / 'invalid').glob('*.json')} - {'manifest.json'})
        for name, expect in manifest.items():
            errs = rc.validate_doc(load('invalid/' + name))
            self.assertTrue(any(expect in e for e in errs), (name, errs))

    def test_states_and_reasons_are_closed_enums(self):
        route = rc.SCHEMA['$defs']['route']['properties']
        self.assertEqual(route['state']['enum'], ['READY', 'STANDBY', 'UNAVAILABLE'])   # selection/consent are separate fields
        self.assertEqual(set(rc.SCHEMA['$defs']['reason']['enum']), {'link_down', 'grant_insufficient', 'consent_missing', 'capability_absent',
                                                                     'lease_stale', 'dependency_unready', 'policy_blocked', 'backend_unknown'})

    def test_exact_volume_never_lists_key_presses(self):
        vol = load('skill_routes_tv_volume_exact.json')
        self.assertTrue(all('key' not in r['operation_id'] for r in vol['routes']))
        step = load('skill_routes_tv_volume_step.json')
        self.assertEqual(step['skill']['reversibility'], 'IRREVERSIBLE')

    def test_unknown_top_level_field_and_type_errors(self):
        d = load('skill_routes_empty.json'); d['extra'] = 1
        self.assertTrue(any('unexpected field' in e for e in rc.validate_doc(d)))
        d = load('skill_routes_empty.json'); d['graph_revision']['seq'] = True
        self.assertTrue(rc.validate_doc(d))


class StableIds(unittest.TestCase):
    hops = [{'device_key': 'dev-tv', 'transport': 'RELAY', 'primitive_id': 'relay_ble_scan'}]

    def test_ids_are_stable_and_path_sensitive(self):
        a = rc.route_id('ble_scan_room', self.hops, 'op:relay_ble_scan')
        self.assertEqual(a, rc.route_id('ble_scan_room', copy.deepcopy(self.hops), 'op:relay_ble_scan'))
        other = [dict(self.hops[0], device_key='dev-phone')]
        self.assertNotEqual(a, rc.route_id('ble_scan_room', other, 'op:relay_ble_scan'))
        self.assertRegex(a, r'^rt-[0-9a-f]{16}$')
        self.assertRegex(rc.provider_id('dev-tv', 'RELAY', 'relay_ble_scan', 'op:relay_ble_scan'), r'^pv-[0-9a-f]{16}$')

    def test_binding_changes_with_authority_target_graph_lease_and_params(self):
        req = load('invoke_request.json')
        base = rc.binding_hash('owner', req, 'android_serial:abc', 3)
        variants = [rc.binding_hash('owner', req, 'android_serial:abc', 4),          # grant changed
                    rc.binding_hash('owner', req, 'android_serial:xyz', 3),          # different physical target
                    rc.binding_hash('other', req, 'android_serial:abc', 3)]          # different actor
        for k, v in (('params', {'seconds': 9}), ('lease_id', 'ls-0000000000000000'), ('graph_revision', {'epoch': 'boot-7f3a', 'seq': 43})):
            r2 = dict(req, **{k: v}); variants.append(rc.binding_hash('owner', r2, 'android_serial:abc', 3))
        self.assertEqual(len({base, *variants}), len(variants) + 1)


class Dedup(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.ledger = rc.InvocationLedger()

    def dispatch(self, label='press'):
        self.calls.append(label)
        return {'state': 'EXECUTED', 'n': len(self.calls)}

    def test_retry_with_same_id_dispatches_once(self):
        a = self.ledger.run('owner', 'inv-1', 'b1', self.dispatch)
        b = self.ledger.run('owner', 'inv-1', 'b1', self.dispatch)
        self.assertEqual(a, b); self.assertEqual(len(self.calls), 1)

    def test_two_deliberate_identical_presses_both_run(self):
        self.ledger.run('owner', 'inv-1', 'same-params', self.dispatch)
        self.ledger.run('owner', 'inv-2', 'same-params', self.dispatch)
        self.assertEqual(len(self.calls), 2)          # identical params are NOT coalesced

    def test_reused_id_with_changed_payload_is_rejected_without_dispatch(self):
        self.ledger.run('owner', 'inv-1', 'b1', self.dispatch)
        with self.assertRaises(rc.InvocationIdReused):
            self.ledger.run('owner', 'inv-1', 'b2', self.dispatch)
        self.assertEqual(len(self.calls), 1)

    def test_ids_are_scoped_per_actor(self):
        self.ledger.run('owner', 'inv-1', 'b1', self.dispatch)
        self.ledger.run('watch', 'inv-1', 'b1', self.dispatch)
        self.assertEqual(len(self.calls), 2)

    def test_concurrent_retries_share_one_dispatch(self):
        gate = threading.Event()
        def slow():
            gate.wait(5); return self.dispatch()
        out = []
        ths = [threading.Thread(target=lambda: out.append(self.ledger.run('owner', 'inv-9', 'b', slow))) for _ in range(8)]
        for t in ths: t.start()
        gate.set()
        for t in ths: t.join(5)
        self.assertEqual(len(self.calls), 1); self.assertEqual(len(out), 8); self.assertTrue(all(o == out[0] for o in out))

    def test_failure_is_an_outcome_and_is_not_redispatched(self):
        def boom():
            self.calls.append('x'); raise OSError('link lost')
        a = self.ledger.run('owner', 'inv-1', 'b', boom)
        b = self.ledger.run('owner', 'inv-1', 'b', boom)
        self.assertEqual(a['state'], 'FAILED'); self.assertEqual(a, b); self.assertEqual(self.calls, ['x'])

    def test_expiry_and_full_ledger(self):
        now = [0.0]
        led = rc.InvocationLedger(ttl_s=10, max_entries=2, clock=lambda: now[0])
        led.run('owner', 'a', 'b', self.dispatch); led.run('owner', 'b', 'b', self.dispatch)
        with self.assertRaises(RuntimeError):         # refuses rather than forgetting a live id
            led.run('owner', 'c', 'b', self.dispatch)
        now[0] = 11
        led.run('owner', 'c', 'b', self.dispatch)
        self.assertEqual(len(self.calls), 3)


if __name__ == '__main__':
    unittest.main()
