import copy
import unittest
from src.forge.compiler import compile_manifest, ForgeError
from src.forge.fixtures import manifest
from src.forge.service import ForgeService, MemoryProvider
from src.forge.planner import validate_plan, rules_plan

class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000
        self.m=manifest(self.now)
        self.provider=MemoryProvider(self.m)
        self.service=ForgeService(self.provider,clock=lambda:self.now)
    def test_compile_deterministic_and_openapi(self):
        a=compile_manifest(self.m)
        self.assertEqual(a,compile_manifest(copy.deepcopy(self.m)))
        self.assertEqual(a['openapi']['openapi'],'3.1.0')
        self.assertEqual(set(a['openapi']['paths']),{'/v1/services/ble-observations/observations'})
        self.assertNotIn('temperature',a['schemas']['Observation']['properties'])
        compile(a['python_client'],'generated_client','exec')
    def test_manifest_rejects_unsafe_or_unknown_fields(self):
        for key,value in [('version',2),('operation','shell'),('capability_id','../shell'),('verified',False),('status','IMPLEMENTED_UNVERIFIED'),('source','ADB'),('permissions',['control']),('unexpected','url')]:
            with self.subTest(key=key):
                m=copy.deepcopy(self.m); m[key]=value
                with self.assertRaises(ForgeError):compile_manifest(m)
    def test_standalone_schema_references(self):
        try: import jsonschema
        except ImportError: self.skipTest("Optional jsonschema validator is not installed")
        docs=compile_manifest(self.m)
        response={key:self.m[key] for key in ('service_id','device_id','relay_id','source','simulation','observed_at','evidence_refs','observations')}
        jsonschema.Draft202012Validator(docs['schemas']['ObservationResponse']).validate(response)
    def test_nested_malformed_permissions_are_rejected_cleanly(self):
        self.m['permissions']=[{}]
        with self.assertRaises(ForgeError):compile_manifest(self.m)
    def test_consent_is_required_and_exact(self):
        with self.assertRaises(ForgeError):self.service.publish(self.m,consent=False)
        with self.assertRaises(ForgeError):self.service.publish(self.m,consent='true')
    def test_publish_read_delete_revokes(self):
        sid=self.service.publish(self.m,consent=True)['service_id']
        self.assertEqual(self.service.read(sid)['observations'][0]['rssi_dbm'],-62)
        self.service.remove(sid)
        with self.assertRaises(ForgeError):self.service.read(sid)
        self.assertEqual(self.service.list_services(),[])
    def test_live_permission_revocation_and_expiry(self):
        sid=self.service.publish(self.m,consent=True)['service_id']
        for key,value in [('permissions',[]),('available',False),('identity_conflict',True),('device_present',False),('verified',False),('observed_at',self.now-301),('source','BLE')]:
            with self.subTest(key=key):
                self.provider.current=copy.deepcopy(self.m); self.provider.current[key]=value
                with self.assertRaises(ForgeError):self.service.read(sid)
    def test_forged_caller_manifest_not_trusted(self):
        self.provider.current['available']=False
        with self.assertRaises(ForgeError):self.service.publish(self.m,consent=True)
    def test_missing_data_rejected(self):
        self.m['observations']=[{'observation_id':'obs-1','name':'Beacon'}]
        with self.assertRaises(ForgeError):compile_manifest(self.m)
    def test_plans_require_exact_refs_and_transitions(self):
        plan=rules_plan([self.m],self.now)
        self.assertEqual(validate_plan(plan,[self.m],self.now)['decision'],'propose')
        for change in ('unknown','reverse','consent','evidence','extra'):
            p=copy.deepcopy(plan)
            if change=='unknown':p['steps'][0]['capability_id']='invented'
            elif change=='reverse':p['steps'].reverse()
            elif change=='consent':p['requires_consent']=False
            elif change=='evidence':p['evidence_refs']=['invented']
            else:p['command']='adb shell'
            with self.subTest(change=change),self.assertRaises(ForgeError):validate_plan(p,[self.m],self.now)
    def test_impossible_plan_refuses(self):
        self.m['available']=False
        self.assertEqual(rules_plan([self.m],self.now)['decision'],'unavailable')
    def test_concurrent_publish_has_one_service(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids=list(pool.map(lambda _:self.service.publish(self.m,consent=True)['service_id'],range(20)))
        self.assertEqual(len(set(ids)),1)
        self.assertEqual(len(self.service.list_services()),1)

if __name__=='__main__':unittest.main()
