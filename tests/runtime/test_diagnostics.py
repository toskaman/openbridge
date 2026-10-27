import tempfile
import unittest
from datetime import date

from src.runtime import diagnostics as d

BATTERY = """Current Battery Service state:
  AC powered: false
  USB powered: true
  present: true
  status: 2
  health: 2
  level: 88
  scale: 100
  temperature: 462
"""
DF = "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-5 100000000 95000000 5000000 95% /data\n"


def fake_read(table):
    def read(*a):
        if a not in table:
            raise ValueError('unsupported')
        return table[a]
    return read


def by_name(fs):
    return {f['name']: f for f in fs}


class AndroidDiag(unittest.TestCase):
    def test_parses_and_infers(self):
        r = by_name(d.android(fake_read({
            ('dumpsys', 'battery'): BATTERY, ('df', '-k', '/data'): DF, ('cat', '/proc/uptime'): '7200.5 100.0',
            ('cmd', 'wifi', 'status'): 'Wifi is enabled', ('settings', 'get', 'global', 'airplane_mode_on'): '0',
            ('cat', '/sys/devices/system/cpu/possible'): '0-7\n', ('am', 'get-current-user'): '0',
            ('cat', '/proc/meminfo'): 'MemTotal: 8000000 kB\nMemAvailable: 2097152 kB\n',
            ('getprop', 'ro.build.version.security_patch'): '2024-05-01',
            ('pm', 'list', 'packages', '-3'): 'package:a\npackage:b\n'}), today=date(2026, 10, 27)))
        self.assertEqual(r['battery_level']['value'], 88)
        self.assertEqual(r['battery_temperature']['value'], 46.2)
        self.assertEqual(r['battery_hot']['kind'], 'INFERRED')
        self.assertEqual(r['battery_status']['value'], 'charging')
        self.assertEqual(r['storage_low']['kind'], 'INFERRED')
        self.assertEqual(r['uptime']['value'], 2.0)
        self.assertEqual(r['wifi']['value'], 'enabled')
        self.assertFalse(r['airplane_mode']['value'])
        self.assertEqual(r['cpu_cores']['value'], 8)
        self.assertEqual(r['memory_available']['value'], 2.0)
        self.assertEqual(r['security_patch_outdated']['value'], 29)
        self.assertEqual(r['user_installed_apps']['value'], 2)
        for f in r.values():
            if f['kind'] == 'OBSERVED':
                self.assertFalse(f['basis'])

    def test_every_read_optional(self):
        self.assertEqual(d.android(fake_read({})), [])

    def test_tv_without_battery(self):
        r = by_name(d.android(fake_read({('dumpsys', 'battery'): '  present: false\n'})))
        self.assertEqual(r['battery']['value'], 'none')
        self.assertNotIn('battery_level', r)

    def test_garbage_ignored(self):
        r = d.android(fake_read({('df', '-k', '/data'): 'garbage', ('cat', '/proc/uptime'): 'x',
                                 ('getprop', 'ro.build.version.security_patch'): 'unknown'}))
        self.assertEqual(r, [])


class FakeSession:
    def __init__(self, data, hosts):
        self.data, self.hosts = data, hosts

    def get(self, path):
        if path not in self.data:
            raise RuntimeError('denied')
        return self.data[path]

    def lan_hosts(self):
        return self.hosts


class FreeboxDiag(unittest.TestCase):
    def test_findings_and_privacy(self):
        s = FakeSession({
            'connection/': {'state': 'going_down', 'media': 'ftth', 'type': 'ethernet', 'bandwidth_down': 10_000_000_000,
                            'bandwidth_up': 900_000_000, 'rate_down': 1_000_000, 'rate_up': 125_000},
            'connection/ftth/': {'link': True, 'sfp_pwr_rx': -3000, 'sfp_pwr_tx': 269},
            'system/': {'firmware_version': '4.13.1', 'uptime_val': 86400 * 2, 'serial': 'SECRET',
                        'sensors': [{'id': 'temp_cpu', 'value': 79}], 'fans': [{'id': 'fan0', 'value': 1500}]},
            'wifi/config/': {'enabled': False},
            'wifi/ap/': [{'name': '5G', 'config': {'band': '5g', 'ssid': 'HOMESSID'}, 'status': {'state': 'disabled', 'primary_channel': 36}}],
        }, [{'mac': 'aa:bb', 'active': True}, {'mac': 'cc:dd', 'active': False}])
        with tempfile.TemporaryDirectory() as tmp:
            r = by_name(d.freebox(s, tmp))
            self.assertEqual(r['internet_down']['kind'], 'INFERRED')
            self.assertEqual(r['bandwidth_down']['value'], 10000)
            self.assertEqual(r['rate_up']['value'], 1.0)
            self.assertEqual(r['optical_power_rx']['value'], -30.0)
            self.assertIn('optical_rx_out_of_typical_range', r)
            self.assertEqual(r['box_uptime']['value'], 2.0)
            self.assertEqual(r['temperature_temp_cpu']['value'], 79)
            self.assertFalse(r['wifi_enabled']['value'])
            self.assertEqual(r['wifi_channel_5g']['value'], 36)
            self.assertEqual(r['lan_active_hosts']['value'], 1)
            blob = repr(r)
            for secret in ('SECRET', 'HOMESSID', 'aa:bb'):
                self.assertNotIn(secret, blob)
            s.hosts = [{'mac': 'ee:ff', 'active': True}]
            r2 = by_name(d.freebox(s, tmp))
            ch = r2['lan_presence_changes']
            self.assertEqual((ch['value']['arrived'], ch['value']['left'], ch['kind']), (1, 1, 'INFERRED'))

    def test_denied_endpoints(self):
        class Dead(FakeSession):
            def lan_hosts(self):
                raise RuntimeError('x')
        self.assertEqual(d.freebox(Dead({}, None), tempfile.mkdtemp()), [])


if __name__ == '__main__':
    unittest.main()
