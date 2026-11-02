"""Flagship-C O3 vehicle logic over doubles (no hardware, no server)."""
import json
import unittest
from types import SimpleNamespace

from dev.flagship_c_vehicle import (music_state_from_dumpsys,
                                    resolve_relay_id, resolve_tv_key,
                                    run_vehicle)


def make_io(script):
    """script: list per round of dicts(v0, v1, exec_count, post_revoke_exec)."""
    state = {'round': -1}

    def install(controls):
        return ['ctl-%d' % i for i in range(len(controls))]

    def await_press(control_id, timeout_s):
        return 'req-r%d' % state['round']

    def read_volume():
        r = script[state['round']]
        key = 'reads'
        r[key] = r.get(key, 0) + 1
        return r['v0'] if r[key] == 1 else r['v1']

    def journal_count(request_id):
        return script[state['round']]['exec_count']

    def revoke():
        pass

    def post_revoke_probe(control_id):
        return script[state['round']]['post_revoke_exec']

    return SimpleNamespace(install=install, await_press=await_press,
                           read_volume=read_volume,
                           journal_count=journal_count, revoke=revoke,
                           post_revoke_probe=post_revoke_probe,
                           prompt=lambda text: None, state=state)


class VehicleTest(unittest.TestCase):
    def test_two_perfect_rounds_pass(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 1, 'post_revoke_exec': 0},
                  {'v0': 11, 'v1': 12, 'exec_count': 1, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=2)
        self.assertEqual(receipt['verdict'], 'PASS')
        self.assertEqual([r['verdict'] for r in receipt['rounds']],
                         ['PASS', 'PASS'])
        self.assertEqual(receipt['rounds'][0]['delta'], 1)

    def test_unchanged_volume_fails_the_round(self):
        script = [{'v0': 10, 'v1': 10, 'exec_count': 1, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=1)
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('no volume change', receipt['rounds'][0]['reason'])

    def test_post_revoke_execution_fails_the_round(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 1, 'post_revoke_exec': 1}]
        receipt = run_vehicle(make_io(script), rounds=1)
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('post-revoke', receipt['rounds'][0]['reason'])

    def test_duplicate_execution_fails_the_round(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 2, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=1)
        self.assertEqual(receipt['verdict'], 'FAIL')
        self.assertIn('exactly-one', receipt['rounds'][0]['reason'])

    def test_live_provider_defaults_resolve(self):
        from argparse import Namespace
        from src.cli import default_providers
        self.assertEqual(default_providers(Namespace()),
                         ['mdns', 'ssdp', 'android', 'tuya'])

    def test_tv_resolve_picks_relay_service_view(self):
        tv_plain = {'key': 'dev-a', 'category': 'tv', 'facts': {}, 'capabilities': []}
        tv_relay = {'key': 'dev-b', 'category': 'tv',
                    'facts': {'mdns_services': {'value': ['_openbridge-relay._tcp']}},
                    'capabilities': []}
        srv = SimpleNamespace(fabric_snapshot={'devices': [tv_plain, tv_relay]})
        self.assertEqual(resolve_tv_key(srv), 'dev-b')

    def test_tv_resolve_fails_loudly_when_ambiguous(self):
        devs = [{'key': 'dev-%d' % i, 'category': 'tv',
                 'facts': {'mdns_services': {'value': ['_openbridge-relay._tcp']}},
                 'capabilities': []} for i in range(2)]
        with self.assertRaises(SystemExit):
            resolve_tv_key(SimpleNamespace(fabric_snapshot={'devices': devs}))

    def test_relay_resolve_picks_watch(self):
        relays = {'r-phone': {'online': True, 'device_key': 'h1'},
                  'r-watch': {'online': True, 'device_key': 'h2'}}
        reg = SimpleNamespace(devices={'k1': {'category': 'phone', 'handles': {'ADB': 'h1'}},
                                       'k2': {'category': 'watch', 'handles': {'ADB': 'h2'}}})
        srv = SimpleNamespace(relays=SimpleNamespace(relays=relays), fabric_registry=reg)
        self.assertEqual(resolve_relay_id(srv), 'r-watch')

    def test_relay_resolve_falls_back_to_single_online(self):
        relays = {'r-x': {'online': True, 'device_key': 'hz'}}
        srv = SimpleNamespace(relays=SimpleNamespace(relays=relays),
                              fabric_registry=SimpleNamespace(devices={}))
        self.assertEqual(resolve_relay_id(srv), 'r-x')

    def test_relay_resolve_fails_with_none_online(self):
        srv = SimpleNamespace(relays=SimpleNamespace(relays={}), fabric_registry=None)
        with self.assertRaises(SystemExit):
            resolve_relay_id(srv)

    def test_oracle_reads_stream_volume_not_min(self):
        out = ('- STREAM_MUSIC:\n     Muted: false\n     Min: 0\n'
               '     Max: 15\n     streamVolume:7\n')
        self.assertEqual(music_state_from_dumpsys(out), (7, 15))

    def test_oracle_unknown_format_is_null(self):
        self.assertEqual(music_state_from_dumpsys('Audio service wat?'),
                         (None, None))
        self.assertEqual(music_state_from_dumpsys(None), (None, None))

    def test_receipt_is_json_sanitized(self):
        script = [{'v0': 10, 'v1': 11, 'exec_count': 1, 'post_revoke_exec': 0}]
        receipt = run_vehicle(make_io(script), rounds=1)
        text = json.dumps(receipt)
        self.assertNotIn('654321', text)
        self.assertIn('vehicle', receipt)


class LiveWiringTest(unittest.TestCase):
    def test_live_main_passes_owner_relay_store(self):
        import dev.flagship_c_vehicle as V
        from unittest import mock
        from src.fabric.relay_store import RelayStore
        with mock.patch('src.server.create_server') as mk, \
             mock.patch('src.cli.ensure_discovery', return_value=None), \
             mock.patch.object(V, 'resolve_relay_id', return_value='relay-1'), \
             mock.patch.object(V, 'resolve_tv_key', return_value='tv-1'), \
             mock.patch.object(V, 'LiveIO'), \
             mock.patch.object(V, 'run_vehicle', return_value={'verdict': 'PASS'}):
            self.assertEqual(V.main(['--tv-serial', 'TV123']), 0)
        store = mk.call_args.kwargs['relay_store']
        self.assertIsInstance(store, RelayStore)
        self.assertEqual(store.path.name, 'relays.json')


class LiveRefreshTest(unittest.TestCase):
    def test_install_refreshes_discovery_and_reresolves(self):
        import dev.flagship_c_vehicle as V
        from unittest import mock
        with mock.patch('src.runtime.api_v2.remote_controls') as mkrc, \
             mock.patch('src.cli.ensure_discovery') as mkdisc, \
             mock.patch.object(V, 'resolve_relay_id', return_value='relay-9'), \
             mock.patch.object(V, 'resolve_tv_key', return_value='tv-9'):
            io = V.LiveIO(mock.Mock(), 'relay-0', 'tv-0', 'TV123')
            io.install([{'label': 'TV volume +', 'skill_id': 'tv_volume_step'}])
        mkdisc.assert_called_once_with(io.server, ['mdns', 'android'])
        body = mkrc.return_value.set_controls.call_args.args[0]
        self.assertEqual(body['relay_id'], 'relay-9')
        self.assertEqual(body['controls'][0]['target'], 'tv-9')
        self.assertEqual(io.tv_key, 'tv-9')

    def test_await_press_reinstalls_then_polls_new_id(self):
        import dev.flagship_c_vehicle as V
        from unittest import mock
        with mock.patch('src.runtime.api_v2.remote_controls') as mkrc, \
             mock.patch('src.cli.ensure_discovery') as mkdisc, \
             mock.patch.object(V, 'resolve_relay_id', return_value='relay-9'), \
             mock.patch.object(V, 'resolve_tv_key', return_value='tv-9'), \
             mock.patch.object(V.time, 'sleep', return_value=None):
            rc = mkrc.return_value
            rc.set_controls.return_value = {'controls': [{'control_id': 'ctl-new'}]}
            rc.press_history.side_effect = [[], [{'request_id': 'req-1'}]]
            io = V.LiveIO(mock.Mock(), 'relay-0', 'tv-0', 'TV123')
            io.install([{'label': 'TV volume +', 'skill_id': 'tv_volume_step'}])
            self.assertEqual(io.await_press('ctl-old', 300), 'req-1')
        self.assertEqual(mkdisc.call_count, 2)   # install + await
        self.assertEqual(rc.set_controls.call_count, 2)
        rc.press_history.assert_called_with('ctl-new')


if __name__ == '__main__':
    unittest.main()
