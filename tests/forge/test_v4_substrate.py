"""V4 Muse->substrate wiring: obv4.1 mapping + compile-first. Substrate is duck-typed
(the substrate PR is unmerged); the stub below mirrors the documented contract."""
import json
import unittest

from src.forge import v4_substrate as VS


class StubError(Exception):
    def __init__(self, code, extra=None):
        super().__init__(code)
        self.code = code
        self.extra = extra or {}


class StubSubstrate:
    CONTRACT_VERSION = 'obv4.1'

    def __init__(self, behavior='ok'):
        self.behavior = behavior
        self.seen = []

    def compile(self, manifest, facts=(), inputs=None, for_dispatch=False):
        self.seen.append((manifest, tuple(facts)))
        if self.behavior == 'ok':
            return {'manifest_hash': 'sha256:abc', 'steps': len(manifest['steps'])}
        if self.behavior == 'unsupported':
            raise StubError('REJECTED_UNSUPPORTED_PRIMITIVE',
                            {'engineering_request': {'primitive_id': 'x', 'reason': 'BLOCKED'}})
        raise StubError('PERMISSION_DENIED')

    def manifest_hash(self, manifest):
        import hashlib
        return 'sha256:' + hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


CAND = {'schema_version': 1, 'candidate_id': 'tv.mute_toggle', 'origin': 'meta_generated',
        'intent': 'mute tv', 'target_opaque_id': 't',
        'primitive_chain': [{'primitive_id': 'input.key', 'input': {'key': 'mute'}}],
        'preconditions': [], 'postconditions': [], 'required_grants': ['control'],
        'evidence_refs': ['f-a8477062bde7bd72'], 'model_run_id': 'mr-1'}


class Wiring(unittest.TestCase):
    def test_manifest_shape_obv41(self):
        m = VS.to_manifest(CAND, {'category': 'tv', 'device_fingerprint': 'fp-1'},
                           {'model': 'muse-spark-1.3', 'run_id': 'run_1'}, 'Mute the TV',
                           ['control', 'read'], ['f-a8477062bde7bd72'], '2027-01-15T09:00:00Z')
        self.assertEqual(m['manifest_version'], 'obv4.1')
        self.assertEqual(m['origin'], 'meta_generated')
        self.assertEqual(m['steps'][0]['on_uncertain'], 'INCONCLUSIVE')
        self.assertEqual(m['model_run']['provider'], 'meta')

    def test_compile_first_ok(self):
        sub = StubSubstrate('ok')
        m = VS.to_manifest(CAND, {'category': 'tv', 'device_fingerprint': 'fp-1'},
                           {'model': 'm', 'run_id': 'r'}, 'T', ['control'], [], '2027-01-01T00:00:00Z')
        r = VS.compile_first(sub, m, [])
        self.assertEqual(r['status'], 'COMPILED')
        self.assertTrue(r['manifest_hash'].startswith('sha256:'))

    def test_unsupported_surfaces_engineering_request(self):
        sub = StubSubstrate('unsupported')
        m = VS.to_manifest(CAND, {'category': 'tv', 'device_fingerprint': 'fp-1'},
                           {'model': 'm', 'run_id': 'r'}, 'T', ['control'], [], '2027-01-01T00:00:00Z')
        r = VS.compile_first(sub, m, [])
        self.assertEqual(r['status'], 'NO_SUPPORTED_PRIMITIVE')
        self.assertEqual(r['engineering_request']['reason'], 'BLOCKED')

    def test_other_reject_mapped(self):
        sub = StubSubstrate('deny')
        m = VS.to_manifest(CAND, {'category': 'tv', 'device_fingerprint': 'fp-1'},
                           {'model': 'm', 'run_id': 'r'}, 'T', ['control'], [], '2027-01-01T00:00:00Z')
        r = VS.compile_first(sub, m, [])
        self.assertEqual(r['status'], 'COMPILE_REJECTED')
        self.assertEqual(r['code'], 'PERMISSION_DENIED')

    def test_ui_plan_hash_recomputable(self):
        plan = VS.ui_plan('tv.remote', 'fp-1', [{'widget_id': 'mute', 'label': 'Mute',
                                                'permission_label': 'control TV keys',
                                                'manifest_hash': 'sha256:abc', 'inputs': {}}],
                          'run_1', ['src:wear/ui'])
        body = {k: v for k, v in plan.items() if k != 'plan_hash'}
        self.assertEqual(plan['plan_hash'], 'sha256:' + __import__('hashlib').sha256(
            json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest())

    def test_ui_plan_rejects_bindingless_button(self):
        with self.assertRaises(VS.WireError):
            VS.ui_plan('tv.remote', 'fp-1', [{'widget_id': 'x', 'label': 'X',
                                              'permission_label': '', 'manifest_hash': '', 'inputs': {}}],
                       'run_1', [])

    def test_module_level_layout_like_real_kernel(self):
        import sys, types
        mod = types.ModuleType('fake_kernel72')
        mod.CONTRACT_VERSION = 'obv4.1'
        mod.manifest_hash = lambda m: 'sha256:real-shape'

        class RealShape:
            def compile(self, manifest, facts=(), inputs=None, for_dispatch=False):
                return {'ok': True}
        RealShape.__module__ = 'fake_kernel72'
        sys.modules['fake_kernel72'] = mod
        try:
            m = VS.to_manifest(CAND, {'category': 'tv', 'device_fingerprint': 'fp-1'},
                               {'model': 'm', 'run_id': 'r'}, 'T', ['control'], [], '2027-01-01T00:00:00Z')
            r = VS.compile_first(RealShape(), m, [])
            self.assertEqual(r, {'status': 'COMPILED', 'manifest_hash': 'sha256:real-shape',
                                 'compiled': {'ok': True}})
        finally:
            del sys.modules['fake_kernel72']

    def test_real_kernel_class_if_merged(self):
        try:
            from src.substrate.kernel import Substrate
        except ImportError:
            self.skipTest('substrate PR unmerged')
        obj = Substrate.__new__(Substrate)
        self.assertEqual(VS.contract_version(obj), 'obv4.1')
        self.assertTrue(callable(VS.hash_fn(obj)))

    def test_canonical_matches_kernel_on_unicode(self):
        import hashlib, json
        from src.forge import v4_schemas as S
        value = {'label': 'héllo → tv'}
        expect = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                           ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(S.digest(value), expect)


if __name__ == '__main__':
    unittest.main()
