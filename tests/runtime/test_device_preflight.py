"""Preflight unit tests: parsing + verdict logic (no adb, no server)."""
import unittest
from unittest import mock

from dev import device_preflight as P


DUMPSYS_MUSIC = (
    '- STREAM_MUSIC:\n'
    '     Muted: false\n'
    '     Min: 0\n'
    '     Max: 15\n'
    '     streamVolume:7\n'
    '     Current: 1 (earpiece): 15, 2 (speaker): 7\n'
)


class ParseTest(unittest.TestCase):
    def test_parse_volume_reads_current(self):
        self.assertEqual(P.parse_volume(DUMPSYS_MUSIC), 7)

    def test_parse_max_reads_max(self):
        self.assertEqual(P.parse_max(DUMPSYS_MUSIC), 15)

    def test_parse_ignores_min_and_current_device_bits(self):
        tricky = ('- STREAM_MUSIC:\n     Muted: false\n     Min: 0\n'
                  '     Max: 100\n     streamVolume:20\n'
                  '     Current: 1 (earpiece): 99\n')
        self.assertEqual((P.parse_volume(tricky), P.parse_max(tricky)), (20, 100))

    def test_parse_volume_none_on_garbage(self):
        self.assertIsNone(P.parse_volume('no audio here'))
        self.assertIsNone(P.parse_volume(''))
        self.assertIsNone(P.parse_volume(None))


class AdbCheckTest(unittest.TestCase):
    def test_attached_device_go(self):
        pf = P.Preflight('TV123', 3)
        with mock.patch.object(P, 'adb', return_value=(0, 'List of devices attached\nTV123\tdevice\n')):
            self.assertTrue(pf.check_adb())

    def test_missing_serial_no_go(self):
        pf = P.Preflight('TV123', 3)
        with mock.patch.object(P, 'adb', return_value=(0, 'List of devices attached\nOTHER\tdevice\n')):
            self.assertFalse(pf.check_adb())

    def test_unauthorized_no_go(self):
        pf = P.Preflight('TV123', 3)
        with mock.patch.object(P, 'adb', return_value=(0, 'List of devices attached\nTV123\tunauthorized\n')):
            self.assertFalse(pf.check_adb())
            self.assertIn('unauthorized', pf.checks[-1]['detail'])


class OracleTest(unittest.TestCase):
    def test_plus_one_validates(self):
        pf = P.Preflight('TV123', 3)
        reads = iter([7, 8])
        pf.read_tv_volume = lambda: next(reads)
        with mock.patch.object(P.time, 'sleep', return_value=None):
            self.assertTrue(pf.check_oracle(io_input=lambda: ''))
        self.assertEqual((pf.v0, pf.v1), (7, 8))

    def test_no_move_fails_loudly(self):
        pf = P.Preflight('TV123', 3)
        pf.read_tv_volume = lambda: 7
        with mock.patch.object(P.time, 'sleep', return_value=None):
            self.assertFalse(pf.check_oracle(io_input=lambda: ''))
        self.assertIn('delta', pf.checks[-1]['detail'])

    def test_unreadable_fails(self):
        pf = P.Preflight('TV123', 3)
        pf.read_tv_volume = lambda: None
        self.assertFalse(pf.check_oracle(io_input=lambda: ''))


class HeadroomTest(unittest.TestCase):
    def test_enough_headroom(self):
        pf = P.Preflight('TV123', 3)
        pf.v1 = 10
        with mock.patch.object(P, 'adb', return_value=(0, DUMPSYS_MUSIC)):
            self.assertTrue(pf.check_headroom())

    def test_no_headroom_fails(self):
        pf = P.Preflight('TV123', 3)
        pf.v1 = 14
        with mock.patch.object(P, 'adb', return_value=(0, DUMPSYS_MUSIC)):
            self.assertFalse(pf.check_headroom())
            self.assertIn('lower volume', pf.checks[-1]['detail'])

    def test_unknown_max_fails(self):
        pf = P.Preflight('TV123', 3)
        pf.v1 = 5
        with mock.patch.object(P, 'adb', return_value=(0, 'STREAM_MUSIC: muted')):
            self.assertFalse(pf.check_headroom())


class TruncationTest(unittest.TestCase):
    BIG = 'x' * 7000 + DUMPSYS_MUSIC

    def test_adb_truncates_by_default_but_not_with_limit_none(self):
        from types import SimpleNamespace
        with mock.patch('subprocess.run',
                        return_value=SimpleNamespace(returncode=0, stdout='y' * 7000)):
            self.assertEqual(len(P.adb('devices')[1]), 6000)
            self.assertEqual(len(P.adb('devices', limit=None)[1]), 7000)

    def test_oracle_reads_music_block_beyond_6k(self):
        from types import SimpleNamespace
        pf = P.Preflight('TV123', 3)
        with mock.patch('subprocess.run',
                        return_value=SimpleNamespace(returncode=0, stdout=self.BIG)):
            self.assertEqual(pf.read_tv_volume(), 7)


class VerdictTest(unittest.TestCase):
    def test_all_ok_is_go(self):
        pf = P.Preflight('TV123', 3)
        pf.record('a', True)
        pf.record('b', True)
        self.assertEqual(pf.verdict()['verdict'], 'GO')

    def test_one_fail_is_no_go(self):
        pf = P.Preflight('TV123', 3)
        pf.record('a', True)
        pf.record('b', False, 'x')
        v = pf.verdict()
        self.assertEqual(v['verdict'], 'NO-GO')
        self.assertEqual(v['tv_serial'], 'TV123')


class RelayStoreWiringTest(unittest.TestCase):
    def test_discovery_server_receives_owner_relay_store(self):
        from src.fabric.relay_store import RelayStore
        pf = P.Preflight('TV123', 3)
        fake_server = mock.Mock()
        fake_server.fabric_snapshot = {'devices': []}
        with mock.patch('src.server.create_server', return_value=fake_server) as mk, \
             mock.patch('src.cli.ensure_discovery', return_value=None), \
             mock.patch.object(P, 'resolve_tv_key', return_value='tv-key'):
            self.assertTrue(pf.check_discovery())
        store = mk.call_args.kwargs['relay_store']
        self.assertIsInstance(store, RelayStore)
        self.assertEqual(store.path.name, 'relays.json')


if __name__ == '__main__':
    unittest.main()
