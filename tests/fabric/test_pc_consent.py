"""Per-PC full-control consent (fail-closed): OFF unless the owner opted in."""
import json
import unittest

from src.fabric import pc_consent as P


class ConsentStore(unittest.TestCase):
    def test_default_is_off(self):
        with P.temp_store() as store:
            self.assertFalse(store.allowed('aa01bb02'))

    def test_enable_needs_explicit_confirm(self):
        with P.temp_store() as store:
            with self.assertRaises(P.ConsentError):
                store.set('aa01bb02', True, confirm=False)
            self.assertFalse(store.allowed('aa01bb02'))
            store.set('aa01bb02', True, confirm=True)
            self.assertTrue(store.allowed('aa01bb02'))

    def test_disable_is_immediate_and_needs_no_confirm(self):
        with P.temp_store() as store:
            store.set('aa01bb02', True, confirm=True)
            store.set('aa01bb02', False)
            self.assertFalse(store.allowed('aa01bb02'))

    def test_per_pc_isolation(self):
        with P.temp_store() as store:
            store.set('aa01bb02', True, confirm=True)
            self.assertFalse(store.allowed('cc03dd04'))

    def test_corrupt_store_fails_closed(self):
        with P.temp_dir() as path:
            (path / 'pc_full_control.json').write_text('{oops', encoding='utf-8')
            store = P.PcConsentStore(path / 'pc_full_control.json')
            self.assertFalse(store.allowed('aa01bb02'))
            self.assertIsNotNone(store.error)

    def test_identity_must_be_opaque_hash(self):
        with P.temp_store() as store:
            with self.assertRaises(P.ConsentError):
                store.set('DESKTOP-PLAIN-NAME', True, confirm=True)
            with self.assertRaises(P.ConsentError):
                store.set('', True, confirm=True)

    def test_warning_text_states_scope(self):
        self.assertIn('managed', P.FULL_CONTROL_WARNING.lower())
        self.assertIn('revok', P.FULL_CONTROL_WARNING.lower() + P.FULL_CONTROL_WARNING)


if __name__ == '__main__':
    unittest.main()
