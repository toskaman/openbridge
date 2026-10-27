"""Contract tests: every adapter's graph output yields descriptors satisfying the invariants."""
import unittest
from src.fabric.registry import Registry
from src.fabric.discovery import ingest_mdns, ingest_android, ingest_ble, ingest_ssdp
from src.fabric.freebox_ingest import ingest_freebox
from src.fabric.ble_local import normalize
from src.runtime.capabilities import describe, check_invariants
from tests.fabric.test_freebox_auth import FakeBox, MemVault, TOKEN_NAME
from src.adapters.freebox_auth import FreeboxSession


class FakeAndroid:
    _handles={'S1':'h1','192.168.1.15:5555':'h2'}
    def discover(s):return {'devices':[{'id':'h1','state':'device','transport':'USB','name':'a'},{'id':'h2','state':'device','transport':'WIFI','name':'b'},{'id':'h3','state':'unauthorized','transport':'USB','name':'c'}]}
    def stable_identifier(s,h,salt):return 'android_serial:'+h
    def bluetooth_identifier(s,h,salt):return None
    def inspect(s,h):return {'evidence':[{'key':'model','value':'X','observed_at':'2026-10-27T00:00:00+00:00'},{'key':'bluetooth_le','value':True,'observed_at':'t'},{'key':'is_television','value':h=='h2','observed_at':'t'}]}


class Pub:
    def discover(self):return {'status':'READY','devices':[{'facts':{'api_version':'16.1','device_family':'FreeboxServer7,1','api_base_path':'/api/'}}]}


def full_registry():
    r=Registry()
    ingest_mdns(r,{'instances':[{'service':'_googlecast._tcp','instance':'TV','host':'tv.local','port':8009,'addresses':['192.168.1.15'],'txt':{'id':'c1'},'category':'media'}]},b's')
    ingest_android(r,FakeAndroid(),b's')
    ingest_ble(r,{'devices':[normalize('C1:00:00:00:00:01','Sensor',-70,{},[],{})]},b's')
    ingest_ssdp(r,{'devices':[{'uuid':'uuid:1','ip':'192.168.1.254','location':'x','types':['urn:schemas-upnp-org:device:InternetGatewayDevice:1'],'description':None}]},b's')
    v=MemVault();v.put(TOKEN_NAME,'TOKEN');ingest_freebox(r,{'public':Pub(),'session':FreeboxSession(v,16,transport=FakeBox())},b's')
    return r


class CapabilityContractTests(unittest.TestCase):
    def test_all_adapters_satisfy_invariants(self):
        descs=describe(full_registry().snapshot())
        self.assertGreater(len(descs),10)
        for d in descs:self.assertEqual(check_invariants(d),[],d)

    def test_states_are_not_conflated(self):
        descs={(d.device_key,d.name):d for d in describe(full_registry().snapshot())}
        relay=[d for d in descs.values() if d.name=='ble_relay']
        self.assertTrue(relay and all(not d.controllable for d in relay))      # NOT_SUPPORTED until a Companion is paired
        app=[d for d in descs.values() if d.name=='optional_app_state' and d.verified=='REAL_HARDWARE_VERIFIED']
        self.assertTrue(app and all(d.controllable and d.reversible and d.reversibility=='EXACT' for d in app))
        blocked=[d for d in descs.values() if d.name in ('wifi_settings','upnp_igd_control')]
        self.assertTrue(blocked and all(not d.controllable and not d.operations for d in blocked))
        unauth=[d for d in descs.values() if d.name=='inspect' and d.verified=='BLOCKED']
        self.assertTrue(unauth and all(not d.readable for d in unauth))
        ble=[d for d in descs.values() if d.name=='presence' and not d.readable]
        self.assertTrue(ble)   # observed-only devices (BLE, inventory) are not readable

    def test_relay_controllable_only_with_permission_and_pairing(self):
        r=full_registry();snap=r.snapshot()
        phone=[d for d in snap['devices'] if any(c['name']=='ble_relay' for c in d['capabilities'])][0]
        for c in phone['capabilities']:
            if c['name']=='ble_relay':c['status']='REAL_HARDWARE_VERIFIED'
        d=[x for x in describe(snap,{phone['key']:{'BLUETOOTH_SCAN':False,'owner_enabled':True}}) if x.device_key==phone['key'] and x.name=='ble_relay'][0]
        self.assertFalse(d.controllable)
        d=[x for x in describe(snap,{phone['key']:{'BLUETOOTH_SCAN':True,'owner_enabled':True}}) if x.device_key==phone['key'] and x.name=='ble_relay'][0]
        self.assertTrue(d.controllable and d.reversibility=='SESSION_CLEANUP')
