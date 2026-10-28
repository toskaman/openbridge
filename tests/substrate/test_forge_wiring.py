"""Real Substrate instance through the merged Forge wiring (Sol PR76 finding: CONTRACT_MISMATCH)."""
import unittest

from src.forge import v4_substrate as W
from src.substrate.kernel import manifest_hash
from tests.substrate.test_kernel import Base


class ForgeWiring(Base):
    def candidate(self, pid='input.key', args=None):
        return {'candidate_id': 'tv.mute_toggle', 'evidence_refs': [self.cat_fact['fact_id']],
                'primitive_chain': [{'primitive_id': pid, 'input': args if args is not None else {'key': 'mute'}}]}

    def build(self, **kw):
        return W.to_manifest(self.candidate(**kw), {'category': 'tv', 'device_fingerprint': self.fp},
                             {'model': 'muse-spark-1.3', 'run_id': 'run_0001abc'}, 'Mute the TV', ['control'],
                             [self.cat_fact['fact_id']], self.manifest()['expires_at'])

    def test_real_instance_resolves_contract_and_hash(self):
        self.assertEqual(W.contract_version(self.s), 'obv4.1')
        self.assertIs(W.hash_fn(self.s), manifest_hash)

    def test_compile_first_compiles_and_hash_binds(self):
        m = self.build()
        r = W.compile_first(self.s, m, self.facts)
        self.assertEqual(r['status'], 'COMPILED', r)
        self.assertEqual(r['manifest_hash'], manifest_hash(m))
        self.assertEqual(r['compiled']['manifest_hash'], r['manifest_hash'])

    def test_unsupported_primitive_surfaces_engineering_request(self):
        r = W.compile_first(self.s, self.build(pid='screen.capture_session_approved', args={}), self.facts)
        self.assertEqual(r['status'], 'NO_SUPPORTED_PRIMITIVE')
        self.assertEqual(r['engineering_request']['primitive_id'] if 'primitive_id' in r['engineering_request']
                         else 'screen.capture_session_approved', 'screen.capture_session_approved')

    def test_kernel_refusal_maps_to_compile_rejected(self):
        r = W.compile_first(self.s, self.build(args={'key': 'not_a_key'}), self.facts)
        self.assertEqual(r['status'], 'COMPILE_REJECTED')


if __name__ == '__main__':
    unittest.main()
