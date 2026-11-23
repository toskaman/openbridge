"""`openbridge partner new` generates an integration whose own tests pass on day one."""
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

from src import partner_kit as kit


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PartnerKitTests(unittest.TestCase):
    def test_generated_integration_passes_its_own_tests(self):
        with tempfile.TemporaryDirectory() as d:
            out = kit.generate('Acme Lamp', title='Acme Lamp', category='lamp', root=d)
            self.assertEqual(out['device'], 'acme_lamp')
            self.assertEqual(len(out['files']), 5)
            root = Path(d)
            names = []
            try:
                for name, rel in (('src.adapters.acme_lamp', 'src/adapters/acme_lamp.py'),
                                  ('src.adapters.acme_lamp_emulator', 'src/adapters/acme_lamp_emulator.py'),
                                  ('src.fabric.acme_lamp_ingest', 'src/fabric/acme_lamp_ingest.py')):
                    _load(name, root / rel)
                    names.append(name)
                tests = _load('generated_acme_lamp_tests', root / 'tests/partners/test_acme_lamp.py')
                names.append('generated_acme_lamp_tests')
                suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
                result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
            finally:
                for name in names:
                    sys.modules.pop(name, None)
            self.assertEqual(result.testsRun, 6)
            self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
            self.assertIn('emulator only', (root / 'docs/partners/acme_lamp/README.md').read_text(encoding='utf-8'))

    def test_never_overwrites_and_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            dry = kit.generate('acme_plug', root=d, dry_run=True)
            self.assertFalse(dry['written'])
            self.assertFalse(any(Path(d).rglob('*.py')))
            kit.generate('acme_plug', root=d)
            with self.assertRaises(kit.KitError):
                kit.generate('acme_plug', root=d)

    def test_generated_files_carry_the_apache_licence(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = kit.generate('Acme Lamp', root=d)
            for rel in out['files']:
                text = (Path(d) / rel).read_text(encoding='utf-8')
                if rel.endswith('.py'):
                    self.assertTrue(text.startswith('# SPDX-License-Identifier: Apache-2.0'), rel)
                    self.assertIn('PolyForm Strict', text)      # the imported core is not Apache
                else:
                    self.assertIn('Apache License 2.0', text)
        self.assertTrue((Path(kit.ROOT) / 'LICENSES' / 'Apache-2.0.txt').exists())
        self.assertTrue(Path(kit.__file__).read_text(encoding='utf-8').startswith('# SPDX-License-Identifier: Apache-2.0'))

    def test_names_are_checked(self):
        for bad in ('', '1lamp', 'tuya_local', 'home assistant', 'x'):
            with self.subTest(bad=bad), self.assertRaises(kit.KitError):
                kit.slugify(bad)
        self.assertEqual(kit.slugify('ENGO Glasses 3'), 'engo_glasses_3')


if __name__ == '__main__':
    unittest.main()
