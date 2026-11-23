"""Partner voice profiles: product names repaired offline for matching only, and partner training lines."""
import json
import sys
import unittest
from pathlib import Path

from src.ai import partner_voice as PV
from src.ai import voice_normalize as VN

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'docs' / 'partners' / 'examples' / 'voice-profile.acme.json'


def profile():
    return json.loads(EXAMPLE.read_text(encoding='utf-8'))


class Profile(unittest.TestCase):
    def test_example_is_valid(self):
        PV.validate(profile())

    def test_everyday_words_cannot_be_misheard_variants(self):
        p = profile()
        p['products'][0]['misheard']['fr'].append('la')
        with self.assertRaises(PV.ProfileError):
            PV.validate(p)
        p = profile()
        p['products'][0]['misheard']['en'].append('acme')      # part of the name: would give "acme x5 x5"
        with self.assertRaises(PV.ProfileError):
            PV.validate(p)

    def test_coverage_says_what_a_new_language_needs(self):
        cov = PV.coverage(profile())
        self.assertTrue(cov['fr']['ready'])
        self.assertTrue(cov['en-GB']['ready'])
        self.assertFalse(cov['de']['ready'])
        self.assertTrue(any('speech-to-text' in n for n in cov['de']['needs']))


class Repair(unittest.TestCase):
    def test_misheard_name_is_repaired_and_reported(self):
        vocab = PV.repairs(profile())
        n = VN.normalize('Lance acmé x cinq', 'fr', vocab=vocab)
        self.assertEqual(n['fixed'], 'lance acme x5')
        self.assertTrue(any('acme-example' in r for r in n['repairs']))
        self.assertEqual(n['folded'], 'lance acme x cinq')          # the original is kept

    def test_repairs_are_per_language(self):
        vocab = PV.repairs(profile())
        n = VN.normalize('turn on the acne glow', 'en', vocab=vocab)
        self.assertIn('acme glow', n['fixed'])
        n = VN.normalize('acne glow', 'fr', vocab=[r for r in vocab if r[0] == 'en'])
        self.assertEqual(n['fixed'], 'acne glow')

    def test_no_profile_changes_nothing(self):
        self.assertEqual(VN.normalize('Lance acmé x cinq', 'fr', vocab=())['fixed'], 'lance acme x cinq')


class Dataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'dev' / 'ai_training'))
        import make_partner_dataset as M
        cls.sets = M.build(profile(), base_train=[{'text': 'old line', 'lang': 'en'}], replay=1)

    def test_partner_lines_name_partner_products(self):
        train = [r for r in self.sets['train'] if r.get('partner') == 'acme-example']
        self.assertGreater(len(train), 50)
        refs = {t['ref'] for r in train for t in r['reply']['targets'] if t.get('kind') == 'device'}
        self.assertTrue(any(ref.endswith('acme glow') for ref in refs))      # "acme glow" or "kitchen acme glow"
        self.assertTrue(any('X5' in r['text'] for r in train))
        self.assertTrue(any(r['text'].startswith(('Envoie', 'Send')) for r in train + self.sets['test']))

    def test_test_lines_never_in_train(self):
        train = {r['text'].lower() for r in self.sets['train']}
        self.assertFalse(train & {r['text'].lower() for r in self.sets['partner_test']})

    def test_replay_and_only_known_dialects(self):
        self.assertIn('old line', [r['text'] for r in self.sets['train']])
        self.assertTrue({r['dialect'] for r in self.sets['train'] if r.get('partner')} <= {'fr', 'en', 'en-US', 'en-GB'})


if __name__ == '__main__':
    unittest.main()
