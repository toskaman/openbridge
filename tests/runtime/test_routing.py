"""B2 runtime routing (SIMULATED_VERIFIED: synthetic registry/relays, fake device runners; no hardware or model calls).
Every skill_routes document produced here is validated against the B2 rev 2 schema and cross-field rules."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace

from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.fabric.registry import Registry
from src.fabric.relay import RelayManager
from src.fabric.session import SessionJournal
from src.runtime import route_contract as rc
from src.runtime.api_v2 import executor, get, post, router
from src.runtime.primitives import Executor
from src.runtime.relay_health import RelayLedger
from src.runtime.routing import RouteError


class Clock:
    def __init__(self, t=1_793_100_000.0):
        self.t = t

    def __call__(self):
        return self.t


def world(clock):
    reg = Registry()
    keys = {}
    for name, cat, serial, transport, grants in (('Android TV', 'tv', 'tv-1', 'WIFI', ('observe', 'read', 'control')),
                                                 ('BV9300_Pro', 'phone', 'ph-1', 'USB', ('observe', 'read', 'control'))):
        k = reg.upsert([Identifier('android_serial', serial, True)], category=cat, label=name,
                       observations=[DeviceObservation('model', name, 'ADB', transport, now(), True)])
        reg.devices[k]['handles'] = {transport: 'h-' + serial}
        reg.link(Link('pc', k, transport, grants, 'ADB:device'))
        keys[cat] = k
    relays = RelayManager(transport=lambda relay, msg: {})
    for rid, serial in (('r-tv', 'tv-1'), ('r-ph', 'ph-1')):
        relays.enroll(rid, b'k' * 32, 'h-' + serial, {'capabilities': ['ble_scan'], 'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
    led = RelayLedger(clock=clock)
    server = SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(), relays=relays, relay_ledger=led,
                             session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'), fabric_salt=b't', runtime_executor=None, skill_router=None)
    return server, keys


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        self.calls = []
        ex = executor(self.server)
        def fake(name):
            def run(self_, key, params):
                self.calls.append((name, key, params))
                return 'VERIFIED', None, {'ok': True}, True, {'ok': True}
            return run
        ex.RUNNERS = dict(Executor.RUNNERS, relay_ble_scan=fake('relay_ble_scan'), device_action=fake('device_action'), read_facts=fake('read_facts'))
        self.router = router(self.server)
        self.router.clock = self.clock
        self.server.relay_ledger.record('r-tv', []); self.clock.t += 5; self.server.relay_ledger.record('r-ph', [])   # phone fresher

    def routes(self, skill='ble_scan_room', target=None):
        doc = self.router.skill_routes(skill, target)
        self.assertEqual(rc.validate_doc(doc), [], json.dumps(doc, indent=1)[:2000])
        return doc

    def by_dev(self, doc, key):
        return next(r for r in doc['routes'] if r['hops'][0]['device_key'] == key)

    def arm(self, doc, params=None, skill='ble_scan_room', target=None):
        body = {'skill_id': skill, 'route_id': doc['selected_route_id'], 'params': params or {'seconds': 8}, 'consent': True}
        if target:
            body['target'] = target
        return self.router.arm(body)

    def invoke(self, lease, params=None, skill='ble_scan_room', target=None, **over):
        body = {'invocation_id': lease['invocation_id'], 'skill_id': skill, 'route_id': lease['route_id'], 'lease_id': lease['lease_id'],
                'graph_revision': lease['graph_revision'], 'params': params or {'seconds': 8}, 'consent': True, **over}
        if target:
            body['target'] = target
        return self.router.invoke(body)


class RouteTruth(Base):
    def test_zero_devices_is_an_honest_abstention(self):
        self.server.relays.relays.clear()
        doc = self.routes()
        self.assertEqual((doc['routes'], doc['selected_route_id'], doc['selection']['rule']), ([], None, 'none_eligible'))

    def test_auto_selects_freshest_relay_and_link_loss_flips_reason(self):
        doc = self.routes()
        self.assertEqual(doc['selection']['rule'], 'auto_score')
        self.assertEqual(self.by_dev(doc, self.keys['phone'])['route_id'], doc['selected_route_id'])
        self.server.relays.relays['r-ph']['online'] = False
        doc2 = self.routes()
        ph = self.by_dev(doc2, self.keys['phone'])
        self.assertEqual((ph['state'], ph['reason']), ('UNAVAILABLE', 'link_down'))
        self.assertEqual(self.by_dev(doc2, self.keys['tv'])['route_id'], doc2['selected_route_id'])
        self.assertGreater(doc2['graph_revision']['seq'], doc['graph_revision']['seq'])
        changed = [e for e in executor(self.server).events_since(0) if e['kind'] == 'route_changed']
        self.assertEqual(len(changed), 1)

    def test_missing_scan_permission_names_the_hop_and_stale_lease(self):
        self.server.relays.relays['r-tv']['permissions']['BLUETOOTH_SCAN'] = False
        tv = self.by_dev(self.routes(), self.keys['tv'])
        self.assertEqual(tv['reason'], 'grant_insufficient')
        self.assertEqual(tv['reason_detail'], {'missing_grant': 'control', 'hop_index': 1, 'blocking_device_key': self.keys['tv']})
        self.clock.t += 500                                   # relay leases are 120 s
        doc = self.routes()
        self.assertTrue(all(r['reason'] == 'lease_stale' for r in doc['routes'] if r['hops'][0]['device_key'] == self.keys['phone']))
        self.assertIsNone(doc['selected_route_id'])

    def test_pinned_has_no_fallback_and_preferred_is_respected(self):
        tv_route = self.by_dev(self.routes(), self.keys['tv'])['route_id']
        self.router.set_policy({'skill_id': 'ble_scan_room', 'mode': 'PINNED', 'route_id': tv_route})
        doc = self.routes()
        self.assertEqual(doc['selected_route_id'], tv_route)
        self.assertEqual(self.by_dev(doc, self.keys['phone'])['state'], 'STANDBY')
        self.server.relays.relays['r-tv']['online'] = False
        doc = self.routes()
        self.assertIsNone(doc['selected_route_id'])           # pinned route down: no fallback
        self.assertEqual(self.by_dev(doc, self.keys['phone'])['state'], 'STANDBY')
        self.server.relays.relays['r-tv']['online'] = True
        self.router.set_policy({'skill_id': 'ble_scan_room', 'mode': 'PREFERRED', 'preferred': [tv_route]})
        self.assertEqual(self.routes()['selected_route_id'], tv_route)   # despite the phone being fresher

    def test_failover_only_for_idempotent_reads(self):
        with self.assertRaises(RouteError):
            self.router.set_policy({'skill_id': 'tv_volume_step', 'mode': 'AUTO', 'failover': 'idempotent_read_retry'})
        self.router.set_policy({'skill_id': 'device_facts', 'mode': 'AUTO', 'failover': 'idempotent_read_retry'})
        doc = self.routes('device_facts', self.keys['tv'])
        self.assertEqual(doc['policy']['failover'], 'idempotent_read_retry')

    def test_exact_volume_needs_a_measured_range(self):
        doc = self.routes('tv_volume_set', self.keys['tv'])
        r = doc['routes'][0]
        self.assertEqual((r['state'], r['reason'], r['exactness']), ('UNAVAILABLE', 'dependency_unready', None))
        executor(self.server).probes = {self.keys['tv']: {'ranges': {'media_volume': [0, 15]}}}
        r = self.routes('tv_volume_set', self.keys['tv'])['routes'][0]
        self.assertEqual(r['state'], 'READY'); self.assertEqual(r['exactness']['range'], [0, 15])
        step = self.routes('tv_volume_step', self.keys['tv'])
        self.assertEqual(step['skill']['reversibility'], 'IRREVERSIBLE'); self.assertIn('key_volume', step['routes'][0]['operation_id'])
        with self.assertRaises(RouteError):
            self.router.skill_routes('tv_volume_set')        # targeted skill needs a target


class Invocation(Base):
    def test_arm_invoke_retry_and_new_press(self):
        doc = self.routes()
        lease = self.arm(doc)
        armed = self.routes()
        self.assertEqual(armed['invocation']['status'], 'armed')
        self.assertEqual([r['consent'] for r in armed['routes'] if r['consent'] == 'armed'], ['armed'])
        self.assertEqual(armed['delivery']['poll_after_s'], 2)
        r1 = self.invoke(lease)
        self.assertEqual(r1['state'], 'VERIFIED'); self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][2], {'relay_id': 'r-ph', 'seconds': 8})
        r2 = self.invoke(lease)                               # network retry: same outcome, no second dispatch
        self.assertEqual(r2['transaction_id'], r1['transaction_id']); self.assertEqual(len(self.calls), 1)
        with self.assertRaises(RouteError) as e:              # same id, changed params: rejected
            self.invoke(lease, {'seconds': 9})
        self.assertEqual(e.exception.code, 'INVOCATION_ID_REUSED'); self.assertEqual(len(self.calls), 1)
        self.invoke(self.arm(self.routes()))                  # a deliberate second scan = new consent, new id
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.routes()['invocation']['status'], 'idle')

    def test_consent_voids_on_route_change_authority_lease_and_params(self):
        def expect_void(mutate, params=None):
            lease = self.arm(self.routes())
            mutate()
            with self.assertRaises(RouteError) as e:
                self.invoke(lease, params)
            self.assertIn(e.exception.code, ('CONSENT_VOID',))
            self.assertEqual(self.calls, [])
        expect_void(lambda: self.server.relays.relays['r-ph'].__setitem__('online', False))       # route changed
        self.server.relays.relays['r-ph']['online'] = True
        def revoke():
            snap = self.server.fabric_snapshot
            for l in snap['links']:
                if l['child'] == self.keys['phone']:
                    l['grants'] = ['observe', 'read']
        expect_void(revoke)                                                                      # grant revoked
        self.server.fabric_snapshot = self.server.fabric_registry.snapshot()
        expect_void(lambda: self.server.fabric_snapshot['links'].append(
            {'parent': 'pc', 'child': self.keys['phone'], 'transport': 'LAN', 'grants': ['observe'], 'source': 'MDNS'}))  # authority changed, route still selected
        self.server.fabric_snapshot = self.server.fabric_registry.snapshot()
        expect_void(lambda: setattr(self.clock, 't', self.clock.t + 31))                          # lease expired
        self.server.relay_ledger.record('r-ph', [])
        expect_void(lambda: None, {'seconds': 3})                                                 # params edited after consent

    def test_arm_requires_consent_and_selected_route(self):
        doc = self.routes()
        with self.assertRaises(RouteError):
            self.router.arm({'skill_id': 'ble_scan_room', 'route_id': doc['selected_route_id'], 'params': {}, 'consent': False})
        other = next(r['route_id'] for r in doc['routes'] if r['route_id'] != doc['selected_route_id'])
        with self.assertRaises(RouteError) as e:
            self.router.arm({'skill_id': 'ble_scan_room', 'route_id': other, 'params': {}, 'consent': True})
        self.assertEqual(e.exception.code, 'ROUTE_NOT_SELECTED')
        with self.assertRaises(RouteError):
            self.router.arm({'skill_id': 'ble_scan_room', 'route_id': doc['selected_route_id'], 'params': {'seconds': 99}, 'consent': True})

    def test_unknown_or_forged_invocation_is_refused(self):
        lease = self.arm(self.routes())
        with self.assertRaises(RouteError):
            self.invoke(dict(lease, invocation_id='inv-' + '0' * 32))
        with self.assertRaises(RouteError):
            self.router.invoke({'invocation_id': 'x'})
        self.assertEqual(self.calls, [])

    def test_concurrent_retries_dispatch_once(self):
        lease = self.arm(self.routes())
        gate = threading.Event()
        ex = executor(self.server)
        def slow(self_, key, params):
            gate.wait(5); self.calls.append('scan'); return 'VERIFIED', None, {}, True, {}
        ex.RUNNERS = dict(ex.RUNNERS, relay_ble_scan=slow)
        out = []
        ths = [threading.Thread(target=lambda: out.append(self.invoke(lease))) for _ in range(6)]
        for t in ths: t.start()
        threading.Event().wait(0.2); gate.set()
        for t in ths: t.join(5)
        self.assertEqual(self.calls, ['scan']); self.assertEqual(len({o['transaction_id'] for o in out}), 1)

    def test_volume_set_dispatches_exact_set_with_readback(self):
        executor(self.server).probes = {self.keys['tv']: {'ranges': {'media_volume': [0, 15]}}}
        doc = self.routes('tv_volume_set', self.keys['tv'])
        lease = self.arm(doc, {'value': 7}, 'tv_volume_set', self.keys['tv'])
        self.invoke(lease, {'value': 7}, 'tv_volume_set', self.keys['tv'])
        self.assertEqual(self.calls[-1][2], {'action': 'set', 'args': {'setting': 'media_volume', 'value': 7}})


class Http(unittest.TestCase):
    def test_routes_over_http_and_csrf(self):
        from src.server import create_server
        s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{s.server_port}'
        try:
            doc = json.loads(urllib.request.urlopen(base + '/api/v2/skill_routes?skill=ble_scan_room').read())
            self.assertEqual(rc.validate_doc(doc), [])
            self.assertIn('ble_scan_room', [k['skill_id'] for k in json.loads(urllib.request.urlopen(base + '/api/v2/skills').read())['skills']])
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + '/api/v2/skill_routes?skill=nope')
            self.assertEqual(e.exception.code, 404); e.exception.close()
            req = urllib.request.Request(base + '/api/v2/skill_arm', json.dumps({'skill_id': 'ble_scan_room', 'consent': True}).encode(), {'Content-Type': 'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 403); e.exception.close()
            csrf = json.loads(urllib.request.urlopen(base + '/api/session').read())['csrf_token']
            req = urllib.request.Request(base + '/api/v2/skill_arm', json.dumps({'skill_id': 'ble_scan_room', 'route_id': 'rt-0000000000000000', 'consent': True}).encode(),
                                         {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Origin': base})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 409); e.exception.close()
        finally:
            s.shutdown(); s.server_close()


if __name__ == '__main__':
    unittest.main()


class Stability(Base):
    def test_never_scanned_relays_do_not_flap(self):
        fresh = world(self.clock)[0]                       # new server: no relay has scanned yet
        ex = executor(fresh); r = router(fresh)
        ticking = [self.clock.t]
        calls = [0]
        def tick():                                        # coarse OS timer: sometimes equal, sometimes one 15.6 ms step apart
            calls[0] += 1
            if calls[0] % 3 == 0:
                ticking[0] += 0.0156
            return ticking[0]
        r.clock = tick
        sels = set()
        for i in range(20):
            doc = r.skill_routes('ble_scan_room')
            self.assertEqual(rc.validate_doc(doc), [])
            sels.add(doc['selected_route_id'])
        self.assertEqual(len(sels), 1)
        self.assertEqual([e for e in ex.events_since(0) if e['kind'] == 'route_changed'], [])


class UncertainOutcome(Base):
    def test_timeout_makes_route_unknown_until_a_later_success(self):
        from src.runtime.contract import TransactionReceipt
        ex = executor(self.server)
        ph = self.keys['phone']
        t_fail = '2026-10-28T09:00:00+00:00'
        ex.receipts['tx-aaaaaaaaaaaaaaaa'] = TransactionReceipt('tx-aaaaaaaaaaaaaaaa', 'relay_ble_scan', ph, 'UNKNOWN_TIMEOUT', None, None, False, t_fail, t_fail, ())
        self.clock.t = 1_793_181_000.0                       # just after the timeout; last ledger success is older
        doc = self.routes()
        r = self.by_dev(doc, ph)
        self.assertEqual((r['state'], r['reason']), ('UNAVAILABLE', 'backend_unknown'))
        self.server.relay_ledger.record('r-ph', [])          # a successful scan after the timeout resolves it
        self.assertEqual(self.by_dev(self.routes(), ph)['state'], 'READY')


class LeaseProof(Base):
    def test_signed_reply_reproves_a_stale_relay_route(self):
        self.clock.t += 500                                   # both scans are older than the 120 s relay lease
        self.assertIsNone(self.routes()['selected_route_id'])
        self.server.relay_ledger.proved('r-tv')               # pairing confirmation / status read-back
        doc = self.routes()
        tv = self.by_dev(doc, self.keys['tv'])
        self.assertEqual((tv['state'], doc['selected_route_id']), ('READY', tv['route_id']))
        self.assertEqual(self.by_dev(doc, self.keys['phone'])['reason'], 'lease_stale')
