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
        self.assertFalse(any('setprop' in call or 'install' in call or 'settings' in call for call in calls))

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
