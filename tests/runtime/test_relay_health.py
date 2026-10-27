import unittest
from src.runtime.relay_health import RelayLedger
from src.runtime.fabric_diagnosis import diagnose


def ob(addr, kind='static_random', rssi=-60, name='', cids=(76,)):
    return {'address': addr, 'address_kind': kind, 'rssi': rssi, 'name': name, 'company_ids': list(cids), 'service_uuids': []}


class Clock:
    t = 1000.0
    def __call__(self):
        return self.t


class Ledger(unittest.TestCase):
    def setUp(self):
        self.c = Clock(); self.l = RelayLedger(self.c)

    def test_provenance_freshness_and_stale(self):
        self.l.record('r1', [ob('AA')])
        self.c.t += 10; self.l.record('r2', [ob('AA')])
        a = self.l.advertisers()[0]
        self.assertEqual((a['relays'], a['last_seen_s_ago'], a['stale'], a['samples']), (['r1', 'r2'], 0, False, 2))
        self.c.t += 200
        self.assertTrue(self.l.advertisers()[0]['stale'])
        self.assertEqual(self.l.route_status('r1'), 'FRESH' if 200 < 300 else 'STALE')
        self.c.t += 200
        self.assertEqual(self.l.route_status('r1'), 'STALE')
        self.assertEqual(self.l.route_status('r9'), 'NEVER_SUCCEEDED')
        self.assertEqual(self.l.route_status('r1', online=False), 'OFFLINE')

    def test_rotating_addresses_grouped_weakly(self):
        self.l.record('r1', [ob('11', 'resolvable_private', name='Buds'), ob('22', 'resolvable_private', name='Buds')])
        a = self.l.advertisers()
        self.assertEqual(len(a), 1)
        self.assertTrue(a[0]['rotating']); self.assertEqual(a[0]['addresses_seen'], 2)
        self.assertNotIn('11', repr(a))

    def test_anti_spoofing_flags(self):
        self.l.record('r1', [ob('AA', rssi=-90)]); self.c.t += 5
        self.l.record('r1', [ob('AA', rssi=-40, cids=(6,))])
        flags = {f['flag'] for f in self.l.advertisers()[0]['flags']}
        self.assertEqual(flags, {'rssi_jump', 'inconsistent_payload'})
        self.l.record('r1', [ob('33', 'resolvable_private', name='Living room TV', cids=())])
        rot = next(a for a in self.l.advertisers(['Living room TV']) if a['rotating'])
        self.assertEqual(rot['flags'][0]['flag'], 'name_collision'); self.assertEqual(rot['flags'][0]['kind'], 'INFERRED')


class Diagnosis(unittest.TestCase):
    def test_pc_without_ble_but_relay_capable_tv(self):
        snap = {'providers': {'ble': {'status': 'NO_ADAPTER'}}, 'possible_duplicates': [],
                'devices': [{'label': 'TV', 'capabilities': [{'name': 'ble_relay', 'status': 'REAL_HARDWARE_VERIFIED', 'level': 'observe'}]}]}
        f = {x['name']: x for x in diagnose(snap, [{'status': 'STALE'}], {'pending_transactions': ['t']})}
        self.assertEqual(f['pc_bluetooth']['value'], 'unavailable')
        self.assertEqual(f['ble_via_relay_possible']['kind'], 'INFERRED')
        self.assertIn('1 already proven', f['ble_via_relay_possible']['basis'])
        self.assertIn('relay_routes_degraded', f); self.assertIn('unverified_transactions', f)

    def test_no_relay_no_adapter(self):
        f = {x['name'] for x in diagnose({'providers': {'ble': {'status': 'NO_ADAPTER'}}, 'devices': []})}
        self.assertIn('ble_unreachable', f)
        self.assertEqual(diagnose(None)[0]['value'], 'empty')


if __name__ == '__main__':
    unittest.main()
