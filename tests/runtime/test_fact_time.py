import tempfile
import unittest
from unittest import mock

from src.fabric import discovery
from src.fabric.contracts import Identifier, DeviceObservation
from src.fabric.registry import Registry
from src.fabric.session import SessionJournal
from src.runtime import api_v2
from src.server import create_server


class FactTime(unittest.TestCase):
    def test_fact_time_is_the_observation_time_not_last_seen(self):
        s = create_server(0, fabric_salt=b'x', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        try:
            reg = Registry()
            obs = [{'address': 'C0:00:00:00:00:01', 'address_kind': 'static_random', 'rssi': -61, 'name': '', 'company_ids': [], 'service_uuids': []}]
            with mock.patch('src.fabric.discovery.now', return_value='2026-10-27T00:00:00+00:00'):
                discovery.ingest_ble(reg, {'devices': obs}, b'x', observer='pc', source='RELAY:r1')
            key = next(iter(reg.devices))
            reg.observe(key, DeviceObservation('name', 'x', 'MDNS', 'LAN', '2026-10-27T01:00:00+00:00', True))
            reg.upsert([Identifier('ble_address', next(i.value for i in reg.devices[key]['identifiers']), True)], category='ble')
            s.fabric_registry, s.fabric_snapshot = reg, reg.snapshot()
            read = api_v2.reader(s)
            facts = {f['name']: f for f in read('/api/v2/facts?device=' + key)['facts']}
            self.assertEqual(facts['ble_rssi']['observed_at'], '2026-10-27T00:00:00+00:00')
            self.assertEqual(facts['ble_rssi']['sources'], ['RELAY:r1'])
            self.assertEqual(facts['name']['observed_at'], '2026-10-27T01:00:00+00:00')
            reg.observe(key, DeviceObservation('ble_rssi', -40, 'RELAY:r2', 'BLE', '2026-10-27T02:00:00+00:00', True))
            s.fabric_snapshot = reg.snapshot()
            agg = {f['name']: f for f in read('/api/v2/facts?device=' + key)['facts']}['ble_rssi']
            self.assertEqual(sorted(agg['sources']), ['RELAY:r1', 'RELAY:r2'])
            only = read('/api/v2/facts?device=' + key + '&source=RELAY%3Ar1')['facts']
            self.assertEqual([(f['name'], f['value'], f['sources'], f['observed_at']) for f in only],
                             [('ble_rssi', -61, ['RELAY:r1'], '2026-10-27T00:00:00+00:00')])
            self.assertEqual(read('/api/v2/facts?device=' + key + '&source=RELAY%3Anone')['facts'], [])
            with self.assertRaises(PermissionError):
                read('/api/session')
            with self.assertRaises(LookupError):
                read('/api/v2/facts?device=nope')
        finally:
            s.server_close()


if __name__ == '__main__':
    unittest.main()


class NoGatewayProbe(unittest.TestCase):
    def test_android_only_discovery_never_touches_freebox(self):
        s = create_server(0, fabric_salt=b'x', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        try:
            def boom():
                raise AssertionError('gateway probed')
            s.freebox.discover = boom
            self.assertIsNone(s.fabric_adapters(('android', 'mdns'))['freebox'])
            with self.assertRaises(AssertionError):
                s.fabric_adapters(('freebox',))
        finally:
            s.server_close()
