import subprocess
import tempfile
import unittest
from pathlib import Path
from src.adapters.android import AndroidAdapter
from src.adapters.android_package import AndroidPackageState, DEFAULT, ENABLED, DISABLED, ALLOWED_PACKAGES
from src.core.transactions import TransactionEngine, TransactionBlocked

PKG='org.nixgame.ruler'


class AndroidPackageTests(unittest.TestCase):
    def setUp(self):
        self.calls=[];self.code=0;self.sdk='34';self.user='0';self.state='device';self.fingerprint='build';self.deny=False;self.installed=True
        def run(args,**kwargs):
            self.calls.append(args);tail=args[3:]
            if args[1:]==['devices','-l']:out=f'List of devices attached\nPRIVATE_SERIAL {self.state}\n'
            elif tail==['get-state']:out=self.state
            elif tail==['shell','getprop','ro.build.fingerprint']:out=self.fingerprint
            elif tail==['shell','getprop','ro.build.version.sdk']:out=self.sdk
            elif tail==['shell','am','get-current-user']:out=self.user
            elif tail[:4]==['shell','pm','list','packages'] and tail[-1]==PKG:
                flag=tail[4]
                dis=self.code==3
                show=self.installed and ((flag=='-d' and dis) or (flag=='-e' and not dis))
                out=f'package:{PKG}\n' if show else ''
            elif tail==['shell','dumpsys','package',PKG]:
                out=f'Packages:\n    User 0: ceDataInode=1 installed=true hidden=false\n      notLaunched=false enabled={self.code} instant=false\n    User 999: enabled=0\n' if self.installed else ''
            elif tail==['shell','pm','disable-user','--user','0',PKG]:
                if self.deny:return subprocess.CompletedProcess(args,255,'','java.lang.SecurityException')
                self.code=3;out=f'Package {PKG} new state: disabled-user'
            elif tail==['shell','pm','enable','--user','0',PKG]:
                self.code=1;out=f'Package {PKG} new state: enabled'
            elif tail==['shell','pm','default-state','--user','0',PKG]:
                self.code=0;out=f'Package {PKG} new state: default'
            else:raise AssertionError(f'Unexpected device command {tail}')
            return subprocess.CompletedProcess(args,0,out,'')
        self.adb=AndroidAdapter(executable='adb',runner=run)
        self.handle=self.adb.discover()['devices'][0]['id']

    def adapter(self,pkg=PKG):return AndroidPackageState(self.adb,self.handle,pkg)

    def test_only_allowlisted_optional_packages(self):
        self.assertIn(PKG,ALLOWED_PACKAGES)
        for bad in ('com.android.systemui','com.google.android.gms','android','com.whatsapp','x;reboot'):
            with self.assertRaises(ValueError):self.adapter(bad)

    def test_read_requires_consistent_independent_listings(self):
        a=self.adapter();self.assertEqual(a.read_setting(),DEFAULT)
        self.installed=False
        with self.assertRaises(ValueError):a.read_setting()

    def test_disable_and_enable_use_fixed_user_zero_commands(self):
        a=self.adapter();a.write_setting(DISABLED);self.assertEqual(a.read_setting(),DISABLED)
        a.write_setting(ENABLED);self.assertEqual(a.read_setting(),ENABLED)
        a.write_setting(DEFAULT);self.assertEqual(a.read_setting(),DEFAULT)
        writes=[c[4] for c in self.calls if len(c)>4 and c[3]=='shell' and c[4]=='pm' and c[5] in ('disable-user','enable','default-state')]
        self.assertEqual(len(writes),3)
        self.assertNotIn('PRIVATE_SERIAL',a.identity)

    def test_invalid_value_and_unauthorized_device_block_before_write(self):
        a=self.adapter()
        with self.assertRaises(ValueError):a.write_setting(60)
        self.state='unauthorized'
        with self.assertRaises(ValueError):a.write_setting(DISABLED)
        self.assertFalse(any('disable-user' in c for c in self.calls))

    def test_engine_full_loop_and_denial_preserves_original(self):
        with tempfile.TemporaryDirectory() as d:
            engine=TransactionEngine(Path(d)/'j.sqlite',self.adapter(),allow_physical=True)
            engine.prepare('t1',DISABLED,consent=True)
            self.assertEqual(engine.apply('t1')['state'],'VERIFIED');self.assertEqual(self.code,3)
            self.assertEqual(engine.revert('t1')['state'],'REVERTED');self.assertEqual(self.code,0)
            self.deny=True
            engine.prepare('t2',DISABLED,consent=True)
            with self.assertRaises(TransactionBlocked):engine.apply('t2')
            engine.revert('t2');self.assertEqual(self.code,0)

    def test_exact_default_state_is_restored_not_just_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            engine=TransactionEngine(Path(d)/'j.sqlite',self.adapter(),allow_physical=True)
            engine.prepare('t1',DISABLED,consent=True);engine.apply('t1');engine.revert('t1')
            self.assertEqual(self.code,0)
            self.code=1;engine.prepare('t2',DISABLED,consent=True);engine.apply('t2');engine.revert('t2')
            self.assertEqual(self.code,1)

    def test_other_android_user_blocks_writes(self):
        a=self.adapter();self.user='10'
        with self.assertRaises(ValueError):a.write_setting(DISABLED)
        self.assertEqual(self.code,0)

    def test_pre_android_9_default_state_blocks_before_any_write(self):
        self.sdk='27'
        with tempfile.TemporaryDirectory() as d:
            engine=TransactionEngine(Path(d)/'j.sqlite',self.adapter(),allow_physical=True)
            with self.assertRaises(TransactionBlocked):engine.prepare('t',DISABLED,consent=True)
            self.assertFalse(any('disable-user' in c for c in self.calls))
            self.code=1   # explicitly enabled can be restored with `pm enable`
            engine2=TransactionEngine(Path(d)/'j2.sqlite',self.adapter(),allow_physical=True)
            engine2.prepare('t2',DISABLED,consent=True);engine2.apply('t2');engine2.revert('t2');self.assertEqual(self.code,1)

    def test_wifi_transport_allowed_for_package_writes(self):
        out='List of devices attached\n192.168.1.9:5555 device\n'
        def run(args,**kw):
            if args[1:]==['devices','-l']:return subprocess.CompletedProcess(args,0,out,'')
            return self.adb.runner(args,**kw)
        adb=AndroidAdapter(executable='adb',runner=run);h=adb.discover()['devices'][0]['id']
        a=AndroidPackageState(adb,h,PKG);a.write_setting(DISABLED);self.assertEqual(self.code,3)

    def test_engine_rejects_timeout_targets_for_package_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            engine=TransactionEngine(Path(d)/'j.sqlite',self.adapter(),allow_physical=True)
            with self.assertRaises(TransactionBlocked):engine.prepare('t1',60,consent=True)
