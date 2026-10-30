import subprocess
import unittest
from unittest.mock import patch
from src.adapters.android import AndroidAdapter


class AndroidTests(unittest.TestCase):
    def adapter(self, output):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if args[1:] == ['devices', '-l']:
                return subprocess.CompletedProcess(args, 0, output, '')
            command = tuple(args[3:])
            values = {
                ('get-state',): 'device',
                ('shell', 'getprop', 'ro.product.manufacturer'): 'Google',
                ('shell', 'getprop', 'ro.product.model'): 'Pixel 8',
                ('shell', 'getprop', 'ro.build.version.release'): '15',
                ('shell', 'getprop', 'ro.build.version.sdk'): '35',
                ('shell', 'dumpsys', 'battery'): 'level: 80\nscale: 100\n',
                ('shell', 'df', '-k', '/data'): 'Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/data 10000 4000 6000 40% /data',
            }
            return subprocess.CompletedProcess(args, 0, values.get(command, ''), '')
        return AndroidAdapter(executable='adb', runner=run), calls

    def test_multiple_states_and_no_serial_exposed(self):
        adapter, _ = self.adapter('List of devices attached\nSECRET123 device product:a model:Pixel_8\nSECRET456 unauthorized\nemulator-5554 offline\n')
        result = adapter.discover()
        self.assertEqual([x['state'] for x in result['devices']], ['device', 'unauthorized', 'offline'])
        self.assertNotIn('SECRET', str(result))
        self.assertNotIn('emulator-5554', str(result))
        self.assertFalse(result['devices'][0]['simulated'])

    def test_authorized_inspection_uses_only_fixed_commands(self):
        adapter, calls = self.adapter('List of devices attached\nSERIAL device\n')
        device = adapter.discover()['devices'][0]
        report = adapter.inspect(device['id'])
        self.assertFalse(report['simulated'])
        self.assertEqual(report['source'], 'ADB')
        self.assertEqual(next(x['value'] for x in report['evidence'] if x['key'] == 'battery_percent'), 80)
        self.assertNotIn('SERIAL', str(report))
        reads={('getprop',),('dumpsys','battery'),('df','-k','/data'),('df','/data'),('settings','get'),('cat','/proc/meminfo'),('pm','list','features')}
        for call in calls:
            if 'shell' in call:
                shell=tuple(call[call.index('shell')+1:])
                self.assertTrue(any(shell[:len(r)]==r for r in reads),shell)

    def test_unauthorized_and_unknown_handles_do_not_execute_shell(self):
        adapter, calls = self.adapter('List of devices attached\nSERIAL unauthorized\n')
        handle = adapter.discover()['devices'][0]['id']
        for value in (handle, 'SERIAL; reboot'):
            with self.assertRaises(ValueError):
                adapter.inspect(value)
        self.assertFalse(any('shell' in call for call in calls))

    def test_missing_adb_is_honest_status(self):
        with patch('src.adapters.android.shutil.which', return_value=None):
            self.assertEqual(AndroidAdapter().discover()['status'], 'ADB_MISSING')

    def test_timeout_does_not_leak_details(self):
        def run(args, **kwargs):
            raise subprocess.TimeoutExpired(['adb', '-s', 'PRIVATE_SERIAL'], 8)
        result = AndroidAdapter(executable='adb', runner=run).discover()
        self.assertEqual(result['status'], 'ADB_UNAVAILABLE')
        self.assertNotIn('PRIVATE', str(result))


class AndroidCompatibilityTests(unittest.TestCase):
    def adapter(self,devices,values):
        def run(args,**kwargs):
            if args[1:]==['devices','-l']:return subprocess.CompletedProcess(args,0,devices,'')
            if args[3:]==['get-state']:return subprocess.CompletedProcess(args,0,'device','')
            v=values.get(tuple(args[4:]))
            if v is None:return subprocess.CompletedProcess(args,1,'','error')
            return subprocess.CompletedProcess(args,0,v,'')
        return AndroidAdapter(executable='adb',runner=run)

    def test_wifi_and_mdns_tls_serials_are_wifi_not_usb(self):
        from src.adapters.android import transport_of
        self.assertEqual(transport_of('192.168.1.20:5555'),'WIFI')
        self.assertEqual(transport_of('adb-R5CT1234-AbCdEf._adb-tls-connect._tcp'),'WIFI')
        self.assertEqual(transport_of('emulator-5554'),'EMULATOR')
        self.assertEqual(transport_of('R5CT1234'),'USB')
        a=self.adapter('List of devices attached\n192.168.1.20:5555 device\nadb-X-Y._adb-tls-connect._tcp device\n',{})
        self.assertEqual([d['transport'] for d in a.discover()['devices']],['WIFI','WIFI'])

    def test_df_formats(self):
        from src.adapters.android import parse_df_available_kb as p
        self.assertEqual(p('Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-5 10000 4000 6000 40% /data'),6000)
        self.assertEqual(p('Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/bootdevice/by-name/userdata\n 10000 4000 6000 40% /data'),6000)
        self.assertEqual(p('Filesystem Size Used Free Blksize\n/data 12.5G 3.1G 9.4G 4096'),round(9.4*1024**2))
        self.assertIsNone(p('Filesystem Size\n/system 1G'))
        # Real Xiaomi output: /data reported under a bind-mount point
        self.assertEqual(p('Filesystem       1K-blocks     Used Available Use% Mounted on\n/dev/block/dm-50 235075564 73331000 161613492  32% /storage/emulated/0/Android/obb'),161613492)

    def test_missing_facts_do_not_abort_and_tv_is_detected(self):
        a=self.adapter('List of devices attached\nTV1 device\n',{('getprop','ro.product.manufacturer'):'Sony',('getprop','ro.product.model'):'BRAVIA',
            ('dumpsys','battery'):'present: false\nlevel: 0\nscale: 100',('pm','list','features'):'feature:android.software.leanback\nfeature:android.hardware.bluetooth_le\nfeature:reqGlEsVersion=0x30002',('cat','/proc/meminfo'):'MemTotal:        2048000 kB'})
        r=a.inspect(a.discover()['devices'][0]['id'])
        facts={e['key']:e['value'] for e in r['evidence']}
        self.assertEqual(facts['manufacturer'],'Sony');self.assertTrue(facts['is_television']);self.assertTrue(facts['bluetooth_le'])
        self.assertNotIn('battery_percent',facts)
        self.assertIn('battery_percent',r['unavailable']);self.assertIn('android_version',r['unavailable'])
        self.assertEqual(facts['ram_total_gb'],2.0)


class AndroidTransferTests(unittest.TestCase):
    def adapter(self, handler):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return handler(args, kwargs)
        a = AndroidAdapter(executable='adb', runner=run)
        a._handles['SERIAL1'] = 'h-1'
        return a, calls

    def test_pull_returns_bytes_with_fixed_argv(self):
        def h(args, kw):
            if args[3:] == ['exec-out', 'cat', '/sdcard/Download/a.bin']:
                return subprocess.CompletedProcess(args, 0, b'\x00\x01\x02', b'')
            return subprocess.CompletedProcess(args, 1, b'', b'nope')
        a, calls = self.adapter(h)
        self.assertEqual(a.pull_file('h-1', '/sdcard/Download/a.bin'), b'\x00\x01\x02')
        self.assertEqual(calls[-1][:4], ['adb', '-s', 'SERIAL1', 'exec-out'])

    def test_pull_rejects_unknown_handle_without_exec(self):
        a, calls = self.adapter(lambda args, kw: subprocess.CompletedProcess(args, 0, b'', b''))
        with self.assertRaises(ValueError):
            a.pull_file('h-ghost', '/sdcard/Download/a.bin')
        self.assertEqual(calls, [])

    def test_pull_rejects_paths_outside_allowlist(self):
        a, calls = self.adapter(lambda args, kw: subprocess.CompletedProcess(args, 0, b'', b''))
        for bad in ('/data/data/x', '/sdcard/../etc/passwd', 'relative/path',
                    '/sdcard/a;b', '/sdcard/a b', '/etc/hosts', ''):
            with self.assertRaises(ValueError, msg=bad):
                a.pull_file('h-1', bad)
        self.assertEqual(calls, [])

    def test_pull_rejects_oversize(self):
        def h(args, kw):
            return subprocess.CompletedProcess(args, 0, b'x' * 100, b'')
        a, _ = self.adapter(h)
        with self.assertRaises(ValueError):
            a.pull_file('h-1', '/sdcard/Download/a.bin', max_bytes=10)

    def test_push_writes_temp_then_pushes_to_openbridge_dir(self):
        seen = {}
        def h(args, kw):
            if args[3] == 'push':
                seen['local'] = args[4]
                with open(args[4], 'rb') as f:
                    seen['data'] = f.read()
                return subprocess.CompletedProcess(args, 0, '1 file pushed', '')
            return subprocess.CompletedProcess(args, 1, '', 'nope')
        a, calls = self.adapter(h)
        remote = a.push_file('h-1', b'\x89PNG', 'cap-1.png')
        self.assertEqual(remote, '/sdcard/OpenBridge/cap-1.png')
        self.assertEqual(seen['data'], b'\x89PNG')
        import os
        self.assertFalse(os.path.exists(seen['local']))
        self.assertEqual(calls[-1][3:], ['push', seen['local'], '/sdcard/OpenBridge/cap-1.png'])

    def test_push_rejects_bad_names_and_handles(self):
        a, calls = self.adapter(lambda args, kw: subprocess.CompletedProcess(args, 0, '', ''))
        for bad in ('../x.png', 'a/b.png', '', 'x' * 200, 'a;b.png'):
            with self.assertRaises(ValueError, msg=bad):
                a.push_file('h-1', b'data', bad)
        with self.assertRaises(ValueError):
            a.push_file('h-ghost', b'data', 'a.png')
        self.assertEqual(calls, [])

    def test_file_sha256_parses_hash(self):
        digest = 'a' * 64
        def h(args, kw):
            if args[4:6] == ['sha256sum', '/sdcard/OpenBridge/cap-1.png']:
                return subprocess.CompletedProcess(args, 0, f'{digest}  /sdcard/OpenBridge/cap-1.png\n', '')
            return subprocess.CompletedProcess(args, 1, '', 'nope')
        a, _ = self.adapter(h)
        self.assertEqual(a.file_sha256('h-1', '/sdcard/OpenBridge/cap-1.png'), digest)

    def test_file_sha256_rejects_unparsable(self):
        a, _ = self.adapter(lambda args, kw: subprocess.CompletedProcess(args, 0, 'garbage\n', ''))
        with self.assertRaises(ValueError):
            a.file_sha256('h-1', '/sdcard/OpenBridge/cap-1.png')
