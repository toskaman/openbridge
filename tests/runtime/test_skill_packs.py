"""Skill packs: ready-made cross-brand features, installed onto the owner's devices by role, never pre-approved."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.runtime import skill_library as SL
from src.runtime import skill_packs as P


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, primitive, device, params, consent=False):
        self.calls.append((primitive, device, dict(params)))
        return {'state': 'VERIFIED', 'verified': True, 'transaction_id': 'tx-%d' % len(self.calls), 'errors': []}


HOME = {'dev-tv': {'category': 'media_player', 'label': 'Living room TV'},
        'dev-light': {'category': 'light', 'label': 'Ceiling'},
        'dev-plug': {'category': 'plug', 'label': 'Lamp plug'},
        'dev-ha-robot': {'category': 'robot', 'label': 'Roborock (HA)'},
        'dev-tuya-robot': {'category': 'vacuum', 'label': 'Tuya robot'},
        'dev-lock': {'category': 'lock', 'label': 'Front door'}}


class ShippedPacks(unittest.TestCase):
    def test_every_shipped_pack_is_valid_and_pinned(self):
        packs = P.available()
        self.assertEqual({p['id'] for p in packs}, {'cinema', 'leaving-home', 'quiet-cleaning', 'good-morning', 'good-night',
                                                     'energy-saver'})
        self.assertEqual(json.loads((P.PACK_DIR / 'INDEX.json').read_text(encoding='utf-8')), P.build_index(),
                         'INDEX.json is stale: review the pack, then regenerate it with build_index()')

    def test_every_pack_has_french_and_english(self):
        for p in P.available():
            for field in (p['title'], p['description']):
                self.assertTrue(field.get('en') and field.get('fr'), p['id'])
            for s in p['skills']:
                self.assertTrue(s['name'].get('fr') and s['name'].get('en'), (p['id'], s['name']))

    def test_irreversible_steps_come_last(self):
        # A run stops at the first unverified step, and momentary commands cannot be undone: keep them last.
        momentary = {('ha_command', a) for a in ('start', 'pause', 'return_to_base', 'open', 'close', 'lock', 'play')}
        for p in P.available():
            for s in p['skills']:
                kinds = [any((how['primitive'], how['params'].get('action')) in momentary or how['primitive'] == 'tuya_command'
                             for how in st['by_category'].values()) for st in s['steps']]
                if True in kinds:
                    self.assertTrue(all(kinds[kinds.index(True):]), (p['id'], s['name']['en']))

    def test_a_changed_pack_file_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for f in P.PACK_DIR.glob('*.json'):
                shutil.copy(f, d)
            path = Path(d) / 'cinema.json'
            doc = json.loads(path.read_text(encoding='utf-8'))
            doc['skills'][0]['steps'][0]['by_category']['light']['params']['value'] = 100
            path.write_text(json.dumps(doc), encoding='utf-8')
            self.assertNotIn('cinema', {p['id'] for p in P.available(d)})
            with self.assertRaises(P.PackError):
                P.get('cinema', d)


class Install(unittest.TestCase):
    def setUp(self):
        self.ex = FakeExecutor()
        self.lib = SL.Library(self.ex, persist=False)

    def test_install_maps_roles_and_needs_approval(self):
        pack = P.get('quiet-cleaning')
        ids = P.install(self.lib, pack, HOME, {'media': 'dev-tv', 'robot': 'dev-tuya-robot'}, lang='fr')
        self.assertEqual(len(ids), 2)
        r = self.lib.recipes[ids[0]]
        self.assertEqual(r['origin']['kind'], 'pack')
        self.assertEqual(r['origin']['pack']['id'], 'quiet-cleaning')
        self.assertEqual(r['name'], 'Pause du robot pendant la lecture')
        self.assertEqual(r['trigger'], {'kind': 'state', 'device': 'dev-tv', 'state': 'playing'})
        self.assertEqual(r['steps'], [{'device': 'dev-tuya-robot', 'primitive': 'tuya_command', 'params': {'command': 'pause'}}])
        self.assertEqual(self.lib.run(ids[0])['result'], 'blocked')        # installed, never approved
        self.assertEqual(self.ex.calls, [])
        self.lib.approve(ids[0])
        self.assertEqual(self.lib.run(ids[0])['result'], 'done')

    def test_install_energy_saver(self):
        pack = P.get('energy-saver')
        ids = P.install(self.lib, pack, HOME, {'light': 'dev-light', 'plug': 'dev-plug'}, lang='fr')
        self.assertEqual(len(ids), 3)
        names = [self.lib.recipes[i]['name'] for i in ids]
        self.assertEqual(names, ['Soirée éco', 'Chasse aux veilles', 'Rallumer normal'])
        eco = self.lib.recipes[ids[0]]
        self.assertEqual(eco['steps'], [{'device': 'dev-light', 'primitive': 'ha_set',
                                         'params': {'action': 'set_brightness', 'value': 30}},
                                        {'device': 'dev-plug', 'primitive': 'ha_set',
                                         'params': {'action': 'turn_off'}}])
        sched = self.lib.recipes[ids[1]]
        self.assertEqual(sched['trigger'], {'kind': 'time', 'at': '01:00', 'days': [0, 1, 2, 3, 4, 5, 6]})

    def test_same_pack_resolves_per_brand(self):
        pack = P.get('leaving-home')
        tuya = P.resolve(pack, HOME, {'light': 'dev-plug', 'media': 'dev-tv', 'robot': 'dev-tuya-robot'})
        ha = P.resolve(pack, HOME, {'light': 'dev-light', 'media': 'dev-tv', 'robot': 'dev-ha-robot'})
        self.assertEqual(tuya[0]['steps'][2], {'device': 'dev-tuya-robot', 'primitive': 'tuya_command', 'params': {'command': 'start'}})
        self.assertEqual(ha[0]['steps'][2], {'device': 'dev-ha-robot', 'primitive': 'ha_command', 'params': {'action': 'start'}})
        self.assertEqual(tuya[0]['steps'][0]['params'], {'action': 'turn_off'})

    def test_auto_map_only_when_unambiguous(self):
        pack = P.get('quiet-cleaning')
        mapping, missing, ambiguous = P.auto_map(pack, HOME)
        self.assertEqual(mapping, {'media': 'dev-tv'})
        self.assertEqual(missing, [])
        self.assertEqual(ambiguous, {'robot': ['dev-ha-robot', 'dev-tuya-robot']})
        mapping, missing, _ = P.auto_map(P.get('good-morning'), HOME)
        self.assertIn('thermostat', missing)

    def test_wrong_device_for_a_role_is_refused(self):
        with self.assertRaises(P.PackError):
            P.install(self.lib, P.get('quiet-cleaning'), HOME, {'media': 'dev-light', 'robot': 'dev-ha-robot'})
        with self.assertRaises(P.PackError):
            P.install(self.lib, P.get('quiet-cleaning'), HOME, {'media': 'dev-tv'})
        self.assertEqual(self.lib.recipes, {})

    def test_pack_cannot_smuggle_a_forbidden_primitive(self):
        pack = json.loads(json.dumps(P.get('quiet-cleaning')))
        pack['skills'][1]['steps'][0]['by_category']['robot'] = {'primitive': 'pc_job', 'params': {'cmd': 'calc'}}
        with self.assertRaises(P.PackError):
            P.validate(pack)

    def test_partner_pack_check(self):
        pack = json.loads(json.dumps(P.get('cinema')))
        pack['id'] = 'acme-cinema'
        pack['publisher'] = {'name': 'Acme Lighting', 'kind': 'partner', 'url': 'https://example.com'}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'acme-cinema.json'
            path.write_text(json.dumps(pack), encoding='utf-8')
            info = P.check_file(path)
        self.assertEqual(info['id'], 'acme-cinema')
        self.assertEqual(len(info['sha256']), 64)


class Cli(unittest.TestCase):
    def run_cli(self, argv):
        import io
        import os
        from contextlib import redirect_stderr, redirect_stdout
        from unittest import mock
        from src import cli
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'LOCALAPPDATA': d}), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(['--json'] + argv)
        return code, json.loads(out.getvalue() or 'null')

    def test_packs_and_check(self):
        code, doc = self.run_cli(['skills', 'packs', '--lang', 'fr'])
        self.assertEqual(code, 0)
        self.assertIn('Ménage discret', [p['title'] for p in doc['data']['packs']])
        code, doc = self.run_cli(['skills', 'pack-check', str(P.PACK_DIR / 'good-night.json')])
        self.assertEqual(code, 0)
        self.assertEqual(doc['data']['pack']['id'], 'good-night')

    def test_approve_needs_consent(self):
        code, doc = self.run_cli(['skills', 'approve', 'skill-00000000'])
        self.assertNotEqual(code, 0)
        self.assertEqual(doc['error']['code'], 'CONSENT_REQUIRED')


if __name__ == '__main__':
    unittest.main()
