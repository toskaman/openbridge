"""Campaign Two §4.9: portable dashboard bundles (export/verify/import).

SIMULATED_VERIFIED: synthetic registry/relays + FakeCompanion (mirrors
RelayServer.java); no devices, no network, no model calls.
"""
import copy
import unittest

from src.fabric import relay as R
from src.runtime import dashboard_port as P
from src.runtime import dashboards as D
from src.runtime.api_v2 import remote_controls
from src.runtime.state_store import StateStore
from tests.runtime.test_remote_controls import FakeCompanion, KEY
from tests.runtime.test_routing import Clock, world

CTRLS = [
    {'label': 'Volume +', 'skill_id': 'tv_volume_step', 'target': 'hint-tv',
     'params': {'direction': 'up'}},
    {'label': 'Volume -', 'skill_id': 'tv_volume_step', 'target': 'hint-tv',
     'params': {'direction': 'down'}},
    {'label': 'Find robots', 'skill_id': 'ble_scan_room', 'params': {'seconds': 5}},
]


def fresh_bundle(controls=None):
    return P.export_bundle(name='panel-x', controls=copy.deepcopy(controls or CTRLS))


class Port(unittest.TestCase):
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

    # -- export ------------------------------------------------------

    def test_export_from_live_controls_seals_hints(self):
        b = fresh_bundle()
        self.assertEqual(b['format'], 'openbridge-dashboard-bundle')
        self.assertEqual(b['version'], 1)
        self.assertEqual(b['controls'][0]['target_hint'], 'hint-tv')
        self.assertIsNone(b['controls'][2]['target_hint'])
        self.assertNotIn('target', b['controls'][0])
        self.assertEqual(P.verify_bundle(b), b['integrity']['digest'])

    def test_export_is_deterministic(self):
        self.assertEqual(fresh_bundle(), fresh_bundle())

    def test_export_from_saved_dashboard(self):
        D.create(self.rc, 'r-watch', 'tv', self.keys['tv'])
        self.store.save('r-watch', 'tv-evening', D.defs(self.rc, 'r-watch'))
        b = P.export_bundle(store=self.store, name='tv-evening')
        self.assertEqual([c['label'] for c in b['controls']],
                         ['Volume +', 'Volume -', 'YouTube'])
        self.assertEqual({c['target_hint'] for c in b['controls']}, {self.keys['tv']})

    def test_export_unknown_saved_name(self):
        with self.assertRaises(P.PortError):
            P.export_bundle(store=self.store, name='nope')

    def test_export_needs_exactly_one_source(self):
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x')
        with self.assertRaises(P.PortError):
            P.export_bundle(store=self.store, name='x', controls=[])

    def test_export_refuses_empty(self):
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x', controls=[])

    def test_export_refuses_oversize(self):
        big = [{'label': 'b%d' % i, 'skill_id': 'ble_scan_room', 'params': {}}
               for i in range(R.MAX_CONTROLS + 1)]
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x', controls=big)

    def test_export_refuses_unknown_skill_exec_skill_bad_params(self):
        bad_skill = copy.deepcopy(CTRLS)
        bad_skill[0]['skill_id'] = 'nope'
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x', controls=bad_skill)
        pc = copy.deepcopy(CTRLS)
        pc[0] = {'label': 'Run', 'skill_id': 'pc_run', 'target': 'h', 'params': {'command': 'x'}}
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x', controls=pc)
        nested = copy.deepcopy(CTRLS)
        nested[0]['params'] = {'direction': ['up']}
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x', controls=nested)
        nolabel = copy.deepcopy(CTRLS)
        nolabel[0]['label'] = ''
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x', controls=nolabel)
        notarget = copy.deepcopy(CTRLS)
        del notarget[0]['target']
        with self.assertRaises(P.PortError):
            P.export_bundle(name='x', controls=notarget)

    # -- verify ------------------------------------------------------

    def test_verify_tamper_rejected(self):
        for path in ('label', 'skill', 'params', 'name'):
            b = fresh_bundle()
            if path == 'label':
                b['controls'][0]['label'] += '!'
            elif path == 'skill':
                b['controls'][2]['skill_id'] = 'retro_command'
                b['controls'][2]['params'] = {'command': 'VERSION'}
            elif path == 'params':
                b['controls'][0]['params']['direction'] = 'down'
            else:
                b['name'] = 'other'
            with self.assertRaises(P.PortError, msg=path):
                P.verify_bundle(b)

    def test_verify_rejects_shape_defects(self):
        b = fresh_bundle()
        wrong_format = dict(b, format='other')
        with self.assertRaises(P.PortError):
            P.verify_bundle(wrong_format)
        wrong_version = copy.deepcopy(b)
        wrong_version['version'] = 99
        with self.assertRaises(P.PortError):
            P.verify_bundle(wrong_version)
        no_seal = copy.deepcopy(b)
        del no_seal['integrity']
        with self.assertRaises(P.PortError):
            P.verify_bundle(no_seal)
        extra_key = copy.deepcopy(b)
        extra_key['note'] = 'hi'
        with self.assertRaises(P.PortError):
            P.verify_bundle(extra_key)
        smuggled = copy.deepcopy(b)
        smuggled['controls'][0]['target'] = 'dev-live-key'
        with self.assertRaises(P.PortError):
            P.verify_bundle(smuggled)
        with self.assertRaises(P.PortError):
            P.verify_bundle('not-a-bundle')

    def test_verify_rejects_resigned_hostile_bundle(self):
        # An attacker who re-seals still cannot smuggle hostile content: every
        # control is re-checked against the live skill table after the seal.
        hostile = {'format': P.FORMAT, 'version': 1, 'name': 'hostile',
                   'controls': [{'label': 'Run', 'skill_id': 'pc_run',
                                 'target_hint': 'h', 'params': {'command': 'evil'}}]}
        hostile = dict(hostile, integrity={'algo': 'sha256', 'digest': P._digest(hostile)})
        with self.assertRaises(P.PortError):
            P.verify_bundle(hostile)

    def test_verify_rejects_hint_mismatch(self):
        b = P.export_bundle(name='m', controls=copy.deepcopy(CTRLS))
        b['controls'][2]['target_hint'] = 'hint-x'
        b = dict(b, integrity={'algo': 'sha256', 'digest': P._digest(
            {k: b[k] for k in ('format', 'version', 'name', 'controls')})})
        with self.assertRaises(P.PortError):
            P.verify_bundle(b)

    # -- plan / dry-run ----------------------------------------------

    def test_dry_run_resolves_and_installs_nothing(self):
        plan = P.dry_run(fresh_bundle(), target='live-key')
        self.assertEqual(plan['targets'], {'hint-tv': 'live-key'})
        self.assertEqual([c['target'] for c in plan['controls'][:2]],
                         ['live-key', 'live-key'])
        self.assertNotIn('target', plan['controls'][2])
        self.assertEqual(self.labels(), [])
        self.assertEqual(self.rc.grants, {})

    def test_dry_run_missing_remap_names_hints(self):
        with self.assertRaises(P.PortError) as ctx:
            P.dry_run(fresh_bundle())
        self.assertIn('hint-tv', str(ctx.exception))

    def test_plan_per_hint_map_and_resolver(self):
        ctrls = [dict(c, target='hint-%d' % i) for i, c in enumerate(copy.deepcopy(CTRLS[:2]))]
        b = P.export_bundle(name='two', controls=ctrls)
        plan = P.plan_import(b, target_map={'hint-0': 'label-a', 'hint-1': 'label-b'},
                             resolve_target=lambda t: 'live:' + t)
        self.assertEqual([c['target'] for c in plan['controls']],
                         ['live:label-a', 'live:label-b'])
        with self.assertRaises(P.PortError):
            P.plan_import(b, target_map={'hint-0': 'only-one'})

    # -- import ------------------------------------------------------

    def test_import_installs_fresh_grant_on_live_keys(self):
        receipt = P.import_bundle(self.rc, 'r-watch', fresh_bundle(),
                                  target=self.keys['tv'], consent=True)
        self.assertEqual(self.labels(), ['Volume +', 'Volume -', 'Find robots'])
        self.assertEqual(receipt['installed'], 3)
        live = {c['target'] for c in self.rc.grants['r-watch'].values() if c.get('target')}
        self.assertEqual(live, {self.keys['tv']})
        self.assertIsNone(receipt['saved_as'])

    def test_import_replaces_previous_grant(self):
        P.import_bundle(self.rc, 'r-watch', fresh_bundle(), target=self.keys['tv'], consent=True)
        gen1 = self.rc.generation
        P.import_bundle(self.rc, 'r-watch', fresh_bundle(), target=self.keys['tv'], consent=True)
        self.assertGreater(self.rc.generation, gen1)
        self.assertEqual(len(self.rc.grants['r-watch']), 3)

    def test_import_needs_consent(self):
        with self.assertRaises(P.PortError):
            P.import_bundle(self.rc, 'r-watch', fresh_bundle(), target='k', consent=False)
        self.assertEqual(self.labels(), [])

    def test_import_saves_named_dashboard(self):
        P.import_bundle(self.rc, 'r-watch', fresh_bundle(), target=self.keys['tv'],
                        consent=True, store=self.store, save_as='ported')
        self.assertIn('ported', self.store.list())
        rec = self.store.get('ported')
        self.assertEqual(rec['relay_id'], 'r-watch')
        self.assertEqual(len(rec['controls']), 3)

    def test_import_save_needs_both_args(self):
        with self.assertRaises(P.PortError):
            P.import_bundle(self.rc, 'r-watch', fresh_bundle(), target=self.keys['tv'],
                            consent=True, save_as='half')

    def test_import_schema_rechecked_by_set_controls(self):
        # A bundle whose params violate the live skill schema dies at install,
        # even though the bundle-level (scalar-only) check passed.
        ctrls = copy.deepcopy(CTRLS)
        ctrls[0]['params'] = {'direction': 'sideways'}
        b = P.export_bundle(name='bad-schema', controls=ctrls)
        from src.runtime.remote_controls import RemoteControlError
        with self.assertRaises(RemoteControlError):
            P.import_bundle(self.rc, 'r-watch', b, target=self.keys['tv'], consent=True)

    # -- cli wiring --------------------------------------------------

    def test_cli_parser_accepts_export_import(self):
        from src.cli import build_parser
        p = build_parser()
        a = p.parse_args(['dashboards', 'export', '--name', 'n', '--saved', 's'])
        self.assertEqual(a.name, 'n')
        a = p.parse_args(['dashboards', 'export', '--name', 'n', '--relay', 'r',
                          '--out', 'f.json'])
        self.assertEqual(a.out, 'f.json')
        a = p.parse_args(['dashboards', 'import', '--bundle', 'b.json', '--relay', 'r',
                          '--target', 't', '--save-as', 's', '--dry-run'])
        self.assertTrue(a.dry_run)
        self.assertEqual(a.target_map, None)


if __name__ == '__main__':
    unittest.main()
