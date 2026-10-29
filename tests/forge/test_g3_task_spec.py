"""Sealed G3 task specs: commitment, binding, predicate and owner restore (offline)."""
import copy
import json
import os
import tempfile
import unittest

from dev import g3_task as G

VOL = {'spec_version': 1, 'task_id': 'example-volume', 'intent': 'Set the TV media volume to exactly 7.',
       'target_category': 'tv', 'offer': ['setting.set_exact', 'state.read_setting', 'state.audio'],
       'allowed_effects': [{'primitive_id': 'setting.set_exact', 'args': {'setting': 'media_volume', 'value': 7}}],
       'oracle': {'action': 'get', 'args': {'setting': 'media_volume'}, 'field': 'value'}, 'expect': {'value': 7},
       'restore': {'mode': 'owner_action', 'action': 'set', 'args': {'setting': 'media_volume', 'value': '$pre'}}}
CAT = {'setting.set_exact': {'side_effect_class': 'REVERSIBLE_EXACT'}, 'state.read_setting': {'side_effect_class': 'READ'},
       'state.audio': {'side_effect_class': 'READ'}, 'input.key': {'side_effect_class': 'IRREVERSIBLE'}}


class Commitment(unittest.TestCase):
    def write(self, spec):
        f = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
        json.dump(spec, f); f.close(); self.addCleanup(os.unlink, f.name); return f.name

    def test_committed_hash_loads_and_any_edit_is_refused(self):
        p = self.write(VOL)
        self.assertEqual(G.load(p, G.spec_sha256(VOL))['task_id'], 'example-volume')
        edited = copy.deepcopy(VOL); edited['expect']['value'] = 8
        with self.assertRaises(G.SpecError):
            G.load(self.write(edited), G.spec_sha256(VOL))

    def test_hash_is_key_order_independent(self):
        self.assertEqual(G.spec_sha256(VOL), G.spec_sha256(json.loads(json.dumps(VOL, sort_keys=True))))

    def test_invalid_specs(self):
        for mutate in (lambda s: s.pop('restore'), lambda s: s.update(allowed_effects=[]),
                       lambda s: s['allowed_effects'][0].update(primitive_id='app.launch'),
                       lambda s: s['oracle'].update(action='shell'), lambda s: s['restore'].update(mode='model')):
            bad = copy.deepcopy(VOL); mutate(bad)
            with self.assertRaises(G.SpecError):
                G.validate(bad)
        G.validate(G.MUTE_SMOKE)


class BindingAndPredicate(unittest.TestCase):
    def test_binding_exact(self):
        ok = [{'primitive_id': 'state.read_setting', 'args': {'setting': 'media_volume'}},
              {'primitive_id': 'setting.set_exact', 'args': {'setting': 'media_volume', 'value': 7}}]
        self.assertIsNone(G.effect_binding(ok, CAT, VOL))
        self.assertIsNotNone(G.effect_binding([dict(ok[1], args={'setting': 'media_volume', 'value': 70})], CAT, VOL))
        self.assertIsNotNone(G.effect_binding(ok + [{'primitive_id': 'input.key', 'args': {'key': 'mute'}}], CAT, VOL))

    def test_predicate(self):
        pre, mid = {'value': 20}, {'value': 7}
        self.assertEqual(G.predicate(VOL, pre, mid, {'value': 20}, True, True, 403), (True, []))
        self.assertFalse(G.predicate(VOL, {'value': 7}, mid, {'value': 7}, True, True, 403)[0])   # no-op
        self.assertFalse(G.predicate(VOL, pre, {'value': 20}, pre, True, True, 403)[0])          # effect not seen
        self.assertFalse(G.predicate(VOL, pre, mid, {'value': 7}, True, True, 403)[0])           # not restored
        self.assertFalse(G.predicate(VOL, pre, mid, pre, True, True, 200)[0])                    # revoke bypass

    def test_owner_restore_uses_pre_value(self):
        self.assertEqual(G.restore_args(VOL, {'value': 20}),
                         {'action': 'set', 'args': {'setting': 'media_volume', 'value': 20}})


class SequenceWithOwnerRestore(unittest.TestCase):
    def test_owner_restore_replaces_reinvoke(self):
        from dev.run_g3_smoke import act_restore_sequence
        calls = []
        out = act_restore_sequence(lambda t: (calls.append(t), (200, {'status': 'EXECUTED'}))[1],
                                   lambda: {'value': 7}, lambda: (200, {}), sleep=lambda s: None,
                                   observed=lambda m: G.observed(m, VOL),
                                   restore=lambda: (calls.append('owner'), (200, {'state': 'VERIFIED'}))[1])
        self.assertEqual(calls, ['act', 'owner'])
        self.assertEqual(out[3], 200)


if __name__ == '__main__':
    unittest.main()
