"""C1 bridge: S2 patch -> substrate UIViewPlan (contract-tested vs kernel.validate)."""
import unittest

from src.forge import v4_uidraft as U
from src.substrate import kernel as K

MH = 'sha256:' + 'cd' * 32

PATCH = {'schema_version': 1, 'patch_id': 'p-x', 'target_opaque_id': 'opaque:device:abc',
         'origin': 'meta_generated', 'model_run_id': 'mr-test01',
         'widgets': [{'widget_id': 'w-dock', 'kind': 'button', 'label': 'Dock',
                      'binding_primitive': 'vacuum.dock', 'params': {}},
                     {'widget_id': 'w-title', 'kind': 'text', 'label': 'Vacuum',
                      'binding_primitive': 'vacuum.dock', 'params': {}}]}


def emit(**kw):
    args = {'patch': PATCH, 'manifests': {'vacuum.dock': MH}, 'target_device_fp': 'fp-' + 'ab12' * 4,
            'profile_id': 'forge.draft', 'layout_version': 3, 'evidence_refs': ['src:forge/s2']}
    args.update(kw)
    return U.emit_install_plan(**args)


class Emit(unittest.TestCase):
    def test_emitted_plan_passes_kernel_schema(self):
        plan, needed = emit()
        self.assertEqual(K.validate('UIViewPlan', plan), [])
        self.assertEqual(plan['plan_hash'], K.manifest_hash({k: v for k, v in plan.items() if k != 'plan_hash'}))
        self.assertEqual(needed, {MH})
        by_id = {w['widget_id']: w for w in plan['widgets']}
        self.assertEqual(by_id['w-dock']['kind'], 'button')
        self.assertEqual(by_id['w-dock']['binding'], {'manifest_hash': MH, 'inputs': {}})
        self.assertEqual(by_id['w-title']['kind'], 'label')
        self.assertIsNone(by_id['w-title']['binding'])

    def test_missing_manifest_refused(self):
        with self.assertRaises(U.DraftError) as cm:
            emit(manifests={})
        self.assertIn('UI_MANIFEST_REQUIRED', str(cm.exception))

    def test_status_without_source_refused(self):
        p = dict(PATCH, widgets=[{'widget_id': 'w-s', 'kind': 'status', 'label': 'S',
                                  'binding_primitive': 'vacuum.dock', 'params': {}}])
        with self.assertRaises(U.DraftError) as cm:
            emit(patch=p)
        self.assertIn('STATUS_SOURCE_REQUIRED', str(cm.exception))

    def test_status_with_source_maps(self):
        w = {'widget_id': 'w-s', 'kind': 'status', 'label': 'Last',
             'binding_primitive': 'vacuum.dock', 'params': {}}
        plan, _ = emit(patch=dict(PATCH, widgets=PATCH['widgets'] + [w]),
                       sources={'w-s': 'w-dock'})
        by_id = {x['widget_id']: x for x in plan['widgets']}
        self.assertEqual(by_id['w-s']['source'], 'w-dock')
        self.assertIsNone(by_id['w-s']['binding'])
        self.assertEqual(K.validate('UIViewPlan', plan), [])

    def test_injection_label_refused(self):
        w = dict(PATCH['widgets'][0], label='<script>x')
        with self.assertRaises(U.DraftError) as cm:
            emit(patch=dict(PATCH, widgets=[w]))
        self.assertIn('INJECTION_SUSPECT', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
