"""S2 UI drafting mechanics (offline): slot grammar, prompt builder, refusal codes."""
import unittest

from src.forge import v4_uidraft as U


class Draft(unittest.TestCase):
    def test_add_button_grammar_builds_valid_patch(self):
        patch = U.draft_from_slots(
            {'action': 'add_button', 'label': 'Dock', 'primitive': 'vacuum.dock',
             'params': {}, 'target_opaque_id': 'opaque:device:abc123'},
            primitive_ids=('vacuum.dock', 'vacuum.start'), model_run_id='mr-test')
        self.assertEqual(patch['widgets'][0]['kind'], 'button')
        self.assertEqual(patch['widgets'][0]['binding_primitive'], 'vacuum.dock')
        self.assertEqual(patch['origin'], 'meta_generated')

    def test_unknown_binding_refused_before_validator(self):
        with self.assertRaises(U.DraftError) as cm:
            U.draft_from_slots(
                {'action': 'add_button', 'label': 'X', 'primitive': 'nope.boom',
                 'params': {}, 'target_opaque_id': 'opaque:device:abc123'},
                primitive_ids=('vacuum.dock',), model_run_id='mr-test')
        self.assertIn('UNKNOWN_BINDING', str(cm.exception))

    def test_unsupported_action_refused_with_reason(self):
        with self.assertRaises(U.DraftError) as cm:
            U.draft_from_slots({'action': 'add_video', 'label': 'V'}, primitive_ids=(),
                               model_run_id='mr-test')
        self.assertIn('UNSUPPORTED_ACTION', str(cm.exception))

    def test_non_scalar_params_refused(self):
        with self.assertRaises(U.DraftError) as cm:
            U.draft_from_slots(
                {'action': 'add_button', 'label': 'X', 'primitive': 'vacuum.dock',
                 'params': {'nested': {'a': 1}}, 'target_opaque_id': 'opaque:device:abc123'},
                primitive_ids=('vacuum.dock',), model_run_id='mr-test')
        self.assertIn('PARAMS_MUST_BE_SCALARS', str(cm.exception))

    def test_prompt_builder_carries_caps_and_bindings(self):
        p = U.build_ui_prompt('add a dock button', [{'label': 'Vacuum', 'category': 'vacuum'}],
                              ('vacuum.dock',))
        self.assertIn('vacuum.dock', p)
        self.assertIn('Vacuum', p)
        self.assertIn('add a dock button', p)
        self.assertIn('text|button|status', p)

    def test_prompt_builder_shows_hints_and_copy_rules(self):
        p = U.build_ui_prompt('vacuum panel',
                              [{'label': 'Vacuum', 'category': 'vacuum',
                                'opaque_id': 'opaque:abc'}],
                              ('vacuum_command',),
                              hints={'vacuum_command': '{command=start|dock}'})
        self.assertIn('opaque:abc', p)
        self.assertIn('{command=start|dock}', p)
        self.assertIn('opaque:', p)
        self.assertIn('Example', p)


if __name__ == '__main__':
    unittest.main()
