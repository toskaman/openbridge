"""The project website builds from the repository alone, and every page is fully translated."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'site'))
import build_site  # noqa: E402

PAGES = ('index.html', 'try.html', 'compatibility.html', 'benchmarks.html')


class SiteBuildTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = build_site.build(Path(cls.tmp.name) / '_site')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_pages_and_assets_are_present(self):
        for name in PAGES + ('OpenBridge-Partner-Brief.pdf', 'social-preview.png', 'css/site.css', 'js/i18n.js',
                             'assets/readme/demo-poster.jpg', 'assets/hud_studio_overview.png', '.nojekyll'):
            self.assertTrue((self.out / name).is_file(), name)

    def test_compatibility_data_covers_the_whole_registry(self):
        registry = json.loads((ROOT / 'docs' / 'DEVICE_EVIDENCE.json').read_text(encoding='utf-8'))
        data = json.loads((self.out / 'data' / 'compatibility.json').read_text(encoding='utf-8'))
        self.assertEqual(data['verified_runs'], len(registry))
        runs = sum(len(d['runs']) for d in data['devices'])
        self.assertEqual(runs, len(registry))
        self.assertEqual({d['id'] for d in data['devices'] if d['runs']}, {r['public_device_id'] for r in registry})
        emulated = [d for d in data['devices'] if d['level'] == 'emulated']
        self.assertTrue(all(not d['runs'] for d in emulated), 'emulated devices must never carry verified runs')

    def test_benchmark_data_matches_the_committed_results(self):
        data = json.loads((self.out / 'data' / 'benchmarks.json').read_text(encoding='utf-8'))
        routes = {r['route']: r for r in data['agent_planning']['routes']}
        self.assertEqual(set(routes), {'rules', 'llama3b', 'glimmer'})
        for name, r in routes.items():
            raw = json.loads((ROOT / 'docs' / 'benchmark' / ('agent-benchmark-%s.json' % name)).read_text(encoding='utf-8'))
            self.assertEqual(r['correct_pct'], raw['decision_correct_pct'])
            self.assertEqual(r['unsafe_proposed'], raw['unsafe_proposals'])
        self.assertEqual(sum(data['evidence']['by_level'].values()), data['evidence']['verified_runs'])

    def test_every_page_string_has_a_french_translation(self):
        french = set(re.findall(r"'([a-z0-9]+(?:\.[a-z0-9]+)+)':", (ROOT / 'site' / 'js' / 'i18n.js').read_text(encoding='utf-8')))
        for page in PAGES:
            html = (ROOT / 'site' / page).read_text(encoding='utf-8')
            keys = set(re.findall(r'data-i18n="([^"]+)"', html))
            for attrs in re.findall(r'data-i18n-attr="([^"]+)"', html):
                keys |= {pair.split(':')[1].strip() for pair in attrs.split(';')}
            missing = sorted(keys - french)
            self.assertEqual(missing, [], '%s: untranslated keys %s' % (page, missing))


if __name__ == '__main__':
    unittest.main()
