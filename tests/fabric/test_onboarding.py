"""Connect-a-device candidates (SIMULATED_VERIFIED: synthetic mDNS/BLE/ADB fixtures)."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.fabric import onboarding
from src.fabric.apk_portal import ApkPortal
from src.fabric.contracts import Identifier, Link, DeviceObservation, now
from src.fabric.discovery import ingest_mdns
from src.fabric.registry import Registry


def mdns(*inst):
    return {'instances': [dict(i, txt=i.get('txt', {}), addresses=i.get('addresses', ['192.168.1.40']), host=i.get('host', 'h.local'),
                               category=i.get('category', 'android')) for i in inst]}


class Candidates(unittest.TestCase):
    def build(self):
        reg = Registry()
        ingest_mdns(reg, mdns({'service': '_adb-tls-pairing._tcp', 'instance': 'adb-ABC', 'port': 34511, 'host': 'android-1.local'},
                              {'service': '_adb-tls-connect._tcp', 'instance': 'adb-ABC', 'port': 35751, 'host': 'android-1.local'},
                              {'service': '_device-info._tcp', 'instance': 'Enzo iPhone', 'port': 0, 'host': 'iphone.local', 'addresses': ['192.168.1.50'],
                               'txt': {'model': 'iPhone15,2'}, 'category': 'unknown'},
                              {'service': '_companion-link._tcp', 'instance': 'Enzo iPhone', 'port': 49152, 'host': 'iphone.local',
                               'addresses': ['192.168.1.50'], 'category': 'apple'}), b's')
        k = reg.upsert([Identifier('android_serial', 'id-1', True)], category='phone', label='BV9300_Pro',
                       observations=[DeviceObservation('model', 'BV9300_Pro', 'ADB', 'USB', now(), True)])
        reg.devices[k]['handles'] = {'WIFI': 'h1'}
        reg.link(Link('pc', k, 'WIFI', ('read', 'control'), 'ADB:device'))
        b = reg.upsert([], category='ble', label='Samsung device (BLE)', observations=[DeviceObservation('ble_company_ids', [117], 'RELAY:r', 'BLE', now(), True)])
        return reg

    def test_kinds_states_and_methods(self):
        reg = self.build()
        c = {x['label']: x for x in onboarding.candidates(reg.snapshot(), reg, companion_ready=True)}
        pair = next(x for x in c.values() if any(m.get('pairing_address') for m in x['methods']))
        self.assertEqual(pair['state'], 'READY')
        self.assertEqual(next(m for m in pair['methods'] if m['id'] == 'adb_wifi')['pairing_address'], '192.168.1.40:34511')
        bv = c['BV9300_Pro']
        self.assertEqual(bv['state'], 'CONNECTED'); self.assertEqual(bv['model'], 'BV9300_Pro')
        self.assertEqual(next(m for m in bv['methods'] if m['id'] == 'companion_apk')['status'], 'READY')
        iphone = next(x for x in c.values() if x['kind'] == 'phone' and x['model'] == 'iPhone15,2')
        self.assertEqual(iphone['methods'][0]['status'], 'UNAVAILABLE')
        self.assertIn('No iOS Companion', iphone['methods'][0]['reason'])
        weak = c['Samsung device (BLE)']
        self.assertEqual((weak['kind'], weak['confidence'], weak['state']), ('phone_maybe', 'weak', 'IDENTIFY'))
        snap = reg.snapshot()
        self.assertNotIn('34511', repr(snap))                     # pairing endpoint stays off the snapshot

    def test_companion_not_built_is_honest(self):
        reg = self.build()
        bv = next(x for x in onboarding.candidates(reg.snapshot(), reg, companion_ready=False) if x['label'] == 'BV9300_Pro')
        m = next(m for m in bv['methods'] if m['id'] == 'companion_apk')
        self.assertEqual(m['status'], 'UNAVAILABLE'); self.assertIn('not built', m['reason'])

    def test_no_snapshot(self):
        self.assertEqual(onboarding.candidates(None, None), [])


class Portal(unittest.TestCase):
    def test_lan_only_single_file(self):
        with tempfile.TemporaryDirectory() as d:
            apk = Path(d) / 'a.apk'; apk.write_bytes(b'PK\x03\x04fake')
            for bad in ('8.8.8.8', '127.0.0.1'):
                with self.assertRaises(ValueError):
                    ApkPortal(apk, bad)
            with self.assertRaises(FileNotFoundError):
                ApkPortal(Path(d) / 'missing.apk', '192.168.1.2')
            p = ApkPortal(apk, '192.168.1.2', minutes=99)
            self.assertEqual(p.minutes, 30)


if __name__ == '__main__':
    unittest.main()
