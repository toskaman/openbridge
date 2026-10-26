import tempfile, unittest
from src.fabric.session import SessionJournal, restore


class FakeAdb:
    def __init__(self):self.calls=[];self.installed=True;self.code=1
    def __call__(self,args):
        self.calls.append(args)
        if args[2:4]==['uninstall','fr.openbridge.companion'] or args[:1]==['-s'] and 'uninstall' in args:self.installed=False;return 'Success'
        if 'list' in args:return 'package:fr.openbridge.companion' if self.installed else ''
        if 'disable-user' in args:self.code=3;return 'Package com.android.bluetooth new state: disabled-user'
        if 'dumpsys' in args:return f'User 0: installed=true enabled={self.code}'
        if args[0]=='disconnect':return 'disconnected'
        raise AssertionError(args)


class SessionTests(unittest.TestCase):
    def test_record_dedup_restore_and_close(self):
        j=SessionJournal(tempfile.mkdtemp()+'/s.json')
        a=j.record('companion_installed','TV',{'serial':'1.2.3.4:5555'},'not installed','installed')
        self.assertEqual(a,j.record('companion_installed','TV',{'serial':'1.2.3.4:5555'},'not installed','installed'))
        j.record('system_package_enabled','TV',{'serial':'s','package':'com.android.bluetooth'},3,1)
        j.record('adb_network_connected','TV',{'address':'1.2.3.4:5555'},'not connected','connected')
        adb=FakeAdb()
        for c in j.open_changes():
            state,_=restore(c,adb);self.assertEqual(state,'RESTORED');j.close(c['id'],state)
        self.assertFalse(adb.installed);self.assertEqual(adb.code,3);self.assertEqual(j.open_changes(),[])

    def test_unknown_kind_and_unsupported_before(self):
        j=SessionJournal(tempfile.mkdtemp()+'/s.json')
        with self.assertRaises(ValueError):j.record('flash_firmware','x',{},0,1)
        self.assertEqual(restore({'kind':'system_package_enabled','target':{'serial':'s','package':'p'},'before':0},FakeAdb())[0],'FAILED')
