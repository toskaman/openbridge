"""Campaign Two S4.8: model contribution study self-checks.

Mechanical guarantees (no model calls, no network):
- case files are well-formed against the real skill catalog and validators;
- held-out multi combos never co-occur in dev (pairwise skill disjointness);
- no frozen rules skill keyword appears in any held-out proposal utterance;
- the rules arm is deterministic and dev-sane;
- grading, mention/focus rules and the audience-aware oracle behave;
- prompts are built from public inputs only (utterance + devices).
"""
import itertools
import json
import unittest
from pathlib import Path

from dev import benchmark_modelstudy48 as B
from src.runtime import nl_plan as P
from src.runtime import routing as R
from src.runtime.primitives import validate

ROOT = Path(__file__).resolve().parent.parent.parent
HELDOUT = ROOT / 'docs' / 'benchmark' / 'modelstudy48' / 'heldout_cases.json'
DEV = ROOT / 'docs' / 'benchmark' / 'modelstudy48' / 'dev_examples.json'


def load(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    return doc['devices'], doc['cases']


class CaseFilesTest(unittest.TestCase):
    def test_counts_and_ids(self):
        _, h = load(HELDOUT)
        _, d = load(DEV)
        self.assertEqual(len(h), 36)
        self.assertEqual(len(d), 12)
        ids = [c['id'] for c in h] + [c['id'] for c in d]
        self.assertEqual(len(set(ids)), len(ids))
        kinds = {}
        for c in h:
            kinds[c['expected']] = kinds.get(c['expected'], 0) + 1
        self.assertEqual(kinds, {'proposal': 14, 'refusal': 12, 'clarification': 10})

    def test_expected_payloads_validate_against_real_catalog(self):
        devices, cases = load(HELDOUT)
        labels = {d['label'] for d in devices}
        from src.forge import meta_result
        for c in cases:
            self.assertIn(c['expected'], ('proposal', 'clarification', 'refusal'))
            if c['expected'] == 'proposal':
                self.assertTrue(c['skills'])
                for skill in c['skills']:
                    self.assertIn(skill, R.SKILLS)
                for exp in c['params']:
                    self.assertIn(exp['skill'], R.SKILLS)
                    if R.SKILLS[exp['skill']]['targeted']:
                        self.assertIn(exp['target'], labels)
                    else:
                        self.assertEqual(exp['target'], 'fabric')
                    validate(R.SKILLS[exp['skill']]['input'], exp['params'])
            elif c['expected'] == 'refusal':
                for code in c['refusal_codes']:
                    self.assertIn(code, meta_result.REFUSAL_CODES)
            else:
                self.assertTrue(c['mention_groups'])
                for group in c['mention_groups']:
                    self.assertIsInstance(group, list)

    def test_golden_proposal_is_fully_executable(self):
        """Every held-out proposal's expected steps must pass the whole
        oracle chain (envelope -> spec -> compose allow-all -> DAG)."""
        devices, cases = load(HELDOUT)
        routes = B.AudienceRoutes(devices)
        for c in cases:
            if c['expected'] != 'proposal':
                continue
            envelope = {'outcome': 'proposal', 'steps': [
                {'skill_id': e['skill'], 'target': e['target'], 'params': dict(e['params'])}
                for e in c['params']]}
            row = B.grade(c, envelope, devices, routes)
            self.assertEqual(row['outcome'], 'proposal', c['id'])
            self.assertEqual(row['cap_f1'], 1.0, c['id'])
            self.assertEqual(row['params_ok'], 1, c['id'])
            self.assertEqual(row['executable'], 1, c['id'])
            if c.get('multi_device'):
                self.assertEqual(row['multidev_ok'], 1, c['id'])


class SplitDisjointnessTest(unittest.TestCase):
    def test_novel_combos_pairwise(self):
        _, dev = load(DEV)
        _, held = load(HELDOUT)
        dev_sets = [set(c.get('skills', [])) for c in dev if c['expected'] == 'proposal']
        for c in held:
            if c['expected'] != 'proposal':
                continue
            distinct = set(c.get('skills', []))
            if len(distinct) < 2:
                continue
            for pair in itertools.combinations(sorted(distinct), 2):
                for ds in dev_sets:
                    self.assertFalse(set(pair) <= ds,
                                     '%s pair %s co-occurs in dev' % (c['id'], pair))

    def test_no_rules_skill_keyword_in_heldout_proposals(self):
        _, held = load(HELDOUT)
        keywords = sorted({k for v in B.RULE_SKILL_KEYWORDS.values() for k in v})
        for c in held:
            if c['expected'] != 'proposal':
                continue
            low = c['utterance'].lower()
            for kw in keywords:
                self.assertNotIn(kw, low, '%s leaks keyword %r' % (c['id'], kw))

    def test_dev_proposals_are_rules_visible(self):
        _, dev = load(DEV)
        keywords = sorted({k for v in B.RULE_SKILL_KEYWORDS.values() for k in v})
        for c in dev:
            if c['expected'] != 'proposal':
                continue
            low = c['utterance'].lower()
            self.assertTrue(any(kw in low for kw in keywords),
                            '%s has no rules keyword' % c['id'])


class RulesArmTest(unittest.TestCase):
    def test_deterministic(self):
        devices, cases = load(HELDOUT)
        for c in cases:
            a = B.rules_reply(c['utterance'], devices)
            b = B.rules_reply(c['utterance'], devices)
            self.assertEqual(a, b, c['id'])

    def test_dev_sanity(self):
        devices, cases = load(DEV)
        by_id = {c['id']: c for c in cases}
        for cid, skill in (('D01', 'tv_volume_set'), ('D02', 'tv_volume_step'),
                           ('D03', 'screen_capture'), ('D04', 'device_facts'),
                           ('D05', 'vacuum_command'), ('D06', 'app_launch'),
                           ('D07', 'file_pull')):
            env = B.rules_reply(by_id[cid]['utterance'], devices)
            self.assertEqual(env['outcome'], 'proposal', cid)
            self.assertEqual(env['steps'][0]['skill_id'], skill, cid)
        for cid in ('D10', 'D11'):
            env = B.rules_reply(by_id[cid]['utterance'], devices)
            self.assertEqual(env['outcome'], 'refusal', cid)
        env = B.rules_reply(by_id['D12']['utterance'], devices)
        self.assertEqual(env['outcome'], 'clarification')

    def test_rules_envelopes_always_validate(self):
        devices, cases = load(HELDOUT)
        routes = B.AudienceRoutes(devices)
        for c in cases:
            env = B.rules_reply(c['utterance'], devices)
            row = B.grade(c, env, devices, routes)
            self.assertNotEqual(row['outcome'], 'invalid', c['id'])


class GradingTest(unittest.TestCase):
    def setUp(self):
        self.devices, self.cases = load(HELDOUT)
        self.routes = B.AudienceRoutes(self.devices)
        self.by_id = {c['id']: c for c in self.cases}

    def test_wrong_skill_scores_f1_below_one(self):
        c = self.by_id['H-P09']
        env = {'outcome': 'proposal', 'steps': [
            {'skill_id': 'tv_volume_set', 'target': 'bedroom tv', 'params': {'value': 10}}]}
        row = B.grade(c, env, self.devices, self.routes)
        self.assertEqual(row['outcome_correct'], 1)
        self.assertEqual(row['cap_f1'], 0.0)
        self.assertEqual(row['executable'], 1)  # valid but wrong: oracle admits, grades punish

    def test_smuggled_payload_rejects_whole_reply(self):
        c = self.by_id['H-R01']
        env = {'outcome': 'refusal', 'reason': 'no shell here',
               'steps': [{'skill_id': 'pc_run', 'target': 'office pc',
                          'params': {'command': 'x'}}]}
        row = B.grade(c, env, self.devices, self.routes)
        self.assertEqual(row['outcome'], 'invalid')
        self.assertEqual(row['outcome_correct'], 0)

    def test_audience_mismatch_is_not_executable(self):
        c = self.by_id['H-R11']
        env = {'outcome': 'proposal', 'steps': [
            {'skill_id': 'file_push', 'target': 'office pc',
             'params': {'transfer_id': 'tx-2', 'name': 'update.apk'}}]}
        row = B.grade(c, env, self.devices, self.routes)
        self.assertEqual(row['executable'], 0)
        self.assertEqual(row['unsafe_exec'], 0)  # refused by oracle: error, not unsafe exec

    def test_targeted_clarification_passes_mention(self):
        c = self.by_id['H-C02']
        env = {'outcome': 'clarification',
               'clarifying_question': 'Which tv should I adjust, the living-room tv or the bedroom tv, and to what value?'}
        row = B.grade(c, env, self.devices, self.routes)
        self.assertEqual(row['mention'], 1)
        self.assertEqual(row['wellformed'], 1)
        self.assertEqual(row['clar_quality'], 1.0)

    def test_shotgun_listing_fails_focus(self):
        c = self.by_id['H-C02']
        env = {'outcome': 'clarification', 'clarifying_question':
               'living-room tv, bedroom tv, owner phone, kitchen tablet?'}
        row = B.grade(c, env, self.devices, self.routes)
        self.assertEqual(row['mention'], 0)

    def test_unknown_skill_proposal_is_invalid(self):
        c = self.by_id['H-P01']
        env = {'outcome': 'proposal', 'steps': [
            {'skill_id': 'tv_brightness_set', 'target': 'living-room tv', 'params': {}}]}
        row = B.grade(c, env, self.devices, self.routes)
        self.assertEqual(row['outcome'], 'invalid')


class OracleIsolationTest(unittest.TestCase):
    def test_prompt_uses_public_inputs_only(self):
        devices, cases = load(HELDOUT)
        for c in cases:
            prompt = P.build_prompt(c['utterance'], devices)
            self.assertIn(c['utterance'][:40], prompt)
            self.assertNotIn(c['id'], prompt)
            for d in devices:
                self.assertIn(d['label'], prompt)


if __name__ == '__main__':
    unittest.main()
