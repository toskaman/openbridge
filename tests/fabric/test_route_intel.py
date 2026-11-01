"""Adaptive Route Intelligence (Campaign Two S4.4). Simulated relays only: no
network, no ADB, no hardware. Every transport below is an in-memory fake."""
import time
import unittest

from src.fabric import relay as R
from src.fabric.route_intel import (
    ACKED, NOT_SENT, REFUSED_KNOWN, UNCERTAIN, RouteIntel, UncertainOutcome,
)

PHONE_KEY = R.derive_key('111111', 'rn-phone', 'pn')
TV_KEY = R.derive_key('222222', 'rn-tv', 'pn')
TARGET = 'ble:C1:22:33:44:55:66'


class SimRelay:
    """In-memory relay: verifies commands, answers signed replies. Behaviour
    switches: fail (raise on send), tamper (break reply MAC), refuse (protocol
    RelayError instead of a reply). Counts every send per nonce."""

    def __init__(self, key, fail=None, tamper=False, refuse=None):
        self.key = key
        self.fail = fail
        self.tamper = tamper
        self.refuse = refuse
        self.seen = {}
        self.sends = []          # every envelope handed to the transport
        self.ops = []

    def __call__(self, entry, message):
        self.sends.append(message)
        if self.fail:
            raise self.fail
        if self.refuse:
            raise R.RelayError(self.refuse)
        msg = R.verify(self.key, message, self.seen)
        self.ops.append(msg['op'])
        params = {'observations': []} if msg['op'] == 'start_discovery' else {'ok': True}
        now = int(time.time())
        reply = {'protocol': R.PROTOCOL, 'relay_id': msg['relay_id'], 'op': 'reply',
                 'params': params, 'nonce': 'r' + msg['nonce'],
                 'issued_at': now, 'expires_at': now + 30}
        mac = R.sign(self.key, reply)
        if self.tamper:
            mac = '0' * 64
        return {**reply, 'mac': mac}


def _manager(phone, tv, phone_battery=True):
    m = R.RelayManager(lambda entry, msg: entry['sim'](entry, msg))
    m.enroll('phone', PHONE_KEY, 'dev-phone',
             {'capabilities': ['ble_scan'],
              'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True},
              'battery_powered': phone_battery})
    m.enroll('tv', TV_KEY, 'dev-tv',
             {'capabilities': ['ble_scan'],
              'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
    m.relays['phone']['sim'] = phone
    m.relays['tv']['sim'] = tv
    return m


def _intel(phone=None, tv=None, **kw):
    phone = phone if phone is not None else SimRelay(PHONE_KEY)
    tv = tv if tv is not None else SimRelay(TV_KEY)
    return RouteIntel(_manager(phone, tv, **kw)), phone, tv


class EnumerationTests(unittest.TestCase):
    def test_enumerates_multiple_valid_routes_pc_phone_and_pc_tv(self):
        intel, _, _ = _intel()
        routes = intel.routes_for(TARGET)
        self.assertEqual([r.relay_id for r in routes], ['tv', 'phone'])
        self.assertEqual(routes[0].hops, ('pc', 'tv', TARGET))
        self.assertEqual(routes[1].hops, ('pc', 'phone', TARGET))
        self.assertEqual([r.rank for r in routes], [0, 1])

    def test_mains_powered_relay_preferred_over_battery(self):
        intel, _, _ = _intel(phone_battery=True)
        self.assertEqual(intel.select(TARGET).relay_id, 'tv')
        intel, _, _ = _intel(phone_battery=False)
        # Tie on power: deterministic id order.
        self.assertEqual([r.relay_id for r in intel.routes_for(TARGET)],
                         ['phone', 'tv'])

    def test_relays_without_permission_or_consent_yield_no_valid_route(self):
        m = R.RelayManager(lambda e, msg: {})
        m.enroll('phone', PHONE_KEY, 'dev', {'capabilities': ['ble_scan'],
                 'permissions': {'BLUETOOTH_SCAN': False, 'owner_enabled': True}})
        m.enroll('tv', TV_KEY, 'dev', {'capabilities': [],
                 'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        intel = RouteIntel(m)
        self.assertEqual(intel.routes_for(TARGET), [])
        self.assertIsNone(intel.select(TARGET))

    def test_bad_target_rejected(self):
        intel, _, _ = _intel()
        for bad in ('', '   ', None, 42):
            with self.assertRaises(ValueError):
                intel.routes_for(bad)


class DisappearanceTests(unittest.TestCase):
    def test_simulated_loss_of_preferred_relay_selects_alternate(self):
        intel, _, _ = _intel()
        sim = intel.simulate_loss(TARGET, 'tv')
        self.assertEqual(sim.lost.relay_id, 'tv')
        self.assertEqual(sim.alternate.relay_id, 'phone')
        self.assertEqual(sim.alternate.hops, ('pc', 'phone', TARGET))
        self.assertEqual([r.relay_id for r in sim.remaining], ['phone'])

    def test_simulation_is_pure_manager_state_untouched(self):
        intel, _, _ = _intel()
        before = {rid: dict(v, seen=None) for rid, v in intel.manager.relays.items()}
        intel.simulate_loss(TARGET, 'tv')
        after = {rid: dict(v, seen=None) for rid, v in intel.manager.relays.items()}
        self.assertEqual(
            {k: {kk: vv for kk, vv in v.items() if kk != 'seen'} for k, v in before.items()},
            {k: {kk: vv for kk, vv in v.items() if kk != 'seen'} for k, v in after.items()})
        self.assertTrue(intel.manager.relays['tv']['online'])
        # And enumeration without the simulation still prefers tv.
        self.assertEqual(intel.select(TARGET).relay_id, 'tv')

    def test_loss_of_all_relays_leaves_no_route(self):
        intel, _, _ = _intel()
        sim = intel.simulate_loss(TARGET, 'tv', down=('phone',))
        self.assertIsNone(sim.alternate)
        self.assertEqual(sim.remaining, [])

    def test_real_offline_relay_is_excluded(self):
        intel, _, _ = _intel()
        intel.manager.relays['tv']['online'] = False
        self.assertEqual(intel.select(TARGET).relay_id, 'phone')


class DispatchTests(unittest.TestCase):
    def test_success_dispatches_once_on_preferred_route(self):
        intel, phone, tv = _intel()
        rec = intel.dispatch(TARGET, 'get_status')
        self.assertEqual(rec.outcome, ACKED)
        self.assertEqual(rec.route.relay_id, 'tv')
        self.assertEqual(len(tv.sends), 1)
        self.assertEqual(len(phone.sends), 0)
        self.assertEqual(rec.reply, {'ok': True})

    def test_no_route_is_not_sent_and_transmits_nothing(self):
        intel, phone, tv = _intel()
        rec = intel.dispatch(TARGET, 'get_status', down=('tv', 'phone'))
        self.assertEqual(rec.outcome, NOT_SENT)
        self.assertIsNone(rec.route)
        self.assertEqual(phone.sends + tv.sends, [])

    def test_busy_preferred_relay_is_not_sent_without_transmitting(self):
        intel, phone, tv = _intel()
        intel.manager.relays['tv']['busy'] = True
        rec = intel.dispatch(TARGET, 'get_status', relay_id='tv')
        self.assertEqual(rec.outcome, NOT_SENT)
        self.assertEqual(phone.sends + tv.sends, [])

    def test_invalid_operation_is_not_sent(self):
        intel, phone, tv = _intel()
        rec = intel.dispatch(TARGET, 'shell')
        self.assertEqual(rec.outcome, NOT_SENT)
        self.assertEqual(phone.sends + tv.sends, [])

    def test_relay_protocol_refusal_is_known_not_uncertain(self):
        intel, phone, tv = _intel(tv=SimRelay(TV_KEY, refuse='Relay refused: nope'))
        rec = intel.dispatch(TARGET, 'get_status')
        self.assertEqual(rec.outcome, REFUSED_KNOWN)
        self.assertEqual(len(tv.sends), 1)
        self.assertNotIn(rec.command['nonce'], intel.uncertain)


class AtMostOnceTests(unittest.TestCase):
    """The load-bearing property: UNCERTAIN commands are never reissued."""

    def test_timeout_marks_uncertain_and_failover_refuses_without_transmit(self):
        intel, phone, tv = _intel(tv=SimRelay(TV_KEY, fail=TimeoutError()))
        rec = intel.dispatch(TARGET, 'get_status')
        self.assertEqual(rec.outcome, UNCERTAIN)
        self.assertIn(rec.command['nonce'], intel.uncertain)
        self.assertFalse(intel.reissue_allowed(rec.command))
        sends_before = len(tv.sends) + len(phone.sends)
        self.assertEqual(sends_before, 1)
        with self.assertRaises(UncertainOutcome):
            intel.failover(rec)
        # Refusal transmitted nothing: still exactly the one original send.
        self.assertEqual(len(tv.sends) + len(phone.sends), 1)

    def test_oserror_marks_uncertain_and_failover_refuses(self):
        intel, phone, tv = _intel(tv=SimRelay(TV_KEY, fail=OSError('link down')))
        rec = intel.dispatch(TARGET, 'get_status')
        self.assertEqual(rec.outcome, UNCERTAIN)
        with self.assertRaises(UncertainOutcome):
            intel.failover(rec, down=('tv',))
        self.assertEqual(len(tv.sends) + len(phone.sends), 1)

    def test_tampered_reply_marks_uncertain_and_failover_refuses(self):
        intel, phone, tv = _intel(tv=SimRelay(TV_KEY, tamper=True))
        rec = intel.dispatch(TARGET, 'get_status')
        self.assertEqual(rec.outcome, UNCERTAIN)
        with self.assertRaises(UncertainOutcome):
            intel.failover(rec)
        self.assertEqual(len(tv.sends) + len(phone.sends), 1)

    def test_quarantined_envelope_is_rejected_even_on_direct_resend_attempt(self):
        intel, _, _ = _intel(tv=SimRelay(TV_KEY, fail=TimeoutError()))
        rec = intel.dispatch(TARGET, 'get_status')
        with self.assertRaises(UncertainOutcome):
            intel.assert_fresh(rec.command)

    def test_only_the_uncertain_command_is_quarantined_not_the_route(self):
        bad_tv = SimRelay(TV_KEY, fail=TimeoutError())
        intel, phone, tv = _intel(tv=bad_tv)
        rec = intel.dispatch(TARGET, 'get_status')
        self.assertEqual(rec.outcome, UNCERTAIN)
        # Fresh probe (new nonce) reconciles fine over the now-healthy relay.
        bad_tv.fail = None
        probe = intel.dispatch(TARGET, 'get_status')
        self.assertEqual(probe.outcome, ACKED)
        self.assertNotEqual(probe.command['nonce'], rec.command['nonce'])

    def test_refused_and_acked_records_cannot_fail_over(self):
        intel, _, _ = _intel(tv=SimRelay(TV_KEY, refuse='Relay refused: nope'))
        refused = intel.dispatch(TARGET, 'get_status')
        with self.assertRaises(ValueError):
            intel.failover(refused)
        intel2, _, _ = _intel()
        acked = intel2.dispatch(TARGET, 'get_status')
        with self.assertRaises(ValueError):
            intel2.failover(acked)


class SafeFailoverTests(unittest.TestCase):
    def test_not_sent_fails_over_with_fresh_command_on_alternate(self):
        intel, phone, tv = _intel()
        intel.manager.relays['tv']['busy'] = True   # pre-send: nothing transmitted
        rec = intel.dispatch(TARGET, 'get_status', relay_id='tv')
        self.assertEqual(rec.outcome, NOT_SENT)
        self.assertEqual(tv.sends, [])
        alt = intel.failover(rec)
        self.assertEqual(alt.outcome, ACKED)
        self.assertEqual(alt.route.relay_id, 'phone')
        self.assertEqual(alt.route.hops, ('pc', 'phone', TARGET))
        self.assertEqual(len(phone.sends), 1)
        self.assertEqual(len(tv.sends), 0)
        # Fresh envelope, not the original: nonces differ.
        self.assertIsNotNone(rec.command)
        self.assertNotEqual(alt.command['nonce'], rec.command['nonce'])

    def test_not_sent_with_no_survivor_stays_not_sent(self):
        intel, phone, tv = _intel()
        rec = intel.dispatch(TARGET, 'get_status', down=('tv', 'phone'))
        alt = intel.failover(rec, down=('tv', 'phone'))
        self.assertEqual(alt.outcome, NOT_SENT)
        self.assertEqual(phone.sends + tv.sends, [])

    def test_end_to_end_preferred_loss_then_safe_redispatch(self):
        # Preferred relay disappears mid-incident; a NEW command (not a reissue
        # of anything uncertain) goes out once on the survivor.
        intel, phone, tv = _intel()
        sim = intel.simulate_loss(TARGET, 'tv')
        self.assertEqual(sim.alternate.relay_id, 'phone')
        rec = intel.dispatch(TARGET, 'start_discovery',
                             {'radio': 'ble', 'seconds': 5}, down=('tv',))
        self.assertEqual((rec.outcome, rec.route.relay_id), (ACKED, 'phone'))
        self.assertEqual(len(phone.sends), 1)
        self.assertEqual(len(tv.sends), 0)


if __name__ == '__main__':
    unittest.main()
