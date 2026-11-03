"""§7.5 instant reuse + §7.4 lifecycle slice: saved composed skills.

A saved skill replays WITHOUT model regeneration, but lookup never
authorizes: the caller must still run fresh liveness, consent, approve
and execute. States: PROPOSED -> READY -> DISABLED <-> READY, REVOKED
terminal. Lookup hits only READY records.
"""
import unittest

from src.runtime import skill_memory as M


def rec(**kw):
    base = {'skill_id': 'app_launch', 'targets': [{'kind': 'device', 'ref': 'tv'}],
            'params': {'package': 'com.google.android.youtube.tv'},
            'capability_ids': ['app_launch'], 'provenance': {'model': 'm', 'digest': 'd'}}
    base.update(kw)
    return base


class ReuseStore(unittest.TestCase):
    def test_save_lookup_roundtrip_without_model(self):
        s = M.Memory()
        self.assertIsNone(s.lookup('Open YouTube on the TV'))
        s.save('Open YouTube on the TV', rec())
        s.mark_ready('Open YouTube on the TV')
        hit = s.lookup('Open YouTube on the TV')
        self.assertEqual(hit['skill_id'], 'app_launch')
        self.assertEqual(hit['capability_ids'], ['app_launch'])
        self.assertEqual(hit['provenance'], {'model': 'm', 'digest': 'd'})
        self.assertEqual(hit['state'], 'READY')

    def test_lookup_matches_normalized_text_only(self):
        s = M.Memory()
        s.save('  Open   YouTube on the TV ', rec())
        s.mark_ready('open youtube on the tv')
        self.assertIsNotNone(s.lookup('Open YouTube on the TV'))
        self.assertIsNone(s.lookup('Open Netflix on the TV'))

    def test_proposed_is_not_reusable_until_verified(self):
        s = M.Memory()
        s.save('Open YouTube on the TV', rec())
        self.assertIsNone(s.lookup('Open YouTube on the TV'))

    def test_disable_enable_revoke(self):
        s = M.Memory()
        s.save('t', rec())
        s.mark_ready('t')
        s.disable('t')
        self.assertIsNone(s.lookup('t'))
        s.enable('t')
        self.assertIsNotNone(s.lookup('t'))
        s.revoke('t')
        self.assertIsNone(s.lookup('t'))
        with self.assertRaises(M.SkillMemoryError):
            s.enable('t')

    def test_illegal_transitions_refused(self):
        s = M.Memory()
        with self.assertRaises(M.SkillMemoryError):
            s.mark_ready('missing')
        s.save('t', rec())
        with self.assertRaises(M.SkillMemoryError):
            s.enable('t')  # PROPOSED, not DISABLED

    def test_save_validates_record_shape(self):
        s = M.Memory()
        with self.assertRaises(M.SkillMemoryError):
            s.save('t', {'skill_id': 'app_launch'})  # missing targets/params/provenance

    def test_to_intent_replays_validator_clean(self):
        from src.runtime.intent import validate_intent
        s = M.Memory()
        s.save('Open YouTube on the TV', rec())
        s.mark_ready('Open YouTube on the TV')
        doc = M.to_intent(s.lookup('Open YouTube on the TV'), 'Open YouTube on the TV', 'en')
        self.assertEqual(validate_intent(doc), [])
        self.assertEqual(doc['status'], 'resolved')
        self.assertEqual(doc['provenance'], {'parser': 'local', 'model_id': None})
        with self.assertRaises(M.SkillMemoryError):
            M.to_intent({**s.lookup('Open YouTube on the TV'), 'state': 'DISABLED'}, 't')

    def test_persists_through_state_store(self):
        import tempfile, os
        from src.runtime.state_store import StateStore
        with tempfile.TemporaryDirectory() as td:
            st = StateStore(os.path.join(td, 's.json'))
            m1, m2 = M.Memory(st), M.Memory(st)
            m1.save('t', rec())
            m1.mark_ready('t')
            self.assertEqual(m2.lookup('t')['state'], 'READY')
            m2.revoke('t')
            self.assertIsNone(m1.lookup('t'))


if __name__ == '__main__':
    unittest.main()
