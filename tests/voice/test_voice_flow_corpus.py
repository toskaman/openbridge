"""Campaign Two §4.6 controlled FR/EN voice-to-capability evaluation corpus.

Each case in corpus_voice_flow.json runs through a deterministic engine:

- voice_intent: src/ai/voice_intent.py compile_intent (proposal path).
- normalize_lang: src/ai/voice_normalize.py detect_lang.
- normalize_screen: check_control_reference (revoked/active control refs).
- migrate_parse: src/runtime/migrate.py parse_request (sibling slice §4.2;
  pinned here as regression, untouched by this branch).

A case passes when every `expected` key matches and, for
safety=no_proposal cases, the outcome is never a proposal. Baseline
(pre-change) per-case results live in VOICE_FLOW_RESULTS.md next to this file.
"""
import json
import unittest
from pathlib import Path

from src.ai import voice_intent as VI
from src.ai import voice_normalize as VN
from src.runtime import migrate as MIG

_HERE = Path(__file__).resolve().parent
_CORPUS = json.loads((_HERE / 'corpus_voice_flow.json').read_text(encoding='utf-8'))
DEVICES = _CORPUS['devices']
CASES = _CORPUS['cases']


def run_case(case):
    """Run one corpus case through the improved code. Returns observed dict."""
    engine = case['engine']
    if engine == 'voice_intent':
        out = VI.compile_intent(case['transcript'], DEVICES[case['devices']])
        return {'outcome': out.get('outcome'), 'intent': out.get('intent'),
                'device_key': out.get('device_key'),
                'needs_target': bool(out.get('needs_target')),
                'question': out.get('clarifying_question') or out.get('reason') or '',
                'lang': out.get('lang')}
    if engine == 'normalize_lang':
        return {'lang': VN.detect_lang(case['transcript'])}
    if engine == 'normalize_screen':
        fixed = VN.repair(VN.fold(case['transcript']))[0]
        params = case.get('params', {})
        verdict = VN.check_control_reference(
            fixed, active_labels=params.get('active_labels', ()),
            revoked_labels=params.get('revoked_labels', ()),
            active_ids=params.get('active_ids', ()))
        return {'verdict': verdict['verdict']}
    if engine == 'migrate_parse':
        parsed = MIG.parse_request(case['transcript'])
        return {'unparsed': parsed['unparsed'], 'source': parsed.get('source'),
                'dest': parsed.get('dest'), 'match': parsed.get('match')}
    raise AssertionError('unknown engine ' + engine)


def check_case(case, observed):
    """Mismatch strings for one case (empty when the case passes)."""
    errors = []
    for key, want in case['expected'].items():
        if key == 'question_contains':
            got = observed.get('question', '')
            if want.lower() not in str(got).lower():
                errors.append('question %r lacks %r' % (got, want))
        elif observed.get(key) != want:
            errors.append('%s: observed %r, expected %r'
                          % (key, observed.get(key), want))
    if case.get('safety') == 'no_proposal' and observed.get('outcome') == 'proposal':
        errors.append('SAFETY: uncertain speech became a proposal')
    return errors


class CorpusEval(unittest.TestCase):
    def test_all_cases_meet_expected(self):
        for case in CASES:
            with self.subTest(case=case['id']):
                errors = check_case(case, run_case(case))
                self.assertEqual(errors, [], case['transcript'])

    def test_corpus_covers_the_brief(self):
        cats = {c['cat'] for c in CASES}
        for required in ('watch7-regression', 'misrecognized-names', 'accents',
                         'short-partial', 'similar-actions', 'conflicting-intents',
                         'generated-controls', 'ambiguous-destinations',
                         'revoked-controls', 'irreversible'):
            self.assertIn(required, cats, required)
        self.assertGreaterEqual(len(CASES), 50)
        safety = [c for c in CASES if c.get('safety') == 'no_proposal']
        self.assertGreaterEqual(len(safety), 25)

    def test_uncertain_speech_never_becomes_a_proposal(self):
        for case in CASES:
            if case.get('safety') != 'no_proposal':
                continue
            with self.subTest(case=case['id']):
                observed = run_case(case)
                self.assertNotEqual(observed.get('outcome'), 'proposal')


if __name__ == '__main__':
    unittest.main()
