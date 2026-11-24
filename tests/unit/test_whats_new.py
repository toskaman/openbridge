"""The README "What's new" log must exist, sit before the demo, and carry dated, timed entries (newest first)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY = re.compile(r'^- `(\d{4}-\d{2}-\d{2} \d{2}:\d{2})` \S', re.M)


class WhatsNew(unittest.TestCase):
    def check(self, name, demo_heading):
        text = (ROOT / name).read_text(encoding='utf8')
        self.assertIn('<!-- whatsnew:start', text, name)
        self.assertIn('<!-- whatsnew:end -->', text, name)
        block = text.split('<!-- whatsnew:start', 1)[1].split('<!-- whatsnew:end -->', 1)[0]
        self.assertLess(text.index('<!-- whatsnew:start'), text.index(demo_heading), name)
        stamps = ENTRY.findall(block)
        self.assertTrue(stamps, name + ': no dated entries')
        self.assertEqual(stamps, sorted(stamps, reverse=True), name + ': entries must be newest first')
        self.assertIn('<details>', block, name + ': older updates must be in a collapsible block')

    def test_english(self):
        self.check('README.md', '## See it in action')

    def test_french(self):
        self.check('README.fr.md', '## En action')

    def test_same_entries_in_both_languages(self):
        get = lambda n: ENTRY.findall((ROOT / n).read_text(encoding='utf8').split('<!-- whatsnew:start', 1)[1].split('<!-- whatsnew:end -->', 1)[0])
        self.assertEqual(get('README.md'), get('README.fr.md'))


if __name__ == '__main__':
    unittest.main()
