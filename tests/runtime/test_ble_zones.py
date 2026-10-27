"""V4-11 zone proximity (SIMULATED_VERIFIED: generated RSSI with a fixed seed; not a hardware result)."""
import random
import unittest

from src.runtime import ble_zones as bz

# Invented ground truth: median RSSI per (zone, relay). 'doorway' is deliberately ambiguous for the TV relay alone.
TRUTH = {'desk': {'phone': -48, 'tv': -82}, 'doorway': {'phone': -66, 'tv': -71}, 'living_room': {'phone': -80, 'tv': -52}}


def gen(seed=7, runs=3, seconds=60, noise=4.0):
    rnd = random.Random(seed)
    out = []
    for zone, fp in TRUTH.items():
        for run in range(runs):
            for t in range(seconds):
                for relay, m in fp.items():
                    if rnd.random() < 0.8:                       # relays miss some advertisements
                        out.append({'zone': zone, 'run': run, 'relay_id': relay, 't': run * 1000 + t, 'rssi': round(rnd.gauss(m, noise))})
    return out


class Zones(unittest.TestCase):
    def test_two_relays_beat_one(self):
        rep = bz.report(gen())
        two = rep['two_relays']
        for z, m in two['zones'].items():
            self.assertGreaterEqual(m['recall'], 0.8, z)
            self.assertGreaterEqual(m['precision'], 0.9, z)
        self.assertLess(two['wrong_zone_rate'], rep['single_tv']['wrong_zone_rate'] + 1e-9)
        self.assertIn('not a position', two['claim'])

    def test_unknown_when_stale_missing_or_ambiguous(self):
        model = bz.fit(gen())
        self.assertEqual(bz.classify(model, [{'t': 0, 'relay_id': 'phone', 'rssi': -48}], now=100)['zone'], 'unknown')
        self.assertEqual(bz.classify(model, [{'t': 0, 'relay_id': 'phone', 'rssi': -48}])['zone'], 'unknown')   # TV relay missing
        mid = [{'t': 0, 'relay_id': 'phone', 'rssi': -57}, {'t': 0, 'relay_id': 'tv', 'rssi': -76}]           # halfway desk/doorway
        self.assertEqual(bz.classify(model, mid)['zone'], 'unknown')
        near_desk = [{'t': 0, 'relay_id': 'phone', 'rssi': -47}, {'t': 0, 'relay_id': 'tv', 'rssi': -83}]
        self.assertEqual(bz.classify(model, near_desk)['zone'], 'desk')

    def test_hysteresis(self):
        h = bz.Hysteresis(hold_s=15)
        seq = [(0, 'desk'), (5, 'desk'), (16, 'desk'), (20, 'doorway'), (25, 'desk'), (30, 'doorway'), (40, 'doorway'), (46, 'doorway')]
        out = [h.update(z, t) for t, z in seq]
        self.assertEqual(out, ['unknown', 'unknown', 'desk', 'desk', 'desk', 'desk', 'desk', 'doorway'])

    def test_single_run_zone_is_not_scored(self):
        s = [x for x in gen(runs=1)]
        rep = bz.evaluate(s)
        self.assertEqual(rep['windows'], 0)
        self.assertIsNone(rep['wrong_zone_rate'])

    def test_ledger_samples_only_for_selected_group(self):
        from src.runtime.relay_health import RelayLedger
        led = RelayLedger(clock=lambda: 100)
        obs = lambda a, r: {'address': a, 'rssi': r, 'address_kind': 'public', 'company_ids': [], 'service_uuids': [], 'name': ''}
        led.record('phone', [obs('AA:AA:AA:AA:AA:01', -50), obs('AA:AA:AA:AA:AA:02', -70)])
        gid = 'addr:' + RelayLedger._addr('AA:AA:AA:AA:AA:01')
        self.assertEqual(led.samples(gid), [{'t': 100, 'relay_id': 'phone', 'rssi': -50}])


if __name__ == '__main__':
    unittest.main()
