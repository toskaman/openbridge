import unittest
from src.fabric.guidance import guide, vendor_of, classify_install


class GuidanceTests(unittest.TestCase):
    def test_vendor_specific_install_steps(self):
        self.assertEqual(vendor_of('Xiaomi'),'xiaomi');self.assertEqual(vendor_of('realme'),'bbk');self.assertEqual(vendor_of('Fairphone'),'generic')
        x=guide('companion_install_blocked','Xiaomi',34,tried=['adb install (USER_RESTRICTED)'])
        self.assertIn('Install via USB',' '.join(x['steps']));self.assertEqual(x['tried'],['adb install (USER_RESTRICTED)'])
        self.assertTrue(all(k in x for k in ('title','why','steps','waiting')))
        self.assertNotIn('Install via USB',' '.join(guide('companion_install_blocked','Google')['steps'][:1]))

    def test_tv_and_android_version_variants(self):
        self.assertIn('Device Preferences',' '.join(guide('usb_debugging_off','Sony',30,television=True)['steps']))
        self.assertIn('Nearby devices',guide('ble_permission','Samsung',33)['why'])
        old=guide('ble_permission','Samsung',29);self.assertIn('Location',old['why']);self.assertIn('Location services',' '.join(old['steps']))

    def test_unknown_issue_and_install_classification(self):
        with self.assertRaises(ValueError):guide('root_device')
        self.assertEqual(classify_install('Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled by user]'),('INSTALL_FAILED_USER_RESTRICTED','companion_install_blocked'))
        self.assertEqual(classify_install('Performing Streamed Install\nSuccess')[0],'SUCCESS')


class ServerGuidanceTests(unittest.TestCase):
    def test_install_retries_with_vendor_guide_then_succeeds(self):
        import tempfile,time
        from pathlib import Path
        from unittest.mock import patch
        from src.server import create_server
        from src.fabric.registry import Registry
        from src.fabric.contracts import DeviceObservation,now
        server=create_server(0,fabric_salt=b's',session_journal=__import__('src.fabric.session',fromlist=['x']).SessionJournal(__import__('tempfile').mkdtemp()+'/s.json'))
        try:
            reg=Registry();k=reg.upsert([],category='phone',observations=[DeviceObservation('manufacturer','Xiaomi','ADB','USB',now(),True),DeviceObservation('sdk','34','ADB','USB',now(),True)])
            reg.devices[k]['handles']={'USB':'h'};server.fabric_registry=reg
            with tempfile.NamedTemporaryFile(suffix='.apk',delete=False) as f:server.companion_apk=Path(f.name)
            outputs=iter(['Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled by user]','Success'])
            with patch.object(server.android,'install_companion',side_effect=lambda h,a:next(outputs)):
                code,_=server.start_companion_install('h',delay=0.3)
                self.assertEqual(code,202);time.sleep(0.15)
                st=server.companion_install;self.assertEqual(st['state'],'RETRYING')
                self.assertEqual(st['guide']['vendor'],'xiaomi');self.assertIn('Install via USB',' '.join(st['guide']['steps']))
                deadline=time.time()+3
                while server.companion_install['state']!='INSTALLED' and time.time()<deadline:time.sleep(0.05)
                self.assertEqual(server.companion_install['state'],'INSTALLED')
            g=server.guide_for_error('Relay refused: Bluetooth is off on this device','h');self.assertEqual(g['issue'],'bluetooth_off')
            self.assertEqual(server.guide_for_error('Relay refused: The system Bluetooth app is disabled on this device','h')['issue'],'bluetooth_service_disabled')
            self.assertEqual(server.guide_for_error('[WinError 10061] connection refused','h')['issue'],'companion_not_running')
        finally:server.server_close()


class TvTests(unittest.TestCase):
    def test_tv_tutorials_by_brand(self):
        nv=guide('tv_network_debugging','NVIDIA',television=True);self.assertIn('Network debugging',' '.join(nv['steps']))
        gg=guide('tv_network_debugging','Google',television=True);self.assertIn('Android TV OS build',' '.join(gg['steps']))
        self.assertIn('Always allow',' '.join(guide('tv_debug_prompt','Sony',television=True)['steps']))

    def test_connect_network_only_private_and_probe_first(self):
        import subprocess
        from unittest.mock import patch
        from src.adapters.android import AndroidAdapter
        a=AndroidAdapter(executable='adb',runner=lambda *x,**k:subprocess.CompletedProcess(x,0,'',''))
        for bad in ('8.8.8.8','127.0.0.1','fe80::1'):
            with self.assertRaises(ValueError):a.connect_network(bad)
        with patch('socket.socket') as socket_factory:
            probe=socket_factory.return_value
            probe.connect_ex.return_value=111
            self.assertEqual(a.connect_network('192.168.255.254',port=1),'PORT_CLOSED')
            probe.connect_ex.assert_called_once_with(('192.168.255.254',1))
            probe.close.assert_called_once_with()

    def test_tv_and_adb_view_merge_on_bluetooth_address(self):
        from src.fabric.discovery import ingest_mdns, ingest_android
        from src.fabric.registry import Registry
        r=Registry()
        ingest_mdns(r,{'instances':[{'service':'_androidtvremote2._tcp','instance':'TV','host':'tv-a.local','port':6466,'addresses':['192.0.2.15'],'txt':{'bt':'00:1A:2B:3C:4D:5E'},'category':'tv'}]},b's')
        class A:
            _handles={'192.0.2.15:5555':'h'}
            def discover(s):return {'devices':[{'id':'h','state':'device','transport':'WIFI','name':'x'}]}
            def stable_identifier(s,h,salt):return 'android_serial:abc'
            def bluetooth_identifier(s,h,salt):
                from src.fabric.contracts import opaque;return opaque('mac_global','00:1a:2b:3c:4d:5e',salt)
            def inspect(s,h):return {'evidence':[{'key':'model','value':'Android TV','observed_at':'t'},{'key':'is_television','value':True,'observed_at':'t'}]}
        ingest_android(r,A(),b's')
        snap=r.snapshot();tvs=[d for d in snap['devices'] if d['category']=='tv']
        self.assertEqual(len(tvs),1);self.assertEqual(sorted(l['transport'] for l in snap['links']),['LAN','WIFI'])
