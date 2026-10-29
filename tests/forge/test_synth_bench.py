"""S1 bench scoring (pure, offline): valid/invalid taxonomy, no models."""
import unittest

from dev.synth_bench import build_bundle, score, CASES


def bundle():
    return build_bundle(CASES[0])


class Score(unittest.TestCase):
    def test_failed_synth_scores_invalid_with_reason(self):
        rec = score(CASES[0], bundle(), False, {'status': 'SCHEMA_REJECTED', 'reason': 'not JSON'})
        self.assertFalse(rec['valid'])
        self.assertEqual(rec['reason'][0], 'SCHEMA_REJECTED')
        self.assertEqual(rec['baseline'], 'ABSTAIN_UNSUPPORTED')

    def test_invented_evidence_scores_zero_precision(self):
        b = bundle()
        cand = {'evidence_refs': ['opaque:device:nope'], 'required_grants': ['observe'],
                'primitive_chain': [{'primitive_id': 'read_facts', 'input': {}}]}
        rec = score(CASES[0], b, True, {'candidate': cand})
        self.assertFalse(rec['valid'])
        self.assertEqual(rec['evidence_precision'], 0.0)

    def test_exact_case_scores_valid(self):
        b = bundle()
        refs = [f['evidence_ref'] for d in b['devices'] for f in d['facts']]
        cand = {'evidence_refs': refs, 'required_grants': ['observe'],
                'primitive_chain': [{'primitive_id': 'read_facts', 'input': {}}]}
        rec = score(CASES[0], b, True, {'candidate': cand})
        self.assertTrue(rec['valid'])
        self.assertTrue(rec['grants_ok'])

    def test_out_of_scope_grant_rejected(self):
        b = bundle()
        refs = [f['evidence_ref'] for d in b['devices'] for f in d['facts']]
        cand = {'evidence_refs': refs, 'required_grants': ['control'],
                'primitive_chain': [{'primitive_id': 'read_facts', 'input': {}}]}
        rec = score(CASES[0], b, True, {'candidate': cand})
        self.assertFalse(rec['valid'])
        self.assertFalse(rec['grants_ok'])


if __name__ == '__main__':
    unittest.main()
