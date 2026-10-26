import subprocess
import unittest
from src.adapters.android import AndroidAdapter
from src.adapters.android_timeout import AndroidTimeoutSetting


class AndroidTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.value=30000;self.state='device';self.fingerprint='example-build';self.deny=False
        def run(args,**kwargs):
            self.calls.append(args)
            if args[1:]==['devices','-l']:
                output=f'List of devices attached\nPRIVATE_SERIAL {self.state}\n'
            elif args[3:]==['get-state']: output=self.state
            elif args[3:]==['shell','getprop','ro.build.fingerprint']: output=self.fingerprint
            elif args[3:]==['shell','settings','get','system','screen_off_timeout']: output=str(self.value)
            elif args[3:7]==['shell','settings','put','system']:
                if self.deny:return subprocess.CompletedProcess(args,1,'','permission denied')
                self.value=int(args[-1]);output=''
            else: raise AssertionError('Unexpected device command')
            return subprocess.CompletedProcess(args,0,output,'')
        self.adb=AndroidAdapter(executable='adb',runner=run)
        self.handle=self.adb.discover()['devices'][0]['id']

    def test_exact_read_and_fixed_setting_write(self):
        setting=AndroidTimeoutSetting(self.adb,self.handle)
        self.assertEqual(setting.read_setting(),30)
        setting.write_setting(60)
        self.assertEqual(setting.read_setting(),60)
        writes=[c for c in self.calls if 'put' in c]
        self.assertEqual(writes[0][3:],['shell','settings','put','system','screen_off_timeout','60000'])
        self.assertNotIn('PRIVATE_SERIAL',setting.identity)

    def test_unauthorized_device_blocks_before_write(self):
        setting=AndroidTimeoutSetting(self.adb,self.handle);self.state='unauthorized'
        with self.assertRaises(ValueError):setting.write_setting(60)
        self.assertFalse(any('put' in c for c in self.calls))

    def test_changed_build_identity_blocks_before_write(self):
        setting=AndroidTimeoutSetting(self.adb,self.handle);self.fingerprint='different-build'
        with self.assertRaises(ValueError):setting.write_setting(60)
        self.assertFalse(any('put' in c for c in self.calls))

    def test_precision_loss_or_invalid_values_are_rejected(self):
        setting=AndroidTimeoutSetting(self.adb,self.handle);self.value=15500
        with self.assertRaises(ValueError):setting.read_setting()
        for value in (True,0,-1,86401,'60'):
            with self.assertRaises(ValueError):setting.write_setting(value)
        self.assertFalse(any('put' in c for c in self.calls))

    def test_permission_denial_is_not_treated_as_success(self):
        setting=AndroidTimeoutSetting(self.adb,self.handle);self.deny=True
        with self.assertRaises(ValueError):setting.write_setting(60)
        self.assertEqual(self.value,30000)
