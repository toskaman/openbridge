"""Golden leak corpus for cloud payloads (V4-05). Fail closed: every case must leave zero identifiers.
SIMULATED_VERIFIED: values are invented; none belongs to a real device or person."""
import json
import unittest

from src.runtime.redact import prepare, scan, LeakDetected, Redactor

GOLDEN = {
    'mac_colon': 'AA:BB:CC:DD:EE:FF', 'mac_dash': 'aa-bb-cc-dd-ee-01', 'ipv4': '192.168.1.15', 'ipv4_port': '10.0.0.7:5555',
    'ipv6_full': '2001:0db8:85a3:0000:0000:8a2e:0370:7334', 'ipv6_short': 'fe80::1c2:3ff:fe4',
    'ipv6_zone': 'fe80::a1b2:c3d4%wlan0', 'email': 'marie.dupont@example.org', 'phone_fr': '+33 6 12 34 56 78',
    'phone_plain': '0612345678', 'url': 'https://router.example/api?token=abc', 'adb_url': 'adb://10.0.0.9:37000',
    'uuid': '123e4567-e89b-12d3-a456-426614174000', 'opaque_dev': 'dev-3f2a9c1b77aa',
    'serial_hex': 'f8eed1f3a9b0c1d2e3f4', 'ssid_isp': 'Freebox-7A1B2C', 'ssid_box': 'Livebox-1234',
    'hostname_local': 'salon-tv.local', 'hostname_lan': 'nas.lan', 'wifi_qr': 'WIFI:T:WPA;S:Home;P:secret;;',
    'owner_device': "Marie's Galaxy", 'owner_device_fr': 'Salon TV de Marie',
}
SENSITIVE_KEYS = {'ssid': 'Home', 'password': 'hunter2', 'token': 'abc', 'serial': 'R58M', 'imei': '3567',
                  'label': 'Living room', 'hostname': 'tv', 'username': 'marie', 'latitude': 48.85, 'account': 'm@x'}


class Golden(unittest.TestCase):
    def test_each_identifier_is_found_by_the_scanner(self):
        for name, value in GOLDEN.items():
            if name == 'owner_device_fr':
                continue                    # free-text owner names are handled by dropping label/name keys
            with self.subTest(case=name):
                self.assertTrue(scan(f'x {value} y'), f'{name} not detected')

    def test_free_text_values_leave_no_identifier(self):
        for name, value in GOLDEN.items():
            with self.subTest(case=name):
                out = prepare({'note': f'seen {value} at 21:04', 'category': 'tv'})
                body = out['payload'].decode()
                self.assertNotIn(value, body)
                self.assertIn('21:04', body)          # times are not addresses

    def test_sensitive_keys_are_dropped_and_listed_in_the_diff(self):
        out = prepare({'device': dict(SENSITIVE_KEYS, category='tv', battery=80)})
        body = json.loads(out['payload'])
        self.assertEqual(body, {'device': {'category': 'tv', 'battery': 80}})
        self.assertEqual(out['stats']['dropped'], len(SENSITIVE_KEYS))

    def test_aliases_are_stable_inside_one_payload_and_unlinkable_across_payloads(self):
        a = prepare({'a': '192.168.1.15', 'b': 'from 192.168.1.15'})['payload'].decode()
        b = prepare({'a': '192.168.1.15'})['payload'].decode()
        al = json.loads(a)
        self.assertIn(al['a'], al['b'])
        self.assertNotEqual(al['a'], json.loads(b)['a'])

    def test_fail_closed_when_something_survives(self):
        r = Redactor()
        import src.runtime.redact as red
        orig = red.Redactor.text
        try:
            red.Redactor.text = lambda self, s, path: s       # simulate a broken redactor
            with self.assertRaises(LeakDetected):
                prepare({'note': 'AA:BB:CC:DD:EE:FF'})
        finally:
            red.Redactor.text = orig

    def test_indirect_leak_examples(self):
        # Device names built from people's names and Wi-Fi QR payloads are indirect identifiers.
        out = prepare({'facts': [{'name': 'tv', 'value': "Marie's Galaxy paired"}, {'value': 'WIFI:S:Home;P:pw;;'}]})
        body = out['payload'].decode()
        self.assertNotIn('Marie', body)
        self.assertNotIn('WIFI:', body)

    def test_nested_and_bounded(self):
        deep = {'l': [{'k': ['AA:BB:CC:DD:EE:FF'] * 3}] * 300}
        out = prepare(deep)
        self.assertLessEqual(len(json.loads(out['payload'])['l']), 200)
        self.assertNotIn('AA:BB', out['payload'].decode())

    def test_timestamps_and_versions_are_not_false_positives(self):
        for v in ('21:04:33', '2026-10-27', 'Android 14', 'v7.0.12', 'channel 36', '-62 dBm'):
            with self.subTest(v=v):
                self.assertEqual(scan(v), [], v)


if __name__ == '__main__':
    unittest.main()
