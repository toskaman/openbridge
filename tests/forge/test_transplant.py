"""Campaign Two §4.1: transplantation pipeline tests. Simulated companions only."""
import copy
import unittest

from src.forge import transplant as T
from src.forge import v4_evidence as E
from src.forge.fixtures import manifest
from src.forge.service import ForgeService, MemoryProvider

NOW = 1_800_000_000.0
PRIMS = ('relay_ble_scan',)


class StubSubstrate:
    CONTRACT_VERSION = 'obv4.1'

    def __init__(self):
        self.seen = []

    def compile(self, manifest_doc, facts=(), inputs=None, for_dispatch=False):
        self.seen.append(manifest_doc)
        return {'manifest_hash': 'sha256:stub', 'steps': len(manifest_doc['steps'])}

    def manifest_hash(self, manifest_doc):
        return 'sha256:stub'


def companions():
    return {
        'src-1': {'category': 'phone', 'simulated': True, 'online': True,
                  'grants': ['observe', 'read'], 'primitives': list(PRIMS),
                  'capabilities': ['tv.ble.observations']},
        'tgt-1': {'category': 'tv', 'simulated': True, 'online': True,
                  'grants': ['observe', 'read'], 'primitives': list(PRIMS),
                  'capabilities': []},
    }


def links():
    return [{'parent': 'src-1', 'child': 'tgt-1', 'transport': 'LAN',
             'grants': ('observe', 'read'), 'source': 'SIM'}]


def bundle():
    return E.resolve(({'category': 'tv', 'device_id': 'tgt-1',
                       'permission_scope': ['observe', 'read'],
                       'facts': [{'fact_id': 'f0', 'kind': 'name', 'value': 'TV',
                                  'source': 'sim', 'observed_at': NOW}]},),
                     (), PRIMS, NOW)


def service():
    comps = companions()
    return T.TransplantService(comps, links(), T.DeterministicStubProposer(),
                               T.SimulatedDispatcher(), substrate=StubSubstrate(),
                               service_factory=lambda m: ForgeService(
                                   MemoryProvider(copy.deepcopy(m)),
                                   clock=lambda: NOW))


def run_full(svc, **over):
    kw = dict(source_capability_id='tv.ble.observations', target_id='tgt-1',
              intent='mirror ble observations', bundle=bundle(),
              primitive_ids=PRIMS, manifest=manifest(NOW),
              model_run={'model': 'stub-meta-1', 'run_id': 'run-1'},
              title='Mirror observations', facts_required=[], expires_at=NOW + 60,
              target_category='tv', consent=True)
    kw.update(over)
    return svc.transplant(**kw)


class Stages(unittest.TestCase):
    def test_discover_source(self):
        svc = service()
        src = svc.discover_source('tv.ble.observations')
        self.assertEqual(src['companion_id'], 'src-1')
        with self.assertRaises(T.TransplantError):
            svc.discover_source('invented.cap')

    def test_discover_refuses_real_hardware(self):
        svc = service()
        svc.companions['src-1']['simulated'] = False
        with self.assertRaisesRegex(T.TransplantError, 'SIMULATED'):
            svc.discover_source('tv.ble.observations')

    def test_target_compat_and_grant_check(self):
        svc = service()
        tgt = svc.check_target('tgt-1', PRIMS, ('observe', 'read'))
        self.assertEqual(tgt['companion_id'], 'tgt-1')
        with self.assertRaisesRegex(T.TransplantError, 'INCOMPATIBLE'):
            svc.check_target('tgt-1', ('nope_prim',), ('observe',))
        with self.assertRaisesRegex(T.TransplantError, 'GRANT_MISSING'):
            svc.check_target('tgt-1', PRIMS, ('observe', 'read', 'control'))
        svc.companions['tgt-1']['simulated'] = False
        with self.assertRaisesRegex(T.TransplantError, 'SIMULATED'):
            svc.check_target('tgt-1', PRIMS, ('observe',))

    def test_route_selection_needs_granted_link(self):
        svc = service()
        route = svc.select_route('src-1', 'tgt-1')
        self.assertTrue(route['simulated'])
        svc.links = []
        with self.assertRaisesRegex(T.TransplantError, 'NO_ROUTE'):
            svc.select_route('src-1', 'tgt-1')

    def test_propose_validates_schema_and_evidence(self):
        svc = service()
        cand, meta = svc.propose('mirror', bundle(), PRIMS, 'tv')
        self.assertEqual(cand['origin'], 'meta_generated')
        self.assertEqual(meta['prompt_version'], 'v4-synth-5')

        class Liar:
            def propose(self, request):
                good = T.DeterministicStubProposer().propose(request)['candidate']
                good['evidence_refs'] = ['invented-ref']
                return {'candidate': good}

        svc.proposer = Liar()
        with self.assertRaisesRegex(T.TransplantError, 'PROPOSAL_REJECTED'):
            svc.propose('mirror', bundle(), PRIMS, 'tv')

    def test_consent_required(self):
        svc = service()
        with self.assertRaisesRegex(T.TransplantError, 'CONSENT'):
            run_full(svc, consent=False)
        with self.assertRaisesRegex(T.TransplantError, 'CONSENT'):
            run_full(svc, consent='true')

    def test_full_path_dispatch_verify_report(self):
        svc = service()
        out = run_full(svc)
        self.assertEqual(out['state'], 'active')
        self.assertTrue(out['ui_plan']['plan_hash'].startswith('sha256:'))
        self.assertEqual(out['receipt']['state'], 'dispatched')
        for stage in ('discover_source', 'target_compat', 'route', 'propose',
                      'validate', 'consent', 'compile', 'publish_ui',
                      'dispatch', 'verify'):
            self.assertEqual(out['report'][stage]['status'], 'ok', stage)

    def test_dispatcher_refuses_real_hardware(self):
        d = T.SimulatedDispatcher()
        with self.assertRaisesRegex(T.TransplantError, 'REAL_HARDWARE'):
            d.dispatch({'route_id': 'rt-x', 'simulated': False},
                       {'candidate_id': 'c'})

    def test_revoke_cleans_everything(self):
        svc = service()
        out = run_full(svc)
        tid, sid = out['transplant_id'], out['service_id']
        record = svc._records[tid]
        self.assertEqual(len(svc.dispatcher.receipts), 1)
        revoked = svc.revoke(tid)
        self.assertEqual(revoked['state'], 'revoked')
        self.assertEqual(revoked['ui_plan'], {})
        self.assertEqual(revoked['receipt'], {})
        self.assertEqual(record['service'].list_services(), [])
        with self.assertRaises(Exception):
            record['service'].read(sid)
        self.assertEqual(svc.dispatcher.receipts, {})
        self.assertEqual(revoked['report']['revoke']['status'], 'ok')
        self.assertEqual(revoked['report']['cleanup']['status'], 'ok')
        # idempotent
        self.assertEqual(svc.revoke(tid)['state'], 'revoked')

    def test_revoke_unknown(self):
        with self.assertRaisesRegex(T.TransplantError, 'UNKNOWN_TRANSPLANT'):
            service().revoke('tx-9999')


if __name__ == '__main__':
    unittest.main()
