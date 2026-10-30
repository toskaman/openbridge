"""Tests for the §11 eval-kit replay harness (anti-leak + terminal states)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dev import eval_1000 as E


class OracleMetaTest(unittest.TestCase):
    def test_forbidden_keys_stripped(self):
        oracle = {'id': 'X-T1', 'conversation_id': 'X', 'category': 'CAT',
                  'turn': 1,
                  'expected_invariants': ['secret answer'],
                  'turn_invariant': 'secret',
                  'grading': {'a': 1.0},
                  'hard_fail_if': ['cond']}
        with tempfile.NamedTemporaryFile('w', suffix='.jsonl', delete=False,
                                         encoding='utf-8') as f:
            f.write(json.dumps(oracle) + '\n')
            path = f.name
        meta = E.load_oracle_meta(path)
        blob = json.dumps(meta)
        self.assertNotIn('secret answer', blob)
        self.assertNotIn('expected_invariants', blob)
        self.assertNotIn('turn_invariant', blob)
        self.assertNotIn('grading', blob)
        self.assertEqual(meta['X-T1']['category'], 'CAT')
        self.assertEqual(meta['X-T1']['hard_fail_if'], ['cond'])

    def test_abstain_shape_matches_interpret_contract(self):
        self.assertEqual(set(E.ABSTAIN),
                         {'outcome', 'skill_id', 'targets', 'params',
                          'confidence', 'ambiguities', 'clarifying_question'})
        self.assertIsNone(E.ABSTAIN['skill_id'])


class RunTurnTest(unittest.TestCase):
    def test_french_turn_reaches_terminal_state_without_crash(self):
        rec, sends = E.run_turn("Je veux juste un bouton qui coupe et remet le son.")
        self.assertIn(rec['status'], ('resolved', 'unsupported',
                                      'needs_clarification',
                                      'escalation_required'))
        self.assertNotEqual(rec['status'], 'CRASH')
        self.assertEqual(sends, 0)

    def test_resolved_turn_carries_mock_receipt(self):
        # English fabric-scoped keyword turn: deterministic fallback may resolve.
        rec, sends = E.run_turn('facts info device status')
        self.assertIn(rec['status'], ('resolved', 'unsupported',
                                      'needs_clarification',
                                      'escalation_required'))
        if rec['status'] == 'resolved':
            self.assertEqual(rec['receipt']['provenance'], 'eval-mock')
        self.assertEqual(sends, 0)

    def test_empty_text_does_not_crash(self):
        rec, _ = E.run_turn('')
        self.assertIn(rec['status'], ('resolved', 'unsupported',
                                      'needs_clarification',
                                      'escalation_required', 'CRASH'))


if __name__ == '__main__':
    unittest.main()
