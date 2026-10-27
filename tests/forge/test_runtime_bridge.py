"""Contract v1 bridge fixtures: never claims actual runtime hardware evidence."""
import copy
from datetime import datetime,timezone
import unittest
from src.forge.runtime_bridge import RuntimeV1Provider
from src.forge.compiler import ForgeError

class RuntimeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000;ts=datetime.fromtimestamp(self.now,timezone.utc).isoformat();self.paths=[]
        self.data={
          '/api/v2/contract':{'version':'1.0.0'},
          '/api/v2/graph':{'devices':[{'device_key':'dev:tv','possibly_same_as':[]},{'device_key':'dev:beacon','possibly_same_as':[]}],'links':[{'parent':'dev:tv','child':'dev:beacon','transport':'BLE','source':'RELAY:relay-1','grants':['observe']}]},
          '/api/v2/capabilities':{'capabilities':[{'capability_id':'dev:tv:ble_relay','device_key':'dev:tv','name':'ble_relay','discovered':True,'observed':True,'readable':True,'verified':'SIMULATED_VERIFIED','permissions':[{'name':'android.permission.BLUETOOTH_SCAN','granted':True},{'name':'pairing','granted':True}],'operations':['relay_ble_scan','relay_revoke'],'source':'RELAY:relay-1'}]},
          '/api/v2/routes':{'routes':[{'target_device':'*','relay_device':'dev:tv','relay_id':'relay-1','radio':'ble','permission_granted':True,'owner_enabled':True,'online':True}]},
          '/api/v2/facts?device=dev%3Abeacon&source=RELAY%3Arelay-1':{'device':'dev:beacon','facts':[{'device_key':'dev:beacon','name':'ble_rssi','value':-61,'sources':['RELAY:relay-1'],'observed_at':ts,'verified':True,'inferred':False}]}}
        def read(path):self.paths.append(path);return copy.deepcopy(self.data[path])
        self.provider=RuntimeV1Provider(read,'dev:tv:ble_relay','dev:beacon','relay-1',allow_simulated=True,clock=lambda:self.now)
    def test_contract_mapping_handles_colon_ids_and_additive_fields(self):
        self.data['/api/v2/capabilities']['capabilities'][0]['future_field']='ignored'
        m=self.provider.snapshot(self.provider.capability_id)
        self.assertTrue(m['simulation']);self.assertEqual(m['observations'][0]['rssi_dbm'],-61)
        self.assertTrue(all(p.startswith('/api/v2/') for p in self.paths));self.assertFalse(any('/execute' in p for p in self.paths))
    def test_unknown_grant_source_identity_and_fact_are_blocked(self):
        for kind in ('permission','source','identity','missing','inferred','stale','major','offline'):
            with self.subTest(kind=kind):
                original=copy.deepcopy(self.data)
                if kind=='permission':self.data['/api/v2/routes']['routes'][0]['owner_enabled']=False
                if kind=='source':self.data['/api/v2/facts?device=dev%3Abeacon&source=RELAY%3Arelay-1']['facts'][0]['sources']=['ADB','RELAY:relay-1']
                if kind=='identity':self.data['/api/v2/graph']['devices'][1]['possibly_same_as']=['other']
                if kind=='missing':self.data['/api/v2/facts?device=dev%3Abeacon&source=RELAY%3Arelay-1']['facts']=[]
                if kind=='inferred':self.data['/api/v2/facts?device=dev%3Abeacon&source=RELAY%3Arelay-1']['facts'][0]['inferred']=True
                if kind=='stale':self.data['/api/v2/facts?device=dev%3Abeacon&source=RELAY%3Arelay-1']['facts'][0]['observed_at']='2000-01-01T00:00:00+00:00'
                if kind=='major':self.data['/api/v2/contract']['version']='2.0.0'
                if kind=='offline':self.data['/api/v2/routes']['routes'][0]['online']=False
                with self.assertRaises(ForgeError):self.provider.snapshot(self.provider.capability_id)
                self.data=original
    def test_simulated_status_requires_explicit_bridge_option(self):
        self.provider.allow_simulated=False
        with self.assertRaises(ForgeError):self.provider.snapshot(self.provider.capability_id)
    def test_bound_source_query_avoids_other_relay_aggregate(self):
        unfiltered='/api/v2/facts?device=dev%3Abeacon'
        selected=unfiltered+'&source=RELAY%3Arelay-1'
        self.data[unfiltered]=copy.deepcopy(self.data[selected])
        self.data[unfiltered]['facts'][0].update(value=-20,sources=['RELAY:relay-1','RELAY:other'])
        result=self.provider.snapshot(self.provider.capability_id)
        self.assertEqual(result['observations'][0]['rssi_dbm'],-61)
        self.assertIn(selected,self.paths)
        self.assertNotIn(unfiltered,self.paths)
    def test_selected_stale_fact_is_not_replaced_by_fresh_aggregate(self):
        selected='/api/v2/facts?device=dev%3Abeacon&source=RELAY%3Arelay-1'
        self.data['/api/v2/facts?device=dev%3Abeacon']=copy.deepcopy(self.data[selected])
        self.data[selected]['facts'][0]['observed_at']='2000-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ForgeError,'OBSERVATION_EXPIRED'):
            self.provider.snapshot(self.provider.capability_id)
    def test_unsupported_source_filter_never_falls_back(self):
        selected='/api/v2/facts?device=dev%3Abeacon&source=RELAY%3Arelay-1'
        self.data['/api/v2/facts?device=dev%3Abeacon']=self.data.pop(selected)
        with self.assertRaisesRegex(ForgeError,'RUNTIME_SNAPSHOT_UNAVAILABLE'):
            self.provider.snapshot(self.provider.capability_id)
        self.assertNotIn('/api/v2/facts?device=dev%3Abeacon',self.paths)
