"""Offline regressions for Sol's G3-runner HOLD (PR88 review, issue 36).

No network, no ledger, no hardware: the HOLD fixes live in pure/extracted
functions so the false-success predicate, blind restore, missing revoke and
invented scope are all reproducible without a run.
"""
import unittest

from dev.run_g3_smoke import act_restore_sequence, resolve_scope, success_predicate


def ok_act():
    return 200, {'status': 'VERIFIED'}


class ResolveScope(unittest.TestCase):
    def test_live_snapshot_links_for_tv_key(self):
        links = [{'parent': 'pc', 'child': 'tv1', 'transport': 'WIFI', 'grants': ['read', 'control']},
                 {'parent': 'pc', 'child': 'phone', 'transport': 'USB', 'grants': ['observe']}]
        scope, err = resolve_scope(links, 'tv1')
        self.assertIsNone(err)
        self.assertEqual(scope, ['control', 'read'])

    def test_other_children_ignored(self):
        links = [{'parent': 'pc', 'child': 'phone', 'transport': 'USB', 'grants': ['observe']}]
        scope, err = resolve_scope(links, 'tv1')
        self.assertIsNone(scope)
        self.assertIn('refusing invented scope', err)

    def test_missing_links_kills_never_invents(self):
        for links in (None, [], [{}], [{'child': 'tv1'}], [{'child': 'tv1', 'grants': []}]):
            scope, err = resolve_scope(links, 'tv1')
            self.assertIsNone(scope)
            self.assertIn('refusing invented scope', err)


class SuccessPredicate(unittest.TestCase):
    def happy(self):
        return dict(pre={'muted': False, 'i': 3}, mid={'muted': True, 'i': 3},
                    post={'muted': False, 'i': 3}, st1=200, r1={'status': 'VERIFIED'},
                    st2=200, after_revoke_http=403)

    def test_transition_scores_success(self):
        ok, reasons = success_predicate(**self.happy())
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_already_muted_is_not_success(self):
        kw = self.happy()
        kw['pre'] = {'muted': True, 'i': 3}
        kw['post'] = {'muted': True, 'i': 3}
        ok, reasons = success_predicate(**kw)
        self.assertFalse(ok)
        self.assertTrue(any('already-muted' in r for r in reasons))

    def test_no_act_effect_is_not_success(self):
        kw = self.happy()
        kw['mid'] = {'muted': False, 'i': 3}
        ok, _ = success_predicate(**kw)
        self.assertFalse(ok)

    def test_unrestored_is_not_success(self):
        kw = self.happy()
        kw['post'] = {'muted': True, 'i': 3}
        ok, _ = success_predicate(**kw)
        self.assertFalse(ok)

    def test_failed_act_is_not_success(self):
        kw = self.happy()
        kw['st1'] = 500
        ok, _ = success_predicate(**kw)
        self.assertFalse(ok)

    def test_revoke_bypass_is_not_success(self):
        kw = self.happy()
        kw['after_revoke_http'] = 200
        ok, _ = success_predicate(**kw)
        self.assertFalse(ok)


class ActRestoreSequence(unittest.TestCase):
    def test_happy_path_order(self):
        calls = []

        def invoke(tag):
            calls.append(('invoke', tag))
            return 200, {'status': 'VERIFIED'}

        def oracle():
            calls.append(('oracle',))
            return {'muted': True}

        def revoke():
            calls.append(('revoke',))
            return 200, {}
        out = act_restore_sequence(invoke, oracle, revoke, sleep=lambda s: None)
        self.assertEqual([c[0] for c in calls],
                         ['invoke', 'oracle', 'invoke', 'oracle', 'revoke'])
        self.assertEqual(calls[2], ('invoke', 'restore'))
        self.assertEqual(out[6], {'http': 200})

    def test_failed_act_skips_restore_but_revokes(self):
        calls = []

        def invoke(tag):
            calls.append(tag)
            return (500, {}) if tag == 'act' else (200, {})
        out = act_restore_sequence(invoke, lambda: {'muted': False}, lambda: (200, {}),
                                   sleep=lambda s: None)
        self.assertNotIn('restore', calls)
        self.assertIsNone(out[5])  # post oracle never ran
        self.assertEqual(out[6]['http'], 200)

    def test_oracle_crash_still_revokes(self):
        revoked = []

        def invoke(tag):
            return 200, {'status': 'VERIFIED'}

        def oracle():
            raise ConnectionError('link down')

        def revoke():
            revoked.append(True)
            return 200, {}
        with self.assertRaises(ConnectionError):
            act_restore_sequence(invoke, oracle, revoke, sleep=lambda s: None)
        self.assertEqual(revoked, [True])

    def test_revoke_crash_is_recorded_not_raised(self):
        def revoke():
            raise ConnectionError('link down')
        out = act_restore_sequence(lambda t: (200, {'status': 'VERIFIED'}),
                                   lambda: {'muted': True}, revoke, sleep=lambda s: None)
        self.assertEqual(out[6]['http'], -1)
        self.assertIn('ConnectionError', out[6]['error'])


if __name__ == '__main__':
    unittest.main()
