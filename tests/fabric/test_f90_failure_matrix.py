"""F90 extended distributed-systems failure matrix (Campaign One, section 3.3).

Controlled, deterministic simulations of the failure modes a phone/PC fabric
hits in the field: network partition, high latency, duplicate/reordered/stale
messages, delayed acknowledgements, server/relay/companion restart recovery,
invalid and revoked grants, lost receipts, concurrent enrollment, lease expiry,
simultaneous auth changes, unreachable-device recovery, and commands queued
while the device sleeps.

Tests only: no src changes, no network, no model, no real-clock dependence.
Every crypto envelope carries a fixed issue time (T0), every router/ledger
assertion runs on the injected Clock from tests.runtime.test_routing, request
ids are fixed hex, and thread coordination uses Events/barriers with generous
timeouts (synchronisation, never timing assertions). Every spawned thread is
joined.

Fixtures extend tests.fabric.test_relay (scan FakeRelay), tests.runtime
test_routing (world/Clock), test_remote_controls (FakeCompanion),
test_command_center (cmd_server) and test_command_drain (DrainFake).
"""
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from src.fabric import relay as R
from src.fabric.contracts import DeviceObservation, Identifier, Link, now as now_iso
from src.fabric.registry import Registry
from src.fabric.relay_store import RelayStore
from src.fabric.session import SessionJournal
from src.runtime import route_contract as rc
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.contract import TransactionReceipt
from src.runtime.primitives import Executor
from src.runtime.relay_health import RelayLedger
from src.runtime.routing import INVOCATION_LEASE_S, RouteError
from src.runtime.remote_controls import RemoteControlError
from src.runtime.state_store import StateStore
from tests.fabric.test_relay import FakeRelay as ScanFake
from tests.runtime.test_command_center import (
    CMD_KEY, FakeCmdCompanion, FakeTransport, cmd_server, good_reply,
)
from tests.runtime.test_command_drain import (
    FakeRelay as DrainFake,
)
from tests.runtime.test_command_drain import make_server as drain_server
from tests.runtime.test_command_drain import RID as DRAIN_RID
from tests.runtime.test_remote_controls import FakeCompanion
from tests.runtime.test_routing import Clock, world

T0 = 1793100000  # fixed envelope issue time (matches Clock default)
KEY = R.derive_key('123456', 'rn', 'pn')
RC_KEY = R.derive_key('654321', 'rn', 'pn')  # == CMD_KEY / remote-controls KEY


def _rid(i):
    return '%032x' % i


def _reply(key, rid, params, nonce, now, ttl=30):
    msg = {'protocol': R.PROTOCOL, 'relay_id': rid, 'op': 'reply',
           'params': params, 'nonce': nonce, 'issued_at': now,
           'expires_at': now + ttl}
    return {**msg, 'mac': R.sign(key, msg)}


class MemVault:
    """In-memory stand-in for the OS secret store (survives a 'restart')."""

    def __init__(self):
        self.available = True
        self.secrets = {}

    def put(self, name, secret):
        self.secrets[name] = secret

    def get(self, name):
        return self.secrets.get(name)

    def delete(self, name):
        self.secrets.pop(name, None)


def _two_relay_manager(down=None):
    """RelayManager with tv + phone relays; `down` maps device_key -> partitioned."""
    down = down if down is not None else {}
    fakes = {'dev-tv': ScanFake([{'address': 'AA:00', 'name': 'TvAdv', 'rssi': -60}]),
             'dev-phone': ScanFake([{'address': 'BB:00', 'name': 'PhAdv', 'rssi': -70}])}

    def transport(relay, message):
        if down.get(relay['device_key']):
            raise ConnectionRefusedError('partitioned')
        return fakes[relay['device_key']](relay, message)

    mgr = R.RelayManager(transport)
    for rid, dev in (('tv', 'dev-tv'), ('phone', 'dev-phone')):
        mgr.enroll(rid, KEY, dev, {'capabilities': ['ble_scan'],
                                   'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
    return mgr, down


def _remote_server():
    """world() + watch relay + FakeCompanion + fake device_action runner.

    Returns (server, keys, clock, companion, rc, calls). Caller owns rc.close().
    """
    clock = Clock()
    server, keys = world(clock)
    reg = server.fabric_registry
    w = reg.upsert([Identifier('android_serial', 'watch-1', True)], category='watch',
                   label='SM-L310',
                   observations=[DeviceObservation('model', 'SM-L310', 'ADB', 'WIFI', now_iso(), True)])
    reg.devices[w]['handles'] = {'WIFI': 'h-watch-1'}
    reg.link(Link('pc', w, 'WIFI', ('observe', 'read', 'control'), 'ADB:device'))
    server.fabric_snapshot = reg.snapshot()
    companion = FakeCompanion(RC_KEY)
    companion.clock = clock
    server.relays.enroll('r-watch', RC_KEY, 'h-watch-1',
                         {'capabilities': ['remote_controls'], 'permissions': {}})
    server.relays.relays['r-watch']['send'] = companion
    calls = []

    def fake(self_, key, params):
        calls.append((key, params))
        return 'EXECUTED', None, None, True, {}

    ex = executor(server)
    ex.RUNNERS = dict(Executor.RUNNERS, device_action=fake)
    router(server).clock = clock
    rc = remote_controls(server)
    rc.clock = clock
    rc._ensure_thread = lambda: None  # tests drive poll_once() directly
    return server, keys, clock, companion, rc, calls


def _grant_vol(keys, rc):
    st = rc.set_controls({'relay_id': 'r-watch', 'controls': [
        {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
         'target': keys['tv'], 'params': {'direction': 'up'}}], 'consent': True})
    return st['controls'][0]['control_id']


def _unresolved_row(tx, state='UNKNOWN_TIMEOUT'):
    return {'transaction_id': tx, 'primitive_id': 'relay_ble_scan', 'device_key': 'dev-1',
            'state': state, 'before': None, 'after': None, 'verified': False,
            'started_at': '2026-01-01T00:00:00+00:00', 'finished_at': '2026-01-01T00:00:01+00:00',
            'errors': ['TIMEOUT: no result; state not verified']}


class NetworkPartitionTests(unittest.TestCase):
    def test_partitioned_relay_goes_offline_after_three_honest_failures(self):
        mgr, down = _two_relay_manager()
        down['dev-phone'] = True
        for attempt in (1, 2, 3):
            with self.assertRaises(R.RelayError) as ctx:
                mgr.scan(relay_id='phone')
            self.assertIn('unreachable', str(ctx.exception).lower())
            self.assertEqual(mgr.relays['phone']['failures'], attempt)
            self.assertFalse(mgr.relays['phone']['busy'])
        self.assertFalse(mgr.relays['phone']['online'])
        self.assertEqual(mgr.eligible('ble_scan'), ['tv'])

    def test_survivor_serves_scans_during_partition(self):
        mgr, down = _two_relay_manager()
        down['dev-phone'] = True
        for _ in range(3):
            with self.assertRaises(R.RelayError):
                mgr.scan(relay_id='phone')
        rid, found = mgr.scan(relay_id='tv')
        self.assertEqual((rid, found[0]['name']), ('tv', 'TvAdv'))
        auto_rid, _ = mgr.scan()  # auto-selection skips the partitioned relay
        self.assertEqual(auto_rid, 'tv')
        self.assertFalse(mgr.relays['phone']['online'])

    def test_busy_relay_refuses_without_failure_penalty(self):
        mgr, _ = _two_relay_manager()
        mgr.relays['tv']['busy'] = True
        with self.assertRaises(R.RelayError):
            mgr.scan(relay_id='tv')
        self.assertEqual(mgr.relays['tv']['failures'], 0)
        self.assertTrue(mgr.relays['tv']['online'])
        mgr.relays['tv']['busy'] = False
        rid, _ = mgr.scan(relay_id='tv')
        self.assertEqual(rid, 'tv')

    def test_partition_and_heal_across_two_relays_on_server(self):
        from src.server import create_server
        tmp = tempfile.mkdtemp()
        server = create_server(0, fabric_salt=b's', session_journal=SessionJournal(tmp + '/s.json'))
        self.addCleanup(server.server_close)
        reg = Registry()
        phone = reg.upsert([], category='phone', label='Phone')
        reg.devices[phone]['handles'] = {'USB': 'android-h1'}
        tv = reg.upsert([], category='tv', label='TV')
        reg.devices[tv]['handles'] = {'WIFI': 'android-h2'}
        server.fabric_registry = reg
        server.fabric_snapshot = reg.snapshot()
        key_p = R.derive_key('111111', 'rn', 'pn')
        key_t = R.derive_key('222222', 'rn', 'pn')
        state = {'tv_up': True}

        def send_for(key, obs_name):
            def send(relay, message):
                if key == key_t and not state['tv_up']:
                    raise ConnectionRefusedError('companion closed')
                msg = R.verify(key, message, {})
                if msg['op'] == 'get_status':
                    params = {'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}}
                elif msg['op'] == 'start_discovery':
                    params = {'observations': [{'address': 'C1:00:00:00:00:01', 'name': obs_name, 'rssi': -80}]}
                elif msg['op'] == 'stop_discovery':
                    params = {}
                else:
                    raise AssertionError('unexpected op ' + msg['op'])
                now = int(time.time())
                rep = {'protocol': R.PROTOCOL, 'relay_id': msg['relay_id'], 'op': 'reply',
                       'params': params, 'nonce': 'r' + msg['nonce'], 'issued_at': now, 'expires_at': now + 30}
                return {**rep, 'mac': R.sign(key, rep)}
            return send

        for rid, key, dev in (('phone', key_p, 'android-h1'), ('tv', key_t, 'android-h2')):
            server.relays.enroll(rid, key, dev, {'capabilities': ['ble_scan'],
                                                 'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        server.relays.relays['phone']['send'] = send_for(key_p, 'SensorP')
        server.relays.relays['tv']['send'] = send_for(key_t, 'SensorT')

        snap = server.relay_action('/api/relay-scan', {'relay_id': 'phone', 'seconds': 5})
        self.assertTrue(any(d['label'] == 'SensorP' for d in snap['devices']))
        state['tv_up'] = False  # partition the TV link only
        with self.assertRaises(R.RelayError) as ctx:
            server.relay_action('/api/relay-scan', {'relay_id': 'tv', 'seconds': 5})
        self.assertIn('unreachable', str(ctx.exception).lower())
        relay = server.relays.relays['tv']
        self.assertFalse(relay['online'])
        self.assertEqual(server.relay_ledger.routes['tv']['failures'], 1)
        self.assertEqual((relay['key'], relay['device_key']), (key_t, 'android-h2'))  # pairing intact
        snap = server.relay_action('/api/relay-scan', {'relay_id': 'phone', 'seconds': 5})  # survivor serves
        self.assertTrue(any(d['label'] == 'SensorP' for d in snap['devices']))
        state['tv_up'] = True  # heal: the signed status read-back brings it back
        snap = server.relay_action('/api/relay-scan', {'relay_id': 'tv', 'seconds': 5})
        self.assertTrue(server.relays.relays['tv']['online'])
        child = [d for d in snap['devices'] if d['label'] == 'SensorT'][0]
        link = [l for l in snap['links'] if l['child'] == child['key']][0]
        self.assertEqual((link['grants'], link['source']), (['observe'], 'RELAY:tv'))


class HighLatencyTests(unittest.TestCase):
    def test_reply_within_ttl_accepted_beyond_ttl_expired(self):
        R.verify(KEY, R.command(KEY, 'tv', 'get_status', now=T0), {}, now=T0 + 5)
        with self.assertRaisesRegex(R.RelayError, 'Expired'):
            R.verify(KEY, R.command(KEY, 'tv', 'get_status', now=T0), {}, now=T0 + R.COMMAND_TTL + 1)

    def test_failover_skips_blackholed_url_for_healthy_one(self):
        calls = []

        def fake(url, timeout=25):
            def send(_r, _m):
                calls.append(url)
                if len(calls) == 1:
                    raise TimeoutError('blackholed subnet')
                return {'ok': True}
            return send

        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:11', 'http://127.0.0.1:12'])
            self.assertEqual(send(None, {'op': 'probe'}), {'ok': True})
        self.assertEqual(calls, ['http://127.0.0.1:11', 'http://127.0.0.1:12'])

    def test_all_urls_down_raises_last_transport_error(self):
        def fake(url, timeout=25):
            def send(_r, _m):
                raise OSError('down ' + url)
            return send

        with mock.patch.object(R, 'http_transport', side_effect=fake):
            send = R.failover_transport(['http://127.0.0.1:11', 'http://127.0.0.1:12'])
            with self.assertRaisesRegex(OSError, '127.0.0.1:12'):
                send(None, {'op': 'probe'})

    def test_stale_signed_reply_refused_without_link_penalty(self):
        def stale(relay, message):
            R.verify(KEY, message, {})
            return _reply(KEY, 'tv', {'observations': []}, 'stale-%s' % message['nonce'], T0 - 60)

        mgr = R.RelayManager(stale)
        mgr.enroll('tv', KEY, 'dev-tv', {'capabilities': ['ble_scan'],
                                         'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        with self.assertRaisesRegex(R.RelayError, 'Expired'):
            mgr.scan(relay_id='tv')
        self.assertEqual(mgr.relays['tv']['failures'], 0)  # stale crypto is not a link failure
        self.assertTrue(mgr.relays['tv']['online'])
        self.assertFalse(mgr.relays['tv']['busy'])
        self.assertEqual(mgr.eligible('ble_scan'), ['tv'])


class MessageOrderTests(unittest.TestCase):
    """Duplicate, reordered and stale envelopes: fixed issue times, no clock."""

    def test_duplicate_nonce_rejected_as_replay(self):
        seen = {}
        cmd = R.command(KEY, 'tv', 'get_status', now=T0)
        R.verify(KEY, cmd, seen, now=T0)
        with self.assertRaisesRegex(R.RelayError, 'Replay'):
            R.verify(KEY, cmd, seen, now=T0)

    def test_reordered_delivery_all_accepted_exactly_once(self):
        seen = {}
        cmds = [R.command(KEY, 'tv', 'get_status', now=T0) for _ in range(3)]
        for c in (cmds[2], cmds[0], cmds[1]):  # arrival order differs from issue order
            R.verify(KEY, c, seen, now=T0)
        for c in cmds:  # ... but each is still single-use
            with self.assertRaisesRegex(R.RelayError, 'Replay'):
                R.verify(KEY, c, seen, now=T0)

    def test_expiry_boundary_is_inclusive(self):
        R.verify(KEY, R.command(KEY, 'tv', 'get_status', now=T0), {}, now=T0 + R.COMMAND_TTL)
        with self.assertRaisesRegex(R.RelayError, 'Expired'):
            R.verify(KEY, R.command(KEY, 'tv', 'get_status', now=T0), {}, now=T0 + R.COMMAND_TTL + 1)

    def test_future_skew_boundary(self):
        R.verify(KEY, R.command(KEY, 'tv', 'get_status', now=T0), {}, now=T0 - 5)
        with self.assertRaisesRegex(R.RelayError, 'Expired'):
            R.verify(KEY, R.command(KEY, 'tv', 'get_status', now=T0), {}, now=T0 - 6)

    def test_tampered_envelope_and_wrong_key_rejected(self):
        cmd = R.command(KEY, 'tv', 'get_status', now=T0)
        tampered = dict(cmd, op='revoke_access')
        with self.assertRaisesRegex(R.RelayError, 'Bad signature'):
            R.verify(KEY, tampered, None, now=T0)
        with self.assertRaisesRegex(R.RelayError, 'Bad signature'):
            R.verify(R.derive_key('000000', 'rn', 'pn'), cmd, None, now=T0)


class DelayedAckTests(unittest.TestCase):
    def test_lost_report_ack_never_reexecutes_duplicate_recognised(self):
        server, keys, clock, companion, rc, calls = _remote_server()
        self.addCleanup(rc.close)
        cid = _grant_vol(keys, rc)
        state = {'dropped': False}

        def flaky(relay, message):
            if message.get('op') == 'report_result' and not state['dropped']:
                state['dropped'] = True
                raise OSError('ack lost on the wire')  # device never sees it
            return companion(relay, message)

        server.relays.relays['r-watch']['send'] = flaky
        rid = _rid(1301)
        companion.press(cid, request_id=rid)
        self.assertEqual(rc.poll_once(), 1)
        self.assertEqual(len(calls), 1)  # dispatched exactly once ...
        self.assertEqual(companion.results, [])  # ... but the ack never landed
        self.assertEqual(rc.state()['history'][-1]['state'], 'EXECUTED')
        # The dropped ack also marked the relay offline; the retry re-probes it.
        clock.t += 6
        companion.press(cid, request_id=rid)  # device retries the unacked press
        rc.poll_once()
        self.assertEqual(len(calls), 1)  # never dispatched twice
        self.assertIn('already done', companion.results[-1]['text'])
        self.assertEqual(rc.state()['history'][-1]['state'], 'DUPLICATE')

    def test_transient_poll_failure_retains_device_queue(self):
        from src.runtime import command_drain as D

        class FlakyDrain(DrainFake):
            def __init__(self, commands):
                super().__init__(commands)
                self.probes = 0

            def send(self, relay, msg):
                if msg['op'] == 'get_commands' and self.probes == 0:
                    self.probes += 1
                    raise OSError('transient partition')  # device queue untouched
                return super().send(relay, msg)

        cmds = [{'request_id': _rid(1401 + i), 'kind': 'text', 'text': 'allume la lampe',
                 'lang': 'fr', 'quality': 'auto'} for i in range(3)]
        fake = FlakyDrain(cmds)
        srv = drain_server(fake)
        parse = lambda s, b: {'intent': {'status': 'resolved', 'outcome': 'Would run x'}}
        stats = D.poll_once(srv, parse_fn=parse, sync=True)
        self.assertEqual((stats['commands'], stats['reported']), (0, 0))
        self.assertEqual(len(stats['errors']), 1)
        self.assertEqual(fake.reports, [])
        stats = D.poll_once(srv, parse_fn=parse, sync=True)
        self.assertEqual((stats['commands'], stats['reported']), (3, 3))
        self.assertEqual([r[0] for r in fake.reports], [_rid(1401 + i) for i in range(3)])

    def test_report_failure_counted_with_request_identity(self):
        from src.runtime import command_drain as D
        cmd = {'request_id': _rid(1501), 'kind': 'text', 'text': 'allume la lampe',
               'lang': 'fr', 'quality': 'auto'}
        fake = DrainFake([cmd], fail_ops=('report_command',))
        stats = D.poll_once(drain_server(fake),
                            parse_fn=lambda s, b: {'intent': {'status': 'resolved'}}, sync=True)
        self.assertEqual((stats['commands'], stats['reported']), (1, 0))
        self.assertEqual(len(stats['errors']), 1)
        self.assertIn(_rid(1501), stats['errors'][0])
        self.assertEqual(fake.reports, [])


class RestartRecoveryTests(unittest.TestCase):
    def test_relay_store_roundtrip_restores_pairing(self):
        tmp = tempfile.mkdtemp()
        vault = MemVault()
        store = RelayStore(tmp + '/relays.json', vault)
        rid = 'relay-abcdef0123'
        declared = {'capabilities': ['ble_scan'], 'battery_powered': False}
        self.assertTrue(store.save(rid, 'serial-1', KEY, declared))
        fresh = RelayStore(tmp + '/relays.json', vault)  # server restart, same OS vault
        out = fresh.load()
        self.assertEqual(len(out), 1)
        got_rid, serial, key, got_declared, aead = out[0]
        self.assertEqual((got_rid, serial, key), (rid, 'serial-1', KEY))
        self.assertEqual(got_declared, {'capabilities': ['ble_scan'], 'battery_powered': False})
        self.assertIsNone(aead)

    def test_repair_same_serial_replaces_old_pairing(self):
        tmp = tempfile.mkdtemp()
        vault = MemVault()
        store = RelayStore(tmp + '/relays.json', vault)
        store.save('relay-aaaa000001', 'serial-9', KEY, {'capabilities': ['ble_scan']})
        store.save('relay-bbbb000002', 'serial-9', KEY, {'capabilities': ['ble_scan']})
        out = RelayStore(tmp + '/relays.json', vault).load()
        self.assertEqual([r[0] for r in out], ['relay-bbbb000002'])  # one pairing per device
        self.assertIsNone(vault.get('relay-key-aaaa000001'))  # old key forgotten

    def test_corrupt_store_fails_closed_and_refuses_overwrite(self):
        from pathlib import Path
        tmp = tempfile.mkdtemp()
        path = Path(tmp + '/relays.json')
        path.write_text('{corrupt json', encoding='utf-8')
        store = RelayStore(str(path), MemVault())
        self.assertEqual(store.load(), [])
        self.assertIn('unreadable', store.error)
        self.assertFalse(store.save('relay-cccc000003', 'serial-1', KEY, {'capabilities': []}))
        self.assertEqual(path.read_text(encoding='utf-8'), '{corrupt json')  # left for inspection

    def test_invocation_journal_survives_restart(self):
        tmp = tempfile.mkdtemp()
        path = tmp + '/runtime-state.json'
        now = 1700000000.0
        store = StateStore(path)
        self.assertEqual(store.claim_invocation('actor-a', 'id-done', now), (True, None))
        self.assertTrue(store.finish_invocation('actor-a', 'id-done', 'ab' * 32, now + 1))
        self.assertEqual(store.claim_invocation('actor-a', 'id-exec', now), (True, None))
        fresh = StateStore(path)  # process restart: same file
        claimed, row = fresh.claim_invocation('actor-a', 'id-done', now + 2)
        self.assertFalse(claimed)
        self.assertEqual((row['state'], row['fingerprint']), ('DONE', 'ab' * 32))
        claimed, row = fresh.claim_invocation('actor-a', 'id-exec', now + 2)
        self.assertFalse(claimed)  # leftover EXECUTING refuses as uncertain
        self.assertEqual(row['state'], 'EXECUTING')
        claimed, _ = fresh.claim_invocation('actor-a', 'id-fresh', now + 2)
        self.assertTrue(claimed)

    def test_router_boots_journal_rows_as_duplicates(self):
        tmp = tempfile.mkdtemp()
        from pathlib import Path
        Path(tmp, 's.json').write_text('[]', encoding='utf-8')
        store = StateStore(str(Path(tmp, 'runtime-state.json')))
        real_now = time.time()
        store.claim_invocation('relay:r-watch', 'id-done', real_now)
        store.finish_invocation('relay:r-watch', 'id-done', 'cd' * 32, real_now)
        store.claim_invocation('relay:r-watch', 'id-exec', real_now)
        clock = Clock()
        server, _keys = world(clock)
        server.session_journal = SessionJournal(str(Path(tmp, 's.json')))
        rt = router(server)  # boot loads the journal
        rt.clock = clock
        with self.assertRaises(RouteError) as ctx:
            rt.arm({'consent': True}, actor='relay:r-watch', invocation_id='id-done')
        self.assertEqual(ctx.exception.code, 'DUPLICATE_REQUEST')
        with self.assertRaises(RouteError) as ctx:
            rt.arm({'consent': True}, actor='relay:r-watch', invocation_id='id-exec')
        self.assertEqual(ctx.exception.code, 'UNCERTAIN_OUTCOME')

    def test_companion_restart_repairs_ui_without_new_grant(self):
        server, keys, clock, companion, rc, calls = _remote_server()
        self.addCleanup(rc.close)
        cid = _grant_vol(keys, rc)
        companion.controls = []  # Companion restart wiped its UI, grants survive server-side
        self.assertTrue(rc.repush('r-watch'))
        self.assertEqual(companion.controls, [{'control_id': cid, 'label': 'TV volume +'}])
        companion.press(cid, request_id=_rid(2101))
        self.assertEqual(rc.poll_once(), 1)
        self.assertEqual(len(calls), 1)

    def test_repush_without_grants_pushes_nothing(self):
        _server, _keys, _clock, companion, rc, _calls = _remote_server()
        self.addCleanup(rc.close)
        self.assertFalse(rc.repush('r-watch'))
        self.assertEqual(companion.ops, [])


class InvalidRevokedGrantTests(unittest.TestCase):
    def test_malformed_grant_bodies_rejected_without_partial_install(self):
        server, keys, clock, companion, rc, _calls = _remote_server()
        self.addCleanup(rc.close)
        good = {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
                'target': keys['tv'], 'params': {'direction': 'up'}}
        bad_bodies = [None, {}, {'relay_id': 'r-watch', 'controls': []},
                      {'relay_id': 'r-watch', 'controls': [], 'consent': False},
                      {'relay_id': 'r-watch', 'controls': [], 'consent': True, 'evil': 1},
                      {'relay_id': 'r-watch', 'controls': 'x', 'consent': True},
                      {'relay_id': 'r-watch', 'controls': [dict(good) for _ in range(13)], 'consent': True},
                      {'relay_id': 'nope', 'controls': [], 'consent': True}]
        bad_controls = [dict(good, label=''), dict(good, skill_id='pc_job'),
                        dict(good, target=None), dict(good, params={'direction': 'sideways'}),
                        dict(good, extra=1)]
        for body in bad_bodies:
            with self.assertRaises(RemoteControlError, msg=repr(body)):
                rc.set_controls(body)
        for ctl in bad_controls:
            with self.assertRaises(RemoteControlError, msg=repr(ctl)):
                rc.set_controls({'relay_id': 'r-watch', 'controls': [ctl], 'consent': True})
        self.assertEqual(rc.state()['controls'], [])
        self.assertEqual(companion.ops, [])  # nothing was ever pushed to the device

    def test_capability_gate_and_shutdown(self):
        server, keys, _clock, _companion, rc, _calls = _remote_server()
        self.addCleanup(rc.close)
        server.relays.relays['r-watch']['capabilities'] = {'ble_scan'}
        with self.assertRaises(RemoteControlError) as ctx:
            _grant_vol(keys, rc)
        self.assertEqual(ctx.exception.status, 409)
        rc.close()
        with self.assertRaises(RemoteControlError) as ctx:
            rc.set_controls({'relay_id': 'r-watch', 'controls': [], 'consent': True})
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(rc.poll_once(), 0)

    def test_stale_press_after_revoke_dropped_regrant_dispatches(self):
        server, keys, clock, companion, rc, calls = _remote_server()
        self.addCleanup(rc.close)
        cid1 = _grant_vol(keys, rc)
        rc.set_controls({'relay_id': 'r-watch', 'controls': [], 'consent': True})  # owner revokes
        companion.press(cid1, request_id=_rid(2501))  # stale on-device button
        self.assertEqual(rc.poll_once(), 0)
        self.assertEqual(calls, [])
        cid2 = _grant_vol(keys, rc)  # re-grant mints a new generation id
        self.assertNotEqual(cid1, cid2)
        companion.press(cid1, request_id=_rid(2502))  # replay of the revoked id
        self.assertEqual(rc.poll_once(), 0)
        self.assertEqual(calls, [])
        self.assertEqual(rc.state()['history'], [])  # dropped before dispatch, never recorded
        clock.t += 1
        companion.press(cid2, request_id=_rid(2503))
        self.assertEqual(rc.poll_once(), 1)
        self.assertEqual(len(calls), 1)

    def test_repair_new_key_revokes_old_grants_per_dispatch(self):
        server, keys, clock, companion, rc, calls = _remote_server()
        self.addCleanup(rc.close)
        cid = _grant_vol(keys, rc)
        new_key = R.derive_key('999999', 'rn', 'pn')  # owner re-paired: new relay key
        server.relays.enroll('r-watch', new_key, 'h-watch-1',
                             {'capabilities': ['remote_controls'], 'permissions': {}})
        companion2 = FakeCompanion(new_key)
        companion2.clock = clock
        server.relays.relays['r-watch']['send'] = companion2
        companion2.press(cid, request_id=_rid(2601))
        self.assertEqual(rc.poll_once(), 1)
        self.assertEqual(calls, [])
        self.assertEqual(rc.state()['history'][-1]['state'], 'REVOKED')
        self.assertIn('no longer authorized', companion2.results[-1]['text'])

    def test_validate_requests_drops_unknown_but_keeps_known(self):
        report = {'requests': [
            {'request_id': _rid(2701), 'control_id': 'ctl-known'},
            {'request_id': _rid(2702), 'control_id': 'ctl-revoked'},
            {'request_id': 'bad-id', 'control_id': 'ctl-known'},
            'junk']}
        out = R.validate_requests(report, {'ctl-known'})
        self.assertEqual([r['request_id'] for r in out], [_rid(2701)])


class LostReceiptTests(unittest.TestCase):
    def test_press_lost_between_drain_and_dispatch_never_retried(self):
        server, keys, clock, companion, rc, calls = _remote_server()
        self.addCleanup(rc.close)
        cid = _grant_vol(keys, rc)
        companion.press(cid, request_id=_rid(2801))
        relay = server.relays.relays['r-watch']
        companion(relay, R.command(RC_KEY, 'r-watch', 'get_requests'))  # drained ...
        # ... then the PC crashes before dispatch: the reply is lost with it.
        self.assertEqual(companion.queue, [])  # at-most-once: no redelivery possible
        self.assertEqual(calls, [])
        clock.t += 1
        companion.press(cid, request_id=_rid(2802))  # owner presses again: fresh request
        self.assertEqual(rc.poll_once(), 1)
        self.assertEqual(len(calls), 1)

    def test_store_merge_retains_writers_and_tombstones(self):
        tmp = tempfile.mkdtemp()
        path = tmp + '/runtime-state.json'
        store = StateStore(path)
        store.save_unresolved([_unresolved_row('tx-f90-a'), _unresolved_row('tx-f90-b')])
        other = StateStore(path)  # second writer: new row + acknowledgement
        other.save_unresolved([_unresolved_row('tx-f90-c')], acknowledged=('tx-f90-a',))
        doc = other.load()
        self.assertEqual({r['transaction_id'] for r in doc['unresolved']}, {'tx-f90-b', 'tx-f90-c'})
        self.assertIn('tx-f90-a', doc['acknowledged'])
        store.save_unresolved([_unresolved_row('tx-f90-a')])  # stale writer re-saves A
        doc = StateStore(path).load()
        self.assertEqual({r['transaction_id'] for r in doc['unresolved']}, {'tx-f90-b', 'tx-f90-c'})

    def test_executor_restores_unresolved_backlog_on_boot(self):
        tmp = tempfile.mkdtemp()
        StateStore(tmp + '/runtime-state.json').save_unresolved(
            [_unresolved_row('tx-f90-a'), _unresolved_row('tx-f90-b', 'FAILED')])

        def ctx():
            return SimpleNamespace(
                session_journal=SimpleNamespace(path=tmp + '/s.json', open_changes=lambda: []),
                fabric_registry=None)

        ex = Executor(ctx())
        self.assertEqual(set(ex.recovery().pending_transactions), {'tx-f90-a', 'tx-f90-b'})
        self.assertTrue(ex.acknowledge('tx-f90-b'))
        rebooted = Executor(ctx())  # restart: only the unacknowledged row comes back
        self.assertEqual(rebooted.recovery().pending_transactions, ('tx-f90-a',))
        self.assertEqual(rebooted.receipts['tx-f90-a'].state, 'UNKNOWN_TIMEOUT')
        self.assertNotIn('tx-f90-b', rebooted.receipts)

    def test_acknowledged_frees_exactly_one_backlog_slot(self):
        ex = Executor(SimpleNamespace(fabric_registry=None,
                                      session_journal=SimpleNamespace(open_changes=lambda: [])))
        for i in range(Executor.MAX_UNRESOLVED):
            tx = 'u%d' % i
            ex.receipts[tx] = TransactionReceipt(tx, 'relay_revoke', 'k', 'UNKNOWN_TIMEOUT',
                                                None, None, False, '', '', ())
            ex._receipt_order.append(tx)

        def failing(self_, key, params):
            raise RuntimeError('adapter lost mid-operation')

        ex.RUNNERS = dict(Executor.RUNNERS, relay_revoke=failing)
        blocked = ex.execute('relay_revoke', 'k2', {'relay_id': 'r'}, consent=True)
        self.assertEqual(blocked['state'], 'BLOCKED')
        self.assertIn('RECOVERY_BACKLOG', blocked['errors'][0])
        self.assertTrue(ex.acknowledge('u0'))
        admitted = ex.execute('relay_revoke', 'k3', {'relay_id': 'r'}, consent=True)
        self.assertEqual(admitted['state'], 'FAILED')  # admitted, ran, failed honestly
        self.assertNotIn('RECOVERY_BACKLOG', admitted['errors'][0])
        self.assertEqual(len(ex.recovery().pending_transactions), Executor.MAX_UNRESOLVED)


class ConcurrentEnrollmentTests(unittest.TestCase):
    def test_concurrent_distinct_enrolls_all_land_complete(self):
        mgr = R.RelayManager(lambda relay, msg: {})
        ids = ['fx-%d' % i for i in range(8)]
        barrier = threading.Barrier(len(ids))
        errors = []

        def work(rid):
            try:
                barrier.wait(10)
                mgr.enroll(rid, KEY, 'dev-' + rid,
                           {'capabilities': ['ble_scan'],
                            'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errors.append(e)

        threads = [threading.Thread(target=work, args=(rid,)) for rid in ids]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)
        self.assertFalse([th for th in threads if th.is_alive()])
        self.assertEqual(errors, [])
        self.assertEqual(set(mgr.relays), set(ids))
        for rid in ids:
            entry = mgr.relays[rid]
            self.assertEqual(entry['capabilities'], {'ble_scan'})
            self.assertTrue(entry['online'])
            self.assertEqual(entry['seen'], {})
        self.assertEqual(mgr.eligible('ble_scan'), sorted(ids))

    def test_concurrent_same_id_enroll_never_partial(self):
        mgr = R.RelayManager(lambda relay, msg: {})
        barrier = threading.Barrier(4)
        errors = []

        def work(i):
            try:
                barrier.wait(10)
                mgr.enroll('shared', KEY, 'dev-%d' % i,
                           {'capabilities': ['ble_scan'],
                            'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errors.append(e)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)
        self.assertFalse([th for th in threads if th.is_alive()])
        self.assertEqual(errors, [])
        entry = mgr.relays['shared']
        self.assertIn(entry['device_key'], {'dev-%d' % i for i in range(4)})
        self.assertEqual((entry['capabilities'], entry['online'], entry['seen']),
                         ({'ble_scan'}, True, {}))
        self.assertEqual(mgr.eligible('ble_scan'), ['shared'])


class _LeaseBase(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.calls = []
        ex = executor(self.server)

        def fake(self_, key, params):
            self.calls.append((key, params))
            return 'VERIFIED', None, {'ok': True}, True, {'ok': True}

        ex.RUNNERS = dict(Executor.RUNNERS, relay_ble_scan=fake)
        self.router = router(self.server)
        self.router.clock = self.clock
        self.server.relay_ledger.record('r-tv', [])
        self.clock.t += 5
        self.server.relay_ledger.record('r-ph', [])  # phone fresher: selected first

    def routes(self):
        doc = self.router.skill_routes('ble_scan_room')
        self.assertEqual(rc.validate_doc(doc), [])
        return doc

    def by_dev(self, doc, key):
        return next(r for r in doc['routes'] if r['hops'][0]['device_key'] == key)

    def arm(self, doc, params=None):
        return self.router.arm({'skill_id': 'ble_scan_room', 'route_id': doc['selected_route_id'],
                                'params': params or {'seconds': 8}, 'consent': True})

    def invoke(self, lease, params=None):
        return self.router.invoke({'invocation_id': lease['invocation_id'], 'skill_id': 'ble_scan_room',
                                   'route_id': lease['route_id'], 'lease_id': lease['lease_id'],
                                   'graph_revision': lease['graph_revision'],
                                   'params': params or {'seconds': 8}, 'consent': True})


class LeaseExpiryTests(_LeaseBase):
    def test_invocation_lease_expires_and_voids_consent(self):
        doc = self.routes()
        lease = self.arm(doc)
        self.assertEqual(self.routes()['invocation']['status'], 'armed')
        self.clock.t += INVOCATION_LEASE_S + 1
        with self.assertRaises(RouteError) as ctx:
            self.invoke(lease)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(ctx.exception.status, 409)
        self.assertIn('lease expired', str(ctx.exception))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.routes()['invocation']['status'], 'idle')

    def test_route_lease_expiry_voids_armed_consent(self):
        doc = self.routes()
        lease = self.arm(doc)
        self.clock.t += 500  # relay route leases are 120 s
        with self.assertRaises(RouteError) as ctx:
            self.invoke(lease)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(self.calls, [])

    def test_fresh_consent_after_expiry_dispatches_once(self):
        lease = self.arm(self.routes())
        self.clock.t += 500
        with self.assertRaises(RouteError):
            self.invoke(lease)
        self.server.relay_ledger.record('r-ph', [])  # fresh proof at the new time
        doc = self.routes()
        phone_route = self.by_dev(doc, self.keys['phone'])['route_id']
        self.assertEqual(doc['selected_route_id'], phone_route)
        lease2 = self.arm(doc)
        out = self.invoke(lease2)
        self.assertEqual(out['state'], 'VERIFIED')
        self.assertEqual(self.calls, [(self.keys['phone'], {'relay_id': 'r-ph', 'seconds': 8})])
        retry = self.invoke(lease2)
        self.assertEqual(retry['transaction_id'], out['transaction_id'])
        self.assertEqual(len(self.calls), 1)


class SimultaneousAuthTests(unittest.TestCase):
    def test_concurrent_grants_converge_single_generation(self):
        server, keys, _clock, companion, rc, _calls = _remote_server()
        self.addCleanup(rc.close)
        barrier = threading.Barrier(2)
        errors = []

        def work(label):
            try:
                barrier.wait(10)
                rc.set_controls({'relay_id': 'r-watch', 'controls': [
                    {'label': label, 'skill_id': 'tv_volume_step',
                     'target': keys['tv'], 'params': {'direction': 'up'}}], 'consent': True})
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errors.append(e)

        threads = [threading.Thread(target=work, args=(label,))
                   for label in ('Volume A', 'Volume B')]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)
        self.assertFalse([th for th in threads if th.is_alive()])
        self.assertEqual(errors, [])
        grants = rc.grants['r-watch']
        self.assertEqual(len(grants), 1)  # exactly one grant wins, never a mix
        self.assertEqual(len({g['generation'] for g in grants.values()}), 1)
        cid = next(iter(grants))
        self.assertEqual(companion.controls, [{'control_id': cid, 'label': grants[cid]['label']}])
        self.assertIn(grants[cid]['label'], {'Volume A', 'Volume B'})

    def test_slow_grant_loses_to_newer_revocation(self):
        server, keys, _clock, companion, rc, _calls = _remote_server()
        self.addCleanup(rc.close)
        started = threading.Event()
        release = threading.Event()
        errors = []
        orig = rc._send

        def slow(rid, op, params=None):
            if op == 'set_controls' and params.get('controls') and not started.is_set():
                started.set()
                self.assertTrue(release.wait(10))
            return orig(rid, op, params)

        rc._send = slow

        def grant():
            try:
                rc.set_controls({'relay_id': 'r-watch', 'controls': [
                    {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
                     'target': keys['tv'], 'params': {'direction': 'up'}}], 'consent': True})
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errors.append(e)

        worker = threading.Thread(target=grant)
        worker.start()
        self.assertTrue(started.wait(10))
        revoker = threading.Thread(target=lambda: rc.set_controls(
            {'relay_id': 'r-watch', 'controls': [], 'consent': True}))
        revoker.start()
        deadline = time.monotonic() + 10
        while rc._grant_versions.get('r-watch') != 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(rc._grant_versions.get('r-watch'), 2)
        release.set()
        worker.join(10)
        revoker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertFalse(revoker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(rc.state()['controls'], [])  # the delayed grant never resurrects
        self.assertEqual(companion.controls, [])

    def test_permission_revoked_midflight_voids_lease(self):
        clock = Clock()
        server, keys = world(clock)
        calls = []
        ex = executor(server)

        def fake(self_, key, params):
            calls.append((key, params))
            return 'VERIFIED', None, {'ok': True}, True, {'ok': True}

        ex.RUNNERS = dict(Executor.RUNNERS, relay_ble_scan=fake)
        rt = router(server)
        rt.clock = clock
        server.relay_ledger.record('r-tv', [])
        clock.t += 5
        server.relay_ledger.record('r-ph', [])
        doc = rt.skill_routes('ble_scan_room')
        phone_route = next(r for r in doc['routes']
                           if r['hops'][0]['device_key'] == keys['phone'])['route_id']
        self.assertEqual(doc['selected_route_id'], phone_route)
        lease = rt.arm({'skill_id': 'ble_scan_room', 'route_id': phone_route,
                        'params': {'seconds': 8}, 'consent': True})
        server.relays.relays['r-ph']['permissions']['BLUETOOTH_SCAN'] = False  # revoked mid-flight
        with self.assertRaises(RouteError) as ctx:
            rt.invoke({'invocation_id': lease['invocation_id'], 'skill_id': 'ble_scan_room',
                       'route_id': lease['route_id'], 'lease_id': lease['lease_id'],
                       'graph_revision': lease['graph_revision'],
                       'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(calls, [])
        doc2 = rt.skill_routes('ble_scan_room')  # fresh consent goes to the survivor
        tv_route = next(r for r in doc2['routes']
                        if r['hops'][0]['device_key'] == keys['tv'])['route_id']
        self.assertEqual(doc2['selected_route_id'], tv_route)
        lease2 = rt.arm({'skill_id': 'ble_scan_room', 'route_id': tv_route,
                         'params': {'seconds': 8}, 'consent': True})
        out = rt.invoke({'invocation_id': lease2['invocation_id'], 'skill_id': 'ble_scan_room',
                         'route_id': lease2['route_id'], 'lease_id': lease2['lease_id'],
                         'graph_revision': lease2['graph_revision'],
                         'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(out['state'], 'VERIFIED')
        self.assertEqual(calls, [(keys['tv'], {'relay_id': 'r-tv', 'seconds': 8})])


class UnreachableRecoveryTests(unittest.TestCase):
    def test_remote_poll_marks_offline_and_reprobes_on_clock(self):
        from src.runtime.remote_controls import RECONNECT_PROBE_S
        server, keys, clock, companion, rc, calls = _remote_server()
        self.addCleanup(rc.close)
        cid = _grant_vol(keys, rc)
        ops_before = list(companion.ops)

        def dead(relay, msg):
            raise OSError('link down')

        server.relays.relays['r-watch']['send'] = dead
        self.assertEqual(rc.poll_once(), 0)
        self.assertFalse(server.relays.relays['r-watch']['online'])
        self.assertEqual(rc.poll_once(), 0)  # probe budget spent: skipped, not hammered
        self.assertEqual(companion.ops, ops_before)
        clock.t += RECONNECT_PROBE_S + 1
        server.relays.relays['r-watch']['send'] = companion  # link heals
        companion.press(cid, request_id=_rid(4001))
        self.assertEqual(rc.poll_once(), 1)
        relay = server.relays.relays['r-watch']
        self.assertTrue(relay['online'])
        self.assertEqual(relay['failures'], 0)
        self.assertEqual(server.relay_ledger.routes['r-watch']['last_proof_at'], clock.t)
        kinds = [e['kind'] for e in executor(server).events_since(0)]
        self.assertIn('relay_reconnected', kinds)
        self.assertEqual(len(calls), 1)

    def test_companion_poll_isolates_dead_relay_and_recovers_retained(self):
        from src.runtime.companion_commands import CompanionCommands
        srv, comp_a = cmd_server()
        comp_b = FakeCmdCompanion(CMD_KEY)
        srv.relays.relays['r-watch'] = {'key': CMD_KEY, 'capabilities': ['command_submit'],
                                        'online': True, 'busy': False, 'send': comp_b, 'seen': {}}
        rid_a, rid_b = _rid(4101), _rid(4102)
        comp_a.type('Start my vacuum', rid=rid_a)
        comp_b.type('Stop my vacuum', rid=rid_b)

        def dead(relay, msg):
            raise OSError('companion closed')

        srv.relays.relays['r-phone']['send'] = dead
        cc = CompanionCommands(srv, low=FakeTransport(good_reply()), medium=FakeTransport(good_reply()))
        self.assertEqual(cc.poll_once(), 1)  # the survivor still serves
        self.assertEqual(set(cc.pending), {rid_b})
        self.assertFalse(srv.relays.relays['r-phone']['online'])
        srv.relays.relays['r-phone']['send'] = comp_a  # heal: the retained command flows
        srv.relays.relays['r-phone']['online'] = True
        self.assertEqual(cc.poll_once(), 1)
        self.assertEqual(set(cc.pending), {rid_a, rid_b})


class SleepQueueTests(unittest.TestCase):
    def _cc(self, srv):
        from src.runtime.companion_commands import CompanionCommands
        return CompanionCommands(srv, low=FakeTransport(good_reply()),
                                 medium=FakeTransport(good_reply()))

    def test_sleep_retains_queue_wake_delivers_exactly_once(self):
        srv, comp = cmd_server()
        relay = srv.relays.relays['r-phone']
        cc = self._cc(srv)
        ids = [_rid(4301 + i) for i in range(3)]
        relay['online'] = False  # device asleep: PC skips it, device retains
        for rid in ids:
            comp.type('cmd %s' % rid, rid=rid)
        self.assertEqual(cc.poll_once(), 0)
        self.assertEqual(cc.pending, {})
        relay['online'] = True
        self.assertEqual(cc.poll_once(), 3)
        self.assertEqual(set(cc.pending), set(ids))
        self.assertEqual([r['request_id'] for r in comp.reports], ids)
        self.assertEqual(cc.poll_once(), 0)  # drained: no duplicates on re-poll

    def test_repeated_sleep_cycles_preserve_order(self):
        srv, comp = cmd_server()
        relay = srv.relays.relays['r-phone']
        cc = self._cc(srv)
        typed = []
        for cycle in range(3):
            relay['online'] = False
            batch = [_rid(4401 + cycle * 10 + i) for i in range(3)]
            for rid in batch:
                comp.type('cmd %s' % rid, rid=rid)
            typed.extend(batch)
            relay['online'] = True
            self.assertEqual(cc.poll_once(), 3)
        self.assertEqual(len(cc.pending), 9)
        self.assertEqual(cc._order, typed)

    def test_oversize_wake_batch_refused_without_partial_admission(self):
        srv, comp = cmd_server()
        relay = srv.relays.relays['r-phone']
        cc = self._cc(srv)
        relay['online'] = False
        for i in range(9):  # device MAX_COMMANDS is 8
            comp.type('cmd %d' % i, rid=_rid(4501 + i))
        relay['online'] = True
        self.assertEqual(cc.poll_once(), 0)
        self.assertEqual(cc.pending, {})
        self.assertEqual(comp.reports, [])

    def test_drain_sleep_wake_delivers_all(self):
        from src.runtime import command_drain as D
        fake = DrainFake([])
        srv = drain_server(fake)
        relay = srv.relays.relays[DRAIN_RID]
        relay['online'] = False
        ids = [_rid(4601 + i) for i in range(3)]
        for rid in ids:
            fake.commands.append({'request_id': rid, 'kind': 'text', 'text': 'allume la lampe',
                                  'lang': 'fr', 'quality': 'auto'})
        parse = lambda s, b: {'intent': {'status': 'resolved', 'outcome': 'Would run x'}}
        stats = D.poll_once(srv, parse_fn=parse, sync=True)
        self.assertEqual((stats['relays_polled'], stats['commands']), (0, 0))
        self.assertEqual(stats['errors'], [])
        relay['online'] = True
        stats = D.poll_once(srv, parse_fn=parse, sync=True)
        self.assertEqual((stats['commands'], stats['reported']), (3, 3))
        self.assertEqual([r[0] for r in fake.reports], ids)


if __name__ == '__main__':
    unittest.main()
