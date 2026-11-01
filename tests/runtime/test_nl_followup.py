"""Campaign Two D2: deterministic context-aware NL follow-up resolution.

New module src/runtime/nl_followup.py sits ON TOP of the existing router
(src/runtime/nl_router.py is untouched): pronoun/ellipsis follow-ups are
resolved against the prior turn, and candidates are re-ranked against the
live capability graph. No model calls anywhere in this file.
"""
import json
import os
import unittest

from src.runtime import intent as I
from src.runtime import nl_followup as F
from src.runtime import nl_router as N

CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'nl_followup_corpus.json')

DEVICES = {'dev-tv1': {'key': 'dev-tv1', 'category': 'tv', 'label': 'Living room TV'},
           'dev-vac1': {'key': 'dev-vac1', 'category': 'vacuum', 'label': 'Roborock'}}


class FakeTransport:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def __call__(self, prompt):
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply(prompt) if callable(self.reply) else self.reply


def abstain(outcome, targets=()):
    return {'outcome': outcome, 'skill_id': None, 'targets': list(targets),
            'params': {}, 'confidence': 0.0, 'ambiguities': [],
            'clarifying_question': None}


def resolved(skill_id, outcome, targets):
    return {'outcome': outcome, 'skill_id': skill_id, 'targets': list(targets),
            'params': {}, 'confidence': 0.9, 'ambiguities': [],
            'clarifying_question': None}


def prior_doc(skill_id, targets, lang='en'):
    return N.parse('prior turn', lang, 'low',
                   FakeTransport(resolved(skill_id, 'prior turn', targets)), None)


VAC_PRIOR = [{'kind': 'device', 'ref': 'vacuum-1'}]
TV_PRIOR = [{'kind': 'device', 'ref': 'tv-1'}]


class DetectReference(unittest.TestCase):
    def test_en_pronouns(self):
        for text in ('pause it', 'turn it up', 'pause that one', 'stop this',
                     'show its status', 'send it home'):
            self.assertTrue(F.detect_reference(text, 'en'), text)

    def test_en_ellipsis(self):
        for text in ('louder', 'quieter', 'pause'):
            self.assertTrue(F.detect_reference(text, 'en'), text)

    def test_fr_pronouns_and_clitics(self):
        for text in ('mets-le en pause', 'baisse-le', 'fais-le biper',
                     'monte le son', 'mets-le plus fort', 'vide le bac'):
            self.assertTrue(F.detect_reference(text, 'fr'), text)

    def test_explicit_targets_are_not_followups(self):
        for text, lang in (('turn the tv up', 'en'), ('pause the vacuum', 'en'),
                           ('start cleaning with the vacuum', 'en'),
                           ('scan for bluetooth devices', 'en'),
                           ('démarre le ménage avec l\u2019aspirateur', 'fr')):
            self.assertFalse(F.detect_reference(text, lang), text)

    def test_capability_word_without_device_is_followup(self):
        # 'le'/'son' name WHAT, not WHICH device: still a follow-up.
        self.assertTrue(F.detect_reference('monte le son', 'fr'))
        # No pronoun and no ellipsis: not detectable as a reference.
        self.assertFalse(F.detect_reference('turn up the volume', 'en'))


class Rewrite(unittest.TestCase):
    def test_substitutes_prior_noun(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR)
        self.assertEqual(F.rewrite('pause it', prior), 'pause vacuum')

    def test_fr_clitic(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR, 'fr')
        self.assertEqual(F.rewrite('mets-le en pause', prior), 'mets vacuum en pause')

    def test_ellipsis_appends_noun(self):
        prior = prior_doc('tv_volume_set', TV_PRIOR)
        self.assertEqual(F.rewrite('louder', prior), 'louder tv')

    def test_no_prior_targets_gives_empty(self):
        self.assertEqual(F.rewrite('pause it', None), '')
        self.assertEqual(F.rewrite('pause it', {'targets': []}), '')


class FamilyGate(unittest.TestCase):
    def test_prior_family(self):
        self.assertEqual(F.prior_family(prior_doc('vacuum.start', VAC_PRIOR)), 'vacuum')
        self.assertEqual(F.prior_family(prior_doc('tv_volume_set', TV_PRIOR)), 'tv')
        self.assertIsNone(F.prior_family(None))
        self.assertIsNone(F.prior_family({'status': 'unsupported'}))

    def test_compatible(self):
        self.assertTrue(F.compatible('vacuum.pause', 'vacuum'))
        self.assertTrue(F.compatible('device_facts', 'vacuum'))
        self.assertTrue(F.compatible('device_facts', 'tv'))
        self.assertFalse(F.compatible('tv_volume_step', 'vacuum'))
        self.assertFalse(F.compatible('vacuum.pause', 'tv'))
        self.assertFalse(F.compatible('fabric.status', 'vacuum'))
        self.assertFalse(F.compatible('vacuum.pause', 'fabric'))
        self.assertFalse(F.compatible('nope.unknown', 'vacuum'))
        self.assertFalse(F.compatible('vacuum.pause', None))


class RankCandidates(unittest.TestCase):
    def test_live_family_boosted(self):
        ranked = F.rank_candidates([(1, 'vacuum.start'), (1, 'tv_volume_set')],
                                   {'d': {'category': 'vacuum'}})
        self.assertEqual(ranked[0][1], 'vacuum.start')
        self.assertGreater(ranked[0][0], ranked[1][0])

    def test_missing_family_demoted(self):
        ranked = F.rank_candidates([(1, 'vacuum.start'), (1, 'device_facts')],
                                   {'d': {'category': 'tv'}})
        self.assertEqual(ranked[0][1], 'device_facts')

    def test_fabric_and_any_always_live(self):
        ranked = F.rank_candidates([(0, 'fabric.status'), (0, 'vacuum.start')], {})
        self.assertGreater(ranked[0][0], ranked[-1][0])
        self.assertEqual(ranked[0][1], 'fabric.status')

    def test_unknown_skill_demoted(self):
        ranked = F.rank_candidates([(1, 'nope.unknown'), (1, 'fabric.status')], {})
        self.assertEqual(ranked[0][1], 'fabric.status')

    def test_deterministic_tie_order(self):
        scored = [(1, 'vacuum.start'), (1, 'vacuum.pause')]
        self.assertEqual(F.rank_candidates(scored, DEVICES),
                         F.rank_candidates(scored, DEVICES))


class TopCandidate(unittest.TestCase):
    def test_unique_best(self):
        self.assertEqual(F.top_candidate('pause it'), 'vacuum.pause')
        self.assertEqual(F.top_candidate('turn it up'), 'tv_volume_step')

    def test_tie_is_none(self):
        self.assertIsNone(F.top_candidate('vacuum'))  # whole family ties
        self.assertIsNone(F.top_candidate('do it again'))  # zero keywords

    def test_eligible_gates_before_election(self):
        # "show its status" ties device_facts/fabric.status unfiltered...
        self.assertIsNone(F.top_candidate('show its status'))
        # ...but a device prior rules fabric out as a candidate.
        got = F.top_candidate('show its status',
                              eligible=lambda c: F.compatible(c, 'vacuum'))
        self.assertEqual(got, 'device_facts')

    def test_keywordless_never_elected(self):
        self.assertIsNone(F.top_candidate('do it again', devices=DEVICES))


class ResolveFollowup(unittest.TestCase):
    def test_resolves_with_prior_targets(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR)
        doc = F.resolve_followup('pause it', 'en', prior, DEVICES)
        self.assertEqual(doc['status'], 'resolved')
        self.assertEqual(doc['skill_id'], 'vacuum.pause')
        self.assertEqual(doc['targets'], VAC_PRIOR)
        self.assertEqual(doc['confidence'], 0.6)
        self.assertEqual(I.validate_intent(doc), [])
        self.assertTrue(any('follow-up' in a for a in doc['ambiguities']))
        self.assertEqual(doc['provenance'], {'parser': 'rules', 'model_id': None})

    def test_guards_return_none(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR)
        self.assertIsNone(F.resolve_followup('pause it', 'en', None, DEVICES))
        self.assertIsNone(F.resolve_followup('pause it', 'xx', prior, DEVICES))
        self.assertIsNone(F.resolve_followup('', 'en', prior, DEVICES))
        self.assertIsNone(F.resolve_followup('x' * 2001, 'en', prior, DEVICES))
        self.assertIsNone(F.resolve_followup('pause the vacuum', 'en', prior, DEVICES))
        self.assertIsNone(F.resolve_followup('pause it', 'en',
                                              {'status': 'unsupported'}, DEVICES))

    def test_cross_family_is_none(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR)
        self.assertIsNone(F.resolve_followup('turn it up', 'en', prior, DEVICES))

    def test_fabric_prior_donates_nothing(self):
        prior = prior_doc('fabric.status', [{'kind': 'category', 'ref': 'fabric'}])
        self.assertIsNone(F.resolve_followup('pause it', 'en', prior, DEVICES))

    def test_prior_targets_not_mutated(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR)
        F.resolve_followup('pause it', 'en', prior, DEVICES)
        self.assertEqual(prior['targets'], VAC_PRIOR)


class ParseWithContext(unittest.TestCase):
    def test_hit_returns_context_doc_without_transport(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR)
        boom = FakeTransport(error=N.TransportError('must not be called'))
        doc = F.parse_with_context('pause it', 'en', 'low', boom, prior,
                                   devices=DEVICES)
        self.assertEqual(doc['skill_id'], 'vacuum.pause')
        self.assertEqual(boom.calls, [])

    def test_miss_delegates_to_router_unchanged(self):
        prior = prior_doc('vacuum.start', VAC_PRIOR)
        reply = resolved('vacuum.pause', 'pause cleaning', VAC_PRIOR)
        via_ctx = F.parse_with_context('pause the vacuum', 'en', 'low',
                                       FakeTransport(dict(reply)), prior,
                                       devices=DEVICES)
        direct = N.parse('pause the vacuum', 'en', 'low',
                         FakeTransport(dict(reply)), None)
        self.assertEqual(via_ctx['status'], direct['status'])
        self.assertEqual(via_ctx['skill_id'], direct['skill_id'])

    def test_none_prior_delegates(self):
        reply = resolved('vacuum.pause', 'pause cleaning', VAC_PRIOR)
        doc = F.parse_with_context('pause it', 'en', 'low',
                                   FakeTransport(dict(reply)), None,
                                   devices=DEVICES)
        self.assertEqual(doc['status'], 'resolved')
        self.assertEqual(doc['skill_id'], 'vacuum.pause')


class CorpusEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CORPUS, encoding='utf-8') as fh:
            cls.corpus = json.load(fh)

    def test_corpus_is_controlled(self):
        self.assertGreaterEqual(len(self.corpus), 25)
        langs = {c['lang'] for c in self.corpus}
        self.assertEqual(langs, {'en', 'fr'})
        self.assertTrue(any(c['expected_skill'] is None for c in self.corpus))
        ids = [c['id'] for c in self.corpus]
        self.assertEqual(len(ids), len(set(ids)))

    def test_after_resolves_every_case(self):
        for case in self.corpus:
            with self.subTest(case=case['id']):
                prior = (prior_doc(case['prior_skill'], case['prior_targets'],
                                   case['lang']) if case['prior_skill'] else None)
                hit = F.resolve_followup(case['followup'], case['lang'],
                                         prior, DEVICES)
                if case['expected_skill'] is None:
                    self.assertIsNone(hit, case['id'])
                else:
                    self.assertIsNotNone(hit, case['id'])
                    self.assertEqual(hit['skill_id'], case['expected_skill'])
                    self.assertEqual(hit['status'], 'resolved')
                    self.assertEqual(hit['targets'], case['prior_targets'])
                    self.assertEqual(I.validate_intent(hit), [])

    def test_before_is_strictly_worse(self):
        # Baseline: router fallback alone, model abstains (deterministic).
        before = after = 0
        for case in self.corpus:
            base = N.parse(case['followup'], case['lang'], 'low',
                           FakeTransport(abstain(case['followup'])), None)
            prior = (prior_doc(case['prior_skill'], case['prior_targets'],
                               case['lang']) if case['prior_skill'] else None)
            hit = F.resolve_followup(case['followup'], case['lang'],
                                     prior, DEVICES)
            exp = case['expected_skill']
            if exp is None:
                before += base['status'] != 'resolved'
                after += hit is None
            else:
                before += (base['status'] == 'resolved'
                           and base['skill_id'] == exp)
                after += (hit is not None and hit['skill_id'] == exp)
        self.assertLess(before, after)
        self.assertEqual(after, len(self.corpus))


if __name__ == '__main__':
    unittest.main()
