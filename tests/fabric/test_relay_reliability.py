"""F30 reliability starters, Phase B (tests-only, deterministic, offline).

Covers, against the current code at base 5f1d084:
  (1) relay failover between two BLE relays with consent-void proof
      (Router ble_scan_room: phone loss -> TV takes over, old lease void);
  (2) Companion command-queue overflow policy (bounded at MAX_PENDING,
      oldest-dropped FIFO, explicit drop count, no unbounded growth of
      either the pending map or its order list);
  (3) relay unreachable -> honest escalation (RelayError / offline flag /
      escalation_required / error stats, never a phantom success).

Fixtures extend tests.fabric.test_relay (FakeRelay/manager), tests.runtime
test_routing.world/Clock, tests.runtime.test_command_center.cmd_server and
tests.runtime.test_command_drain.FakeRelay. No network, no model, no clock
dependence beyond the injected Clock; request ids are fixed hex.
"""
import tempfile
import time
import unittest

from src.fabric import relay as R
from src.fabric.registry import Registry
from src.fabric.session import SessionJournal
from src.runtime import route_contract as rc
from src.runtime.api_v2 import executor, router
from src.runtime.primitives import Executor
from src.runtime.routing import RouteError
from tests.fabric.test_relay import FakeRelay, manager
from tests.runtime.test_command_center import (
    FakeTransport, cmd_server, good_reply,
)
from tests.runtime.test_command_drain import (
    FakeRelay as DrainFake,
)
from tests.runtime.test_command_drain import make_server as drain_server
from tests.runtime.test_routing import Clock, world


def _rid(i):
    return '%032x' % i


class TwoRelayFailoverTests(unittest.TestCase):
    """Router-level failover between r-tv and r-ph (ble_scan_room)."""

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
        # Phone scanned most recently, so AUTO picks the phone first.
        self.server.relay_ledger.record('r-tv', [])
        self.clock.t += 5
        self.server.relay_ledger.record('r-ph', [])

    def routes(self):
        doc = self.router.skill_routes('ble_scan_room')
        self.assertEqual(rc.validate_doc(doc), [])
        return doc

    def by_dev(self, doc, key):
        return next(r for r in doc['routes'] if r['hops'][0]['device_key'] == key)

    def arm(self, doc, params=None):
        return self.router.arm({
            'skill_id': 'ble_scan_room', 'route_id': doc['selected_route_id'],
            'params': params or {'seconds': 8}, 'consent': True})

    def invoke(self, lease, params=None):
        return self.router.invoke({
            'invocation_id': lease['invocation_id'], 'skill_id': 'ble_scan_room',
            'route_id': lease['route_id'], 'lease_id': lease['lease_id'],
            'graph_revision': lease['graph_revision'],
            'params': params or {'seconds': 8}, 'consent': True})

    def test_phone_loss_voids_armed_consent_and_tv_takes_over(self):
        doc = self.routes()
        phone_route = self.by_dev(doc, self.keys['phone'])['route_id']
        tv_route = self.by_dev(doc, self.keys['tv'])['route_id']
        self.assertEqual(doc['selected_route_id'], phone_route)
        lease = self.arm(doc)
        armed = self.routes()
        self.assertEqual(armed['invocation']['status'], 'armed')
        self.assertEqual(armed['invocation']['route_id'], phone_route)
        seq_before = doc['graph_revision']['seq']

        # The phone relay drops: its route goes link_down, TV is selected,
        # and the armed phone consent is void (invocation back to idle).
        self.server.relays.relays['r-ph']['online'] = False
        doc2 = self.routes()
        ph = self.by_dev(doc2, self.keys['phone'])
        tv = self.by_dev(doc2, self.keys['tv'])
        self.assertEqual((ph['state'], ph['reason']), ('UNAVAILABLE', 'link_down'))
        self.assertEqual(tv['state'], 'READY')
        self.assertEqual(doc2['selected_route_id'], tv_route)
        self.assertEqual(doc2['invocation']['status'], 'idle')
        self.assertGreater(doc2['graph_revision']['seq'], seq_before)
        changed = [e for e in executor(self.server).events_since(0)
                   if e['kind'] == 'route_changed']
        self.assertEqual(len(changed), 1)

        # The old lease is proof-void: invoking it dispatches nothing.
        with self.assertRaises(RouteError) as ctx:
            self.invoke(lease)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(ctx.exception.status, 409)
        self.assertEqual(self.calls, [])

        # Fresh consent on the survivor dispatches exactly once, to r-tv.
        lease2 = self.arm(doc2)
        out = self.invoke(lease2)
        self.assertEqual(out['state'], 'VERIFIED')
        self.assertEqual(out['route_id'], tv_route)
        self.assertEqual(self.calls, [(self.keys['tv'], {'relay_id': 'r-tv', 'seconds': 8})])
        retry = self.invoke(lease2)
        self.assertEqual(retry['transaction_id'], out['transaction_id'])
        self.assertEqual(len(self.calls), 1)

    def test_pinned_route_down_refuses_without_silent_failover(self):
        doc = self.routes()
        phone_route = self.by_dev(doc, self.keys['phone'])['route_id']
        self.router.set_policy({'skill_id': 'ble_scan_room', 'mode': 'PINNED',
                                'route_id': phone_route})
        self.assertEqual(self.routes()['selected_route_id'], phone_route)
        self.server.relays.relays['r-ph']['online'] = False
        doc2 = self.routes()
        self.assertIsNone(doc2['selected_route_id'])
        ph = self.by_dev(doc2, self.keys['phone'])
        tv = self.by_dev(doc2, self.keys['tv'])
        self.assertEqual((ph['state'], ph['reason']), ('UNAVAILABLE', 'link_down'))
        self.assertEqual(tv['state'], 'STANDBY')
        with self.assertRaises(RouteError) as ctx:
            self.router.arm({'skill_id': 'ble_scan_room', 'route_id': phone_route,
                             'params': {'seconds': 8}, 'consent': True})
        self.assertEqual(ctx.exception.code, 'ROUTE_NOT_SELECTED')
        self.assertEqual(self.calls, [])

    def test_failback_to_recovered_relay_voids_survivor_consent(self):
        doc = self.routes()
        self.server.relays.relays['r-ph']['online'] = False
        doc2 = self.routes()
        lease_tv = self.arm(doc2)
        # Phone comes back and proves fresher than the TV scan.
        self.server.relays.relays['r-ph']['online'] = True
        self.clock.t += 10
        self.server.relay_ledger.record('r-ph', [])
        doc3 = self.routes()
        phone_route = self.by_dev(doc3, self.keys['phone'])['route_id']
        self.assertEqual(doc3['selected_route_id'], phone_route)
        self.assertEqual(doc3['invocation']['status'], 'idle')
        with self.assertRaises(RouteError) as ctx:
            self.invoke(lease_tv)
        self.assertEqual(ctx.exception.code, 'CONSENT_VOID')
        self.assertEqual(self.calls, [])
        lease_ph = self.arm(doc3)
        out = self.invoke(lease_ph)
        self.assertEqual(out['state'], 'VERIFIED')
        self.assertEqual(self.calls[-1][1], {'relay_id': 'r-ph', 'seconds': 8})


class CommandQueueOverflowTests(unittest.TestCase):
    """CompanionCommands pending queue: bounded FIFO with a drop count."""

    def make_cc(self):
        from src.runtime.companion_commands import CompanionCommands
        srv, comp = cmd_server()
        cc = CompanionCommands(srv, low=FakeTransport(good_reply()),
                               medium=FakeTransport(good_reply()))
        return srv, comp, cc

    def test_pending_bounded_fifo_with_explicit_drop_count(self):
        from src.runtime.companion_commands import MAX_PENDING
        srv, comp, cc = self.make_cc()
        total = MAX_PENDING + 6
        ids = [_rid(1000 + i) for i in range(total)]
        for i, rid in enumerate(ids):
            comp.type('cmd %d' % i, rid=rid)
            self.assertEqual(cc.poll_once(), 1)
            self.assertLessEqual(len(cc.pending), MAX_PENDING)
            self.assertLessEqual(len(cc._order), MAX_PENDING)
        # Bounded, and both structures stay in lockstep (no hidden growth).
        self.assertEqual(len(cc.pending), MAX_PENDING)
        self.assertEqual(len(cc._order), MAX_PENDING)
        self.assertEqual(set(cc.pending), set(cc._order))
        self.assertEqual(len(set(cc._order)), MAX_PENDING)
        # Oldest-dropped FIFO with an explicit counter: 6 evicted.
        dropped = total - len(cc.pending)
        self.assertEqual(dropped, 6)
        for rid in ids[:dropped]:
            self.assertNotIn(rid, cc.pending)
        for rid in ids[dropped:]:
            self.assertIn(rid, cc.pending)
        self.assertEqual(cc._order[0], ids[dropped])
        self.assertEqual(cc._order[-1], ids[-1])
        # A second flood still cannot grow either structure.
        extra = [_rid(9000 + i) for i in range(MAX_PENDING)]
        for rid in extra:
            comp.type('more %s' % rid, rid=rid)
            cc.poll_once()
        self.assertEqual(len(cc.pending), MAX_PENDING)
        self.assertEqual(len(cc._order), MAX_PENDING)

    def test_duplicate_after_overflow_neither_grows_nor_evicts(self):
        from src.runtime.companion_commands import MAX_PENDING
        srv, comp, cc = self.make_cc()
        ids = [_rid(2000 + i) for i in range(MAX_PENDING)]
        for rid in ids:
            comp.type('cmd %s' % rid, rid=rid)
            cc.poll_once()
        self.assertEqual(len(cc.pending), MAX_PENDING)
        before = list(cc._order)
        survivor = before[0]
        comp.queue.append({'request_id': survivor, 'text': 'cmd again',
                           'lang': 'en', 'quality': 'auto'})
        self.assertEqual(cc.poll_once(), 0)
        self.assertEqual(len(cc.pending), MAX_PENDING)
        self.assertEqual(cc._order, before)
        self.assertIn(survivor, cc.pending)

    def test_oversize_device_batch_refused_without_queue_growth(self):
        srv, comp, cc = self.make_cc()
        for i in range(9):  # device MAX_COMMANDS is 8
            comp.type('cmd %d' % i, rid=_rid(5000 + i))
        self.assertEqual(cc.poll_once(), 0)
        self.assertEqual(cc.pending, {})
        self.assertEqual(cc._order, [])
        self.assertEqual(comp.reports, [])
        with self.assertRaises(R.RelayError):
            R.validate_commands({'commands': [
                {'request_id': _rid(6000 + i), 'text': 'x', 'lang': 'en',
                 'quality': 'auto'} for i in range(9)]})


class UnreachableHonestEscalationTests(unittest.TestCase):
    """Unreachable relays fail honestly at every layer; nothing fakes success."""

    def test_scan_transport_errors_are_honest_and_offline_after_three(self):
        for err in (OSError('refused'), TimeoutError(),
                    ConnectionResetError('reset'), ConnectionRefusedError('down')):
            with self.subTest(err=type(err).__name__):
                m = manager(FakeRelay(fail=err))
                for attempt in range(1, 4):
                    with self.assertRaises(R.RelayError) as ctx:
                        m.scan()
                    self.assertIn('unreachable', str(ctx.exception).lower())
                    self.assertEqual(m.relays['tv']['failures'], attempt)
                    self.assertFalse(m.relays['tv']['busy'])
                self.assertFalse(m.relays['tv']['online'])
                self.assertEqual(m.eligible('ble_scan'), [])

    def test_companion_poll_unreachable_marks_offline_without_phantom(self):
        from src.runtime.companion_commands import CompanionCommands
        srv, comp = cmd_server()
        comp.type('Start my vacuum', rid=_rid(7001))

        def dead(relay, msg):
            raise OSError('companion closed')

        srv.relays.relays['r-phone']['send'] = dead
        cc = CompanionCommands(srv, low=FakeTransport(good_reply()),
                               medium=FakeTransport(good_reply()))
        self.assertEqual(cc.poll_once(), 0)
        self.assertEqual(cc.pending, {})
        self.assertEqual(comp.reports, [])
        self.assertFalse(srv.relays.relays['r-phone']['online'])
        # Offline relays are skipped, still with no phantom work.
        self.assertEqual(cc.poll_once(), 0)
        self.assertEqual(cc.pending, {})
        # Recovery is explicit: back online, the retained + new commands flow.
        # (The first get_commands never reached the device, so 7001 is still
        # queued there; nothing was lost or phantom-completed while down.)
        srv.relays.relays['r-phone']['send'] = comp
        srv.relays.relays['r-phone']['online'] = True
        comp.type('Start my vacuum', rid=_rid(7002))
        self.assertEqual(cc.poll_once(), 2)
        self.assertIn(_rid(7001), cc.pending)
        self.assertIn(_rid(7002), cc.pending)

    def test_drain_unreachable_and_parse_failures_are_honest(self):
        from src.runtime import command as CMD
        from src.runtime import command_drain as D

        def dtext(rid, text='allume la lampe du salon'):
            return {'request_id': rid, 'kind': 'text', 'text': text,
                    'lang': 'fr', 'quality': 'auto'}

        # Unreachable get_commands: error stats, no report, no raise.
        fake = DrainFake([dtext(_rid(8001))], fail_ops=('get_commands',))
        stats = D.poll_once(drain_server(fake),
                            parse_fn=lambda s, b: {'intent': {'status': 'resolved'}},
                            sync=True)
        self.assertEqual(stats['commands'], 0)
        self.assertEqual(stats['reported'], 0)
        self.assertTrue(stats['errors'])
        self.assertEqual(fake.reports, [])

        # Parse failure: exactly one honest escalation report, never resolved.
        fake2 = DrainFake([dtext(_rid(8002), '???')])

        def bad_parse(s, b):
            raise CMD.CommandError(400, 'text must be 1..2000 characters')

        stats2 = D.poll_once(drain_server(fake2), parse_fn=bad_parse, sync=True)
        self.assertEqual(stats2['commands'], 1)
        self.assertEqual(stats2['reported'], 1)
        self.assertEqual(stats2['errors'], [])
        self.assertEqual(len(fake2.reports), 1)
        rid, status, text = fake2.reports[0]
        self.assertEqual(rid, _rid(8002))
        self.assertEqual(status, 'escalation_required')
        self.assertIn('Could not parse', text)

        # Report failure: counted, not crashed, not phantom-reported.
        fake3 = DrainFake([dtext(_rid(8003))], fail_ops=('report_command',))
        stats3 = D.poll_once(drain_server(fake3),
                             parse_fn=lambda s, b: {'intent': {'status': 'resolved'}},
                             sync=True)
        self.assertEqual(stats3['commands'], 1)
        self.assertEqual(stats3['reported'], 0)
        self.assertTrue(stats3['errors'])

    def test_server_scan_unreachable_is_honest_and_signed_status_recovers(self):
        from src.server import create_server
        key = R.derive_key('123456', 'rn', 'pn')
        server = create_server(0, fabric_salt=b's',
                               session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        self.addCleanup(server.server_close)
        reg = Registry()
        tv = reg.upsert([], category='tv', label='TV')
        reg.devices[tv]['handles'] = {'WIFI': 'dev-tv'}
        server.fabric_registry = reg
        server.fabric_snapshot = reg.snapshot()
        server.relays.enroll('tv', key, 'dev-tv',
                             {'capabilities': ['ble_scan'],
                              'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})

        def dead(relay, msg):
            raise ConnectionRefusedError('companion closed')

        server.relays.relays['tv']['send'] = dead
        with self.assertRaises(R.RelayError) as ctx:
            server.relay_action('/api/relay-scan', {'relay_id': 'tv'})
        self.assertIn('unreachable', str(ctx.exception).lower())
        relay = server.relays.relays['tv']
        self.assertFalse(relay['online'])
        self.assertEqual(server.relay_ledger.routes['tv']['failures'], 1)
        self.assertEqual((relay['key'], relay['device_key']), (key, 'dev-tv'))

        obs = [{'address': 'C1:22:33:44:55:66', 'name': 'Thermo', 'rssi': -71,
                'company_ids': [76], 'address_kind': 'static_random'}]

        def alive(relay_obj, message):
            msg = R.verify(key, message, {})
            if msg['op'] == 'get_status':
                params = {'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}}
            elif msg['op'] == 'start_discovery':
                params = {'observations': obs}
            elif msg['op'] == 'stop_discovery':
                params = {}
            else:
                raise AssertionError('unexpected op ' + msg['op'])
            now = int(time.time())
            reply = {'protocol': R.PROTOCOL, 'relay_id': 'tv', 'op': 'reply',
                     'params': params, 'nonce': 'r' + msg['nonce'],
                     'issued_at': now, 'expires_at': now + 30}
            return {**reply, 'mac': R.sign(key, reply)}

        server.relays.relays['tv']['send'] = alive
        snap = server.relay_action('/api/relay-scan', {'relay_id': 'tv', 'seconds': 5})
        self.assertTrue(server.relays.relays['tv']['online'])
        child = [d for d in snap['devices'] if d['label'] == 'Thermo'][0]
        link = [l for l in snap['links'] if l['child'] == child['key']][0]
        self.assertEqual(link['grants'], ['observe'])
        self.assertEqual(link['source'], 'RELAY:tv')


if __name__ == '__main__':
    unittest.main()
