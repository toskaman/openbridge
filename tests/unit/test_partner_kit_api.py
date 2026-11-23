"""Bring your device, leave with an integration: an OpenAPI description becomes an adapter whose tests pass,
and the browser page (site/js/integrate-core.js) writes exactly the same files as the command line."""
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src import partner_kit as kit
from src import partner_kit_api as api

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'docs' / 'partners' / 'examples' / 'openapi.acme-glow.json'


def example():
    return json.loads(EXAMPLE.read_text(encoding='utf-8'))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ApiSpec(unittest.TestCase):
    def test_rules(self):
        s = api.api_spec(example())
        self.assertEqual(s['read']['path'], '/state')
        self.assertEqual(sorted(s['writable']), ['brightness_percent', 'color_temp', 'effect', 'power'])
        self.assertEqual(s['writable']['color_temp']['values'], {'min': 2200, 'max': 6500})
        self.assertEqual(s['read']['fields']['color_temp']['unit'], 'K')
        self.assertEqual(sorted(s['commands']), ['identify', 'scene'])
        self.assertEqual(sorted(s['policy']), ['firmware_version', 'update'])     # OTA and firmware: always refused
        self.assertNotIn('label', s['writable'])                                  # unbounded string: no allowlist
        self.assertTrue(any('label' in x for x in s['skipped']))
        self.assertTrue(any('{id}' in x for x in s['skipped']))

    def test_refuses_what_it_cannot_read(self):
        for doc in ({}, {'swagger': '2.0', 'paths': {}}, {'openapi': '3.0.0', 'paths': {}},
                    {'openapi': '3.0.0', 'paths': {'/x': {'post': {}}}}):
            with self.assertRaises(api.SpecError):
                api.api_spec(doc)
        with self.assertRaises(api.SpecError):
            api.api_spec({'openapi': '3.0.0', 'paths': {'/s': {'get': {'responses': {'200': {'content': {
                'application/json': {'schema': {'$ref': 'http://evil.example/schema.json'}}}}}}}}})

    def test_pylit(self):
        self.assertEqual(api.pylit({'a': (True, None, 1.0, 'it\'s')}), "{'a': (True, None, 1, 'it\\'s')}")
        self.assertEqual(api.pylit(['x']), "('x',)")
        self.assertEqual(api.pylit({'min': 0, 'max': 9}), 'range(0, 10)')


class GeneratedFromApi(unittest.TestCase):
    def test_generated_integration_passes_its_own_tests(self):
        with tempfile.TemporaryDirectory() as d:
            out = kit.generate('Acme Glow', category='lamp', root=d, spec=api.api_spec(example()))
            root, names = Path(d), []
            try:
                for name, rel in (('src.adapters.acme_glow', 'src/adapters/acme_glow.py'),
                                  ('src.adapters.acme_glow_emulator', 'src/adapters/acme_glow_emulator.py'),
                                  ('src.fabric.acme_glow_ingest', 'src/fabric/acme_glow_ingest.py')):
                    _load(name, root / rel)
                    names.append(name)
                tests = _load('generated_acme_glow_tests', root / 'tests/partners/test_acme_glow.py')
                names.append('generated_acme_glow_tests')
                result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
                    unittest.defaultTestLoader.loadTestsFromModule(tests))
                adapter = sys.modules['src.adapters.acme_glow']
                with self.assertRaises(adapter.AcmeGlowBlocked):       # an OTA can never be triggered
                    adapter.AcmeGlow(sys.modules['src.adapters.acme_glow_emulator'].AcmeGlowEmulator()).command('update')
            finally:
                for name in names:
                    sys.modules.pop(name, None)
            self.assertEqual(result.testsRun, 7)
            self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
            readme = (root / 'docs/partners/acme_glow/README.md').read_text(encoding='utf-8')
            self.assertIn('`PATCH /state`', readme)
            self.assertIn('no enum or minimum/maximum', readme)
            self.assertIn('Apache', (root / out['files'][0]).read_text(encoding='utf-8'))

    def test_cli(self):
        from contextlib import redirect_stderr, redirect_stdout
        from unittest import mock
        from src import cli
        with tempfile.TemporaryDirectory() as d, mock.patch.object(kit, 'ROOT', Path(d)):
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = cli.main(['--json', 'partner', 'new', 'Acme Glow', '--from-openapi', str(EXAMPLE), '--dry-run'])
            self.assertEqual(code, 0)
            data = json.loads(buf.getvalue())['data']
            self.assertEqual(data['mapped']['refused'], ['firmware_version', 'update'])
            self.assertFalse(any(Path(d).rglob('*.py')))


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class BrowserParity(unittest.TestCase):
    """The page must write byte-for-byte the files the command line writes."""

    TRICKY = {'openapi': '3.1.0', 'info': {'title': 'Fan "Pro" ventilateur'}, 'paths': {
        '/v2/readings': {'get': {'responses': {'200': {'content': {'application/json': {'schema': {'type': 'object', 'properties': {
            'speedLevel': {'type': 'number', 'minimum': 0.0, 'maximum': 5.0, 'example': 2.0},
            'oscillate': {'type': 'boolean', 'default': True}, 'adminPasscode': {'type': 'string'},
            'tempC': {'type': 'number', 'example': 21.5, 'x-unit': '°C'}}}}}}}}},
        '/v2/oscillate': {'put': {'requestBody': {'content': {'application/json': {'schema': {'type': 'object', 'properties': {
            'oscillate': {'type': 'boolean'}}}}}}}},
        '/v2/speed': {'post': {'requestBody': {'content': {'application/json': {'schema': {'type': 'object', 'properties': {
            'speedLevel': {'type': 'integer', 'minimum': 0, 'maximum': 5}, 'boost': {'enum': ['on', 'off']}}}}}}}},
        '/v2/beep/': {'post': {}}, '/v2/reboot': {'post': {}}, '/v2/note': {'patch': {}}}}

    def run_node(self, doc, name, category):
        sys.path.insert(0, str(ROOT / 'scripts' / 'site'))
        import build_site
        job = {'kit': build_site.integrate_kit(), 'openapi': doc, 'name': name, 'category': category}
        with tempfile.TemporaryDirectory() as d:      # a local copy: node cannot start a script from a network share
            script = Path(d) / 'integrate-core.js'
            shutil.copy2(ROOT / 'site' / 'js' / 'integrate-core.js', script)
            (Path(d) / 'job.json').write_text(json.dumps(job), encoding='utf-8')
            r = subprocess.run(['node', str(script), '--job', str(Path(d) / 'job.json')], cwd=d, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_same_files(self):
        for doc, name, category in ((example(), 'Acme Glow', 'lamp'), (self.TRICKY, 'Zeta Fan 3', 'fan')):
            with self.subTest(name=name):
                js = self.run_node(doc, name, category)
                spec = api.api_spec(doc)
                _, files = kit.plan(name, None, category, root='/', spec=spec)
                files = {str(p.relative_to(Path('/'))).replace('\\', '/'):
                         (kit.PY_HEADER + t) if p.suffix == '.py' else (t + kit.MD_FOOTER) for p, t in files.items()}
                self.assertEqual(js['spec'], json.loads(json.dumps(spec)))
                self.assertEqual(sorted(js['files']), sorted(files))
                for path, text in files.items():
                    self.assertEqual(js['files'][path], text, path)

    def test_tricky_description_still_gives_passing_code(self):
        spec = api.api_spec(self.TRICKY)
        self.assertEqual(sorted(spec['policy']), ['admin_passcode', 'reboot'])
        self.assertNotIn('admin_passcode', spec['read']['fields'])              # a secret is not even read
        self.assertIn('speed_level', spec['writable'])
        self.assertEqual(sorted(spec['commands']), ['beep'])
        self.assertTrue(any('boost' in x for x in spec['skipped']))          # an enum with no type is not trusted

if __name__ == '__main__':
    unittest.main()
