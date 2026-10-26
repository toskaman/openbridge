import unittest
from src.fabric import ble_local
from src.fabric.discovery import run, ingest_ble
from src.fabric.registry import Registry


class BleTests(unittest.TestCase):
    def test_address_kinds(self):
        self.assertEqual(ble_local.address_kind('C1:22:33:44:55:66'),'static_random')
        self.assertEqual(ble_local.address_kind('4A:22:33:44:55:66'),'resolvable_private')
        self.assertEqual(ble_local.address_kind('zz'),'unknown')

    def test_scan_is_bounded_and_errors_are_statuses(self):
        async def ok():return [ble_local.normalize('C1:22:33:44:55:66','Thermo',-60,{76:b'x'},['0000181a-0000-1000-8000-00805f9b34fb'],{})]
        r=ble_local.scan(99,scanner=ok);self.assertEqual((r['status'],r['seconds']),('OK',ble_local.MAX_SECONDS))
        async def boom():raise OSError('radio off')
        self.assertEqual(ble_local.scan(1,scanner=boom)['status'],'BLE_UNAVAILABLE')

    def test_ble_devices_observe_only_and_private_addresses_not_merged(self):
        r=Registry()
        devs=[ble_local.normalize('4A:22:33:44:55:66','Watch',-70,{},[],{}),ble_local.normalize('C1:22:33:44:55:66','Thermo',-60,{76:b''},[],{})]
        ingest_ble(r,{'devices':devs},b's');ingest_ble(r,{'devices':devs[1:]},b's')
        snap=r.snapshot();self.assertEqual(len(snap['devices']),2)   # static address merged across scans
        self.assertTrue(all(l['grants']==['observe'] for l in snap['links']))
        self.assertNotIn('C1:22:33',str(snap))

    def test_discovery_run_combines_providers(self):
        fake_mdns=lambda t:{'status':'OK','packets':1,'instances':[{'service':'_googlecast._tcp','instance':'TV','host':'tv.local','port':8009,'addresses':['192.168.1.40'],'txt':{'id':'abc','fn':'Salon'},'category':'media'}]}
        async def none():return []
        snap,_=run({'ble_scan':lambda:ble_local.scan(1,scanner=none)},b's',providers=('mdns','ble'),mdns_fn=fake_mdns)
        self.assertEqual(snap['providers']['mdns']['instances'],1);self.assertEqual(snap['providers']['ble']['status'],'OK')
        self.assertEqual(snap['devices'][0]['label'],'Salon')
