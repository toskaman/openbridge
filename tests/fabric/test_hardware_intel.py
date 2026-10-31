"""§9 hardware intelligence: measurements, task rankers, benchmark offers."""
import tempfile
import unittest

from src.fabric import hardware_intel as H


def M(name, value, unit='x', source='TEST', confidence='measured'):
    return H.metric(name, value, unit, source, confidence)


WIFI_ON = 'mWifiInfo SSID: "Home", BSSID: aa:bb, freq=2412, rssi=-55\nSupplicant state: COMPLETED'

PC_A = {'key': 'pc-a', 'category': 'pc', 'label': 'Main PC',
        'metrics': {'cpu_threads': M('cpu_threads', 16), 'ram_gb': M('ram_gb', 32, 'GB'),
                    'gpu_vram_gb': M('gpu_vram_gb', 16, 'GB'), 'gpu_name': M('gpu_name', 'RTX 4060 Ti'),
                    'disk_free_gb': M('disk_free_gb', 120, 'GB'), 'os': M('os', 'Windows 10')}}
PC_B = {'key': 'pc-b', 'category': 'pc', 'label': 'Old laptop',
        'metrics': {'cpu_threads': M('cpu_threads', 4), 'ram_gb': M('ram_gb', 8, 'GB'),
                    'gpu_vram_gb': M('gpu_vram_gb', 0, 'GB'), 'gpu_name': M('gpu_name', 'Intel iGPU'),
                    'disk_free_gb': M('disk_free_gb', 40, 'GB'), 'os': M('os', 'Windows 11')}}
PHONE = {'key': 'ph', 'category': 'phone', 'label': 'Phone',
         'metrics': {'battery_percent': M('battery_percent', 72, '%'),
                     'battery_charging': M('battery_charging', False, 'bool'),
                     'wifi_band': M('wifi_band', '5GHz'), 'ble': M('ble', True, 'bool')}}


class Metrics(unittest.TestCase):
    def test_metric_shape(self):
        m = M('ram_gb', 32, 'GB', 'ADB')
        self.assertEqual((m['name'], m['value'], m['unit'], m['source'], m['confidence'],
                          m['availability']),
                         ('ram_gb', 32, 'GB', 'ADB', 'measured', 'available'))
        self.assertIn('observed_at', m)

    def test_band_from_mhz(self):
        self.assertEqual(H.band_from_mhz(2412), '2.4GHz')
        self.assertEqual(H.band_from_mhz(2472), '2.4GHz')
        self.assertEqual(H.band_from_mhz(5180), '5GHz')
        self.assertEqual(H.band_from_mhz(5745), '5GHz')
        self.assertEqual(H.band_from_mhz(6255), '6GHz')
        self.assertEqual(H.band_from_mhz(0), 'unknown')
        self.assertEqual(H.band_from_mhz(None), 'unknown')

    def test_parse_wifi_freq(self):
        self.assertEqual(H.parse_wifi_freq('mWifiInfo SSID: x, BSSID: y, freq=5180'), 5180)
        self.assertIsNone(H.parse_wifi_freq('Wifi is disabled'))
        self.assertIsNone(H.parse_wifi_freq(''))

    def test_parse_battery_extra(self):
        text = ('level: 72\nscale: 100\npresent: true\nstatus: 2\nplugged: 1\n'
                'technology: Li-ion\nMax charging current: 1500000\n')
        self.assertEqual(H.parse_battery_extra(text), {'charging': True, 'plugged': 'ac',
                                                       'capacity_mah': None})
        self.assertEqual(H.parse_battery_extra('level: 5\nstatus: 3\nplugged: 0\n'),
                         {'charging': False, 'plugged': 'none', 'capacity_mah': None})
        self.assertEqual(H.parse_battery_extra('garbage'), {'charging': False, 'plugged': 'unknown',
                                                            'capacity_mah': None})

    def test_parse_cpu_mem(self):
        cpu = 'processor\t: 0\nprocessor\t: 1\nprocessor\t: 2\nHardware\t: qcom\n'
        self.assertEqual(H.parse_cpu_count(cpu), 3)
        self.assertIsNone(H.parse_cpu_count(''))
        self.assertAlmostEqual(H.parse_mem_total_gb('MemTotal:        5944568 kB\n'), 5.7, delta=0.1)
        self.assertIsNone(H.parse_mem_total_gb('nope'))

    def test_parse_nvidia_smi(self):
        text = 'name, memory.total [MiB]\nNVIDIA GeForce RTX 4060 Ti, 16380 MiB\n'
        self.assertEqual(H.parse_nvidia_smi(text), {'gpu_name': 'NVIDIA GeForce RTX 4060 Ti',
                                                    'gpu_vram_gb': 16.0})
        self.assertIsNone(H.parse_nvidia_smi('garbage'))
        self.assertIsNone(H.parse_nvidia_smi(''))


class Collectors(unittest.TestCase):
    def test_android_collect_with_fake_runner(self):
        def run(*args):
            cmd = ' '.join(args)
            if 'dumpsys wifi' in cmd or 'cmd wifi status' in cmd:
                return WIFI_ON
            if 'dumpsys battery' in cmd:
                return 'level: 72\nscale: 100\npresent: true\nstatus: 2\nplugged: 1\n'
            if 'cpuinfo' in cmd:
                return 'processor\t: 0\nprocessor\t: 1\n'
            if 'meminfo' in cmd:
                return 'MemTotal:        5944568 kB\n'
            if 'SurfaceFlinger' in cmd:
                return 'GLES: Qualcomm, Adreno (TM) 660\nVulkan: 1.1\n'
            if 'telephony.registry' in cmd:
                return 'mServiceState={mVoiceRegState=0, mDataRegState=0}'
            raise OSError('unknown: ' + cmd)
        facts = H.android_facts(run)
        by_name = {m['name']: m for m in facts}
        self.assertEqual(by_name['wifi_band']['value'], '2.4GHz')
        self.assertTrue(by_name['battery_charging']['value'])
        self.assertEqual(by_name['cpu_count']['value'], 2)
        self.assertEqual(by_name['gpu']['value'], 'Adreno (TM) 660')
        self.assertEqual(by_name['cellular']['value'], 'present')
        self.assertTrue(all(m['source'] == 'ADB' for m in facts))
        self.assertTrue(all(m['confidence'] in ('measured', 'reported') for m in facts))

    def test_android_collect_degrades_on_failures(self):
        def run(*args):
            raise OSError('adb down')
        self.assertEqual(H.android_facts(run), [])

    def test_pc_facts_smoke(self):
        def run(*args):
            raise OSError('no gpu tool')
        facts = H.pc_facts(run=run)
        by_name = {m['name']: m for m in facts}
        self.assertGreaterEqual(by_name['cpu_threads']['value'], 1)
        self.assertGreater(by_name['ram_gb']['value'], 0)
        self.assertTrue(by_name['os']['value'])
        self.assertNotIn('gpu_name', by_name)

    def test_pc_facts_ram_via_sysctl_when_no_win32_or_proc(self):
        import builtins
        import subprocess
        from types import SimpleNamespace
        from unittest import mock
        real_open = builtins.open

        def no_proc(path, *args, **kwargs):
            if str(path) == '/proc/meminfo':
                raise OSError('no proc (macOS)')
            return real_open(path, *args, **kwargs)

        def fake_sysctl(*args, **kwargs):
            assert args[0] == ['sysctl', '-n', 'hw.memsize']
            return SimpleNamespace(stdout='17179869184\n')

        with mock.patch('ctypes.windll', create=True) as windll, \
                mock.patch.object(builtins, 'open', no_proc), \
                mock.patch.object(subprocess, 'run', fake_sysctl):
            windll.kernel32.GlobalMemoryStatusEx.side_effect = AttributeError('no win32')
            facts = H.pc_facts(run=lambda *a: (_ for _ in ()).throw(OSError('no gpu tool')))
        by_name = {m['name']: m for m in facts}
        self.assertEqual(by_name['ram_gb']['value'], 16.0)


class Rankers(unittest.TestCase):
    def test_rank_minecraft_orders_and_explains(self):
        r = H.rank('minecraft', [PC_A, PC_B])
        self.assertEqual([x['key'] for x in r['ranking']], ['pc-a', 'pc-b'])
        top = r['ranking'][0]
        self.assertGreater(top['score'], r['ranking'][1]['score'])
        self.assertTrue(top['reasons'] and top['evidence'])
        self.assertIn(top['confidence'], ('high', 'medium'))

    def test_rank_ai_suggests_model_class(self):
        r = H.rank('ai_model', [PC_A, PC_B])
        self.assertEqual(r['ranking'][0]['key'], 'pc-a')
        self.assertIn('30B', ' '.join(r['ranking'][0]['reasons']))

    def test_rank_uses_android_gpu_name(self):
        phone = {'key': 'ph', 'category': 'phone', 'label': 'Phone',
                 'metrics': {'gpu': M('gpu', 'Mali-G57'), 'ram_gb': M('ram_gb', 12, 'GB')}}
        r = H.rank('ai_model', [phone])
        self.assertIn('Mali-G57', ' '.join(r['ranking'][0]['reasons']))

    def test_rank_dev_prefers_ram_and_cpu(self):
        r = H.rank('dev', [PC_A, PC_B])
        self.assertEqual([x['key'] for x in r['ranking']], ['pc-a', 'pc-b'])

    def test_rank_recharge_excludes_unknown(self):
        full = {'key': 'full', 'category': 'phone', 'label': 'Full',
                'metrics': {'battery_percent': M('battery_percent', 95, '%'),
                            'battery_charging': M('battery_charging', True, 'bool')}}
        low = {'key': 'low', 'category': 'phone', 'label': 'Low',
               'metrics': {'battery_percent': M('battery_percent', 12, '%'),
                           'battery_charging': M('battery_charging', False, 'bool')}}
        unknown = {'key': 'myst', 'category': 'phone', 'label': 'Myst', 'metrics': {}}
        r = H.rank('recharge_first', [full, low, unknown])
        self.assertEqual([x['key'] for x in r['ranking']], ['low', 'full'])
        self.assertTrue(any('myst' in n for n in r['notes']))

    def test_rank_weekend_distinguishes_nominal_vs_remaining(self):
        big = {'key': 'big', 'category': 'phone', 'label': 'Big',
               'metrics': {'battery_percent': M('battery_percent', 50, '%'),
                           'battery_capacity_mah': M('battery_capacity_mah', 10000, 'mAh')}}
        small = {'key': 'small', 'category': 'phone', 'label': 'Small',
                 'metrics': {'battery_percent': M('battery_percent', 90, '%'),
                             'battery_capacity_mah': M('battery_capacity_mah', 3000, 'mAh')}}
        r = H.rank('weekend_phone', [small, big])
        self.assertEqual(r['ranking'][0]['key'], 'big')
        self.assertTrue(any('remaining' in x.lower() for x in r['ranking'][0]['reasons']))

    def test_rank_wifi_reports_bands_and_cellular(self):
        r = H.rank('wifi_bands', [PHONE])
        row = r['ranking'][0]
        self.assertIsNone(row['score'])
        self.assertTrue(any('5GHz' in x for x in row['reasons']))

    def test_rank_bt_relay_uses_relay_state(self):
        relays = {'ph': {'paired': True, 'fresh_s': 30}}
        r = H.rank('bt_relay', [PHONE], relays=relays)
        self.assertGreater(r['ranking'][0]['score'], 0)
        r2 = H.rank('bt_relay', [PHONE], relays={})
        self.assertLess(r2['ranking'][0]['score'], r['ranking'][0]['score'])

    def test_missing_metrics_lower_confidence_and_offer_bench(self):
        thin = {'key': 'thin', 'category': 'pc', 'label': 'Thin', 'metrics': {}}
        r = H.rank('minecraft', [thin])
        self.assertEqual(r['ranking'][0]['confidence'], 'low')
        self.assertIn(r['benchmark_offer']['kind'], ('cpu_loop', 'inference_latency', 'device_rtt'))

    def test_unknown_task_rejected(self):
        with self.assertRaises(H.HardwareError):
            H.rank('teleport', [PC_A])


class Benches(unittest.TestCase):
    def test_microbench_bounds(self):
        with self.assertRaises(H.HardwareError):
            H.microbench('cpu_loop', iterations=10**12)
        with self.assertRaises(H.HardwareError):
            H.microbench('disk_write', megabytes=10**6)
        with self.assertRaises(H.HardwareError):
            H.microbench('nope')
        r = H.microbench('cpu_loop', iterations=20000)
        self.assertGreater(r['value'], 0)
        self.assertEqual((r['unit'], r['confidence']), ('ms', 'measured'))

    def test_microbench_disk_bounded_and_clean(self):
        with tempfile.TemporaryDirectory() as d:
            import os
            r = H.microbench('disk_write', megabytes=1, directory=d)
            self.assertGreater(r['value'], 0)
            self.assertEqual(r['unit'], 'MB/s')
            self.assertEqual(os.listdir(d), [])

    def test_microbench_needs_consent(self):
        with self.assertRaises(H.HardwareError):
            H.microbench('cpu_loop', iterations=1000, consent=False)

    def test_microbench_device_rtt_with_fake_runner(self):
        r = H.microbench('device_rtt', runner=lambda *a: 'ok', attempts=2)
        self.assertEqual(r['unit'], 'ms')
        self.assertGreaterEqual(r['value'], 0)
        self.assertEqual(r['confidence'], 'measured')
        with self.assertRaises(H.HardwareError):
            H.microbench('device_rtt', attempts=99)
