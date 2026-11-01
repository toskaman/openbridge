"""Campaign One section 3.4: instrumented probe of the historical 2-presses-to-16-executions report.

Historical record (28 Oct, Galaxy Watch7 -> Android TV, first B3 build): two injected
taps produced 16 executed volume steps over about 30 s, roughly one per poll, with the
watch off-wrist. First-build facts established from git history:

- The device queue already drained on get_requests (poll() removes each delivered
  request), one request was queued per tap with a 400 ms debounce, and the PC refused
  re-sent request ids through the singleton router's completed map plus a 0.5 s
  per-control interval. One request could only dispatch once.
- There was no hold-to-send (a tap sent), no burst limiter, and no per-request
  seq/gesture/touch evidence.

The pipeline-consistent explanation is therefore 16 distinct request ids (phantom taps
on the off-wrist watch), each dispatched exactly once: an input-layer storm, not a PC
re-dispatch defect. That explanation stays UNPROVEN because the first build recorded no
per-request evidence. This probe replays the historical shape (2 presses, 16 deliveries,
about 30 s, about 1 per poll) against CURRENT code with full instrumentation and
asserts the guards hold. The probe FAILS (defect reproduced) if physical executions
ever exceed the guard allowance.

Instrumentation per delivery: poll index, relay id, control id, request id, seq,
gesture, touch, pressed_at, invocation id, transaction id, outcome, plus
(fake-clock, wall-ns) stamps at admission, dispatch start/end and receipt.
"""
import threading
import time
import unittest

from src.fabric.contracts import DeviceObservation, Identifier, Link, now
from src.runtime.api_v2 import executor, remote_controls, router
from src.runtime.primitives import Executor
from src.runtime.routing import Router
from tests.runtime.test_remote_controls import KEY, FakeCompanion
from tests.runtime.test_routing import Clock, world


def _short(value, n=8):
    return None if value is None else str(value)[:n]


class Probe(unittest.TestCase):
    """Same doubles as the B3 suite (own TestCase so only probe tests run here)."""

    def setUp(self):
        self.clock = Clock()
        self.server, self.keys = world(self.clock)
        reg = self.server.fabric_registry
        w = reg.upsert([Identifier('android_serial', 'watch-1', True)], category='watch',
                       label='SM-L310',
                       observations=[DeviceObservation('model', 'SM-L310', 'ADB', 'WIFI', now(), True)])
        reg.devices[w]['handles'] = {'WIFI': 'h-watch-1'}
        reg.link(Link('pc', w, 'WIFI', ('observe', 'read', 'control'), 'ADB:device'))
        self.server.fabric_snapshot = reg.snapshot()
        self.companion = FakeCompanion()
        self.companion.clock = self.clock
        self.server.relays.enroll('r-watch', KEY, 'h-watch-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-watch']['send'] = self.companion
        self.calls = []
        router(self.server).clock = self.clock
        self.rc = remote_controls(self.server)
        self.rc.clock = self.clock
        self.rc._ensure_thread = lambda: None          # tests drive poll_once() directly
        self.rows = []          # one instrumented row per process() call
        self.poll_idx = 0
        self.dispatches = []    # one row per physical device action
        calls = self.calls

        def fake_runner(self_, key, params):
            calls.append((key, params))
            return 'EXECUTED', None, None, True, {}

        executor(self.server).RUNNERS = dict(Executor.RUNNERS, device_action=fake_runner)
        orig_dispatch = self.rc._dispatch
        probe = self

        def traced_dispatch(rid, req, grant, actor, entry):
            entry['t_dispatch_start'] = (probe.clock.t, time.perf_counter_ns())
            try:
                return orig_dispatch(rid, req, grant, actor, entry)
            finally:
                entry['t_dispatch_end'] = (probe.clock.t, time.perf_counter_ns())
                probe.dispatches.append({'poll': probe.poll_idx, 'relay_id': rid,
                                         'control_id': req['control_id'],
                                         'request_id': req['request_id'],
                                         'invocation_id': entry.get('invocation_id'),
                                         't_fake': probe.clock.t,
                                         't_wall_ns': time.perf_counter_ns()})

        orig_process = self.rc.process

        def traced_process(rid, req, origin='press'):
            t_admit = (probe.clock.t, time.perf_counter_ns())
            entry = orig_process(rid, req, origin=origin)
            entry['t_admit'] = t_admit
            entry['t_receipt'] = (probe.clock.t, time.perf_counter_ns())
            entry['poll'] = probe.poll_idx
            probe.rows.append(entry)
            return entry

        orig_poll = self.rc.poll_once

        def traced_poll():
            probe.poll_idx += 1
            return orig_poll()

        self.rc._dispatch = traced_dispatch
        self.rc.process = traced_process
        self.rc.poll_once = traced_poll

    def grant(self, controls, consent=True):
        return self.rc.set_controls({'relay_id': 'r-watch', 'controls': controls, 'consent': consent})

    def vol_up(self):
        st = self.grant([{'label': 'TV volume +', 'skill_id': 'tv_volume_step',
                          'target': self.keys['tv'], 'params': {'direction': 'up'}}])
        return st['controls'][0]['control_id']

    def trace_table(self):
        lines = ['poll relay control request seq gesture pressed_at outcome inv tx t_admit']
        for r in self.rows:
            lines.append('%s %s %s %s %s %s %s %s %s %s %s' % (
                r.get('poll'), r.get('relay_id'), _short(r.get('control_id')),
                _short(r.get('request_id')), r.get('seq'), r.get('gesture'),
                r.get('pressed_at'), r.get('state'), _short(r.get('invocation_id')),
                _short(r.get('transaction_id')),
                r.get('t_admit', (None,))[0]))
        return '\n'.join(lines)

    def verdict(self, name, executions, deliveries):
        print('\n[C1-3.4 %s] deliveries=%d executions=%d outcomes=%s' % (
            name, deliveries, executions,
            {s: sum(1 for r in self.rows if r['state'] == s) for s in sorted({r['state'] for r in self.rows})}))
        print(self.trace_table())


class ReplayStuckQueue(Probe):
    """Variant A: the same 2 request ids redelivered 8 times each (16 deliveries).

    Models a stuck device queue / transport replay. Dedup plus the journal claim must
    hold the line at exactly 2 executions; the other 14 deliveries are DUPLICATE and
    must not pollute the burst window.
    """

    def test_two_ids_replayed_8x_each_execute_exactly_twice(self):
        cid = self.vol_up()
        ids = ['%032x' % n for n in (0xA1, 0xB2)]
        for poll in range(8):   # one delivery per poll, like the historical run
            rid = ids[poll % 2]
            self.companion.press(cid, request_id=rid, seq=(poll % 2) + 1, gesture='long_press',
                                 touch={'tool': 1, 'pressure': 0.5, 'size': 0.2, 'down_ms': 600})
            self.clock.t += 2.0
            self.rc.poll_once()
        # second copy of each id per round: 8 more polls of pure replays
        for poll in range(8):
            rid = ids[poll % 2]
            self.companion.press(cid, request_id=rid, seq=(poll % 2) + 1, gesture='long_press',
                                 touch={'tool': 1, 'pressure': 0.5, 'size': 0.2, 'down_ms': 600})
            self.clock.t += 2.0
            self.rc.poll_once()
        self.verdict('replay', len(self.calls), len(self.rows))
        self.assertEqual(len(self.rows), 16, self.trace_table())
        self.assertEqual(len(self.calls), 2, self.trace_table())
        states = [r['state'] for r in self.rows]
        self.assertEqual(states.count('EXECUTED') + states.count('VERIFIED'), 2, self.trace_table())
        self.assertEqual(states.count('DUPLICATE'), 14, self.trace_table())
        self.assertEqual(self.rc.state()['suspended'], [])   # replays never suspend a healthy control
        # One journal row per executed id: DONE, never re-claimable; both executions
        # carry distinct invocation and transaction ids.
        invs = [r['invocation_id'] for r in self.rows if r['state'] in ('EXECUTED', 'VERIFIED')]
        txs = [r['transaction_id'] for r in self.rows if r['state'] in ('EXECUTED', 'VERIFIED')]
        self.assertEqual(len(set(invs)), 2)
        self.assertEqual(len(set(txs)), 2)
        for row in self.rows:
            self.assertEqual(row['relay_id'], 'r-watch')
            self.assertEqual(row['control_id'], cid)
            self.assertIn('t_admit', row)
            self.assertIn('t_receipt', row)


class PhantomStorm(Probe):
    """Variant B: 16 DISTINCT request ids over ~30 s, one per poll (phantom taps).

    This is the pipeline-consistent shape of the 28 Oct report. The 3-in-10 s burst
    limiter must cap physical executions at 3 and SUSPEND the control; the remaining
    13 presses are refused without touching the device. Every row keeps its
    seq/gesture/touch evidence so a storm is distinguishable from a re-dispatch.
    """

    def test_sixteen_distinct_ids_over_30s_execute_at_most_3_then_suspend(self):
        cid = self.vol_up()
        for i in range(16):
            self.companion.press(cid, request_id='%032x' % (0xC000 + i), seq=i + 1,
                                 gesture='click',   # ghost taps are taps, not holds
                                 touch={'tool': 0, 'pressure': 0.1, 'size': 0.3, 'down_ms': 40})
            self.clock.t += 2.0
            self.rc.poll_once()
        self.verdict('phantom-storm', len(self.calls), len(self.rows))
        self.assertEqual(len(self.rows), 16, self.trace_table())
        self.assertLessEqual(len(self.calls), 3, self.trace_table())
        self.assertEqual(len(self.calls), 3, self.trace_table())
        states = [r['state'] for r in self.rows]
        self.assertEqual(states.count('SUSPENDED'), 13, self.trace_table())
        self.assertTrue(self.rc.state()['suspended'])
        # Evidence chain: every delivery keeps its own seq/gesture/touch; executed
        # rows additionally carry invocation + transaction ids.
        self.assertEqual([r['seq'] for r in self.rows], list(range(1, 17)))
        self.assertTrue(all(r['gesture'] == 'click' for r in self.rows))
        self.assertTrue(all(isinstance(r.get('touch'), dict) for r in self.rows))
        done = [r for r in self.rows if r['state'] in ('EXECUTED', 'VERIFIED')]
        self.assertEqual(len(done), 3)
        self.assertEqual(len({r['invocation_id'] for r in done}), 3)
        self.assertEqual(len({r['transaction_id'] for r in done}), 3)
        for row in done:
            self.assertIn('t_dispatch_start', row)
            self.assertIn('t_dispatch_end', row)
            self.assertLessEqual(row['t_admit'][0], row['t_dispatch_start'][0])
            self.assertLessEqual(row['t_dispatch_end'][0], row['t_receipt'][0])


class ConcurrentSamePress(Probe):
    """Variant C: the same request raced down the full press path on two threads."""

    def test_concurrent_same_request_dispatches_exactly_once(self):
        cid = self.vol_up()
        gate = threading.Event()
        ex = executor(self.server)

        def slow(self_, key, params):
            gate.wait(10)
            self.calls.append((key, params))
            return 'EXECUTED', None, None, True, {}

        ex.RUNNERS = dict(ex.RUNNERS, device_action=slow)
        req = {'request_id': '%032x' % 0xD00D, 'control_id': cid,
               'pressed_at': int(self.clock.t * 1000), 'seq': 7,
               'gesture': 'long_press'}
        out, errs = [], []

        def run():
            try:
                out.append(self.rc.process('r-watch', dict(req)))
            except Exception as e:  # noqa: BLE001 - collected, asserted below
                errs.append(e)

        first = threading.Thread(target=run)
        first.start()
        time.sleep(0.3)   # first thread is inside dispatch, holding the slow runner
        second = threading.Thread(target=run)
        second.start()
        time.sleep(0.3)
        gate.set()
        first.join(10)
        second.join(10)
        self.verdict('race', len(self.calls), len(self.rows))
        self.assertEqual(errs, [])
        self.assertEqual(len(self.calls), 1, self.trace_table())
        states = sorted(r['state'] for r in out)
        self.assertEqual(len([s for s in states if s in ('EXECUTED', 'VERIFIED')]), 1,
                         self.trace_table())
        self.assertIn(states[0] if states[1] in ('EXECUTED', 'VERIFIED') else states[1],
                      ('BLOCKED', 'DUPLICATE', 'UNCERTAIN'), self.trace_table())


class RestartResend(Probe):
    """Variant D: a re-sent id after a Router restart is refused by the journal."""

    def test_resent_press_after_restart_is_duplicate_never_reexecuted(self):
        cid = self.vol_up()
        rid = self.companion.press(cid, request_id='%032x' % 0xE57A11E, seq=3,
                                   gesture='long_press')
        self.clock.t += 2.0
        self.rc.poll_once()
        self.assertEqual(len(self.calls), 1)
        self.server.skill_router = Router(self.server)   # restart: fresh memory, same journal
        self.server.skill_router.clock = self.clock
        self.clock.t += 2.0
        self.companion.press(cid, request_id=rid, seq=3, gesture='long_press')
        self.rc.poll_once()
        self.verdict('restart-resend', len(self.calls), len(self.rows))
        self.assertEqual(len(self.calls), 1, self.trace_table())
        self.assertEqual(self.rows[-1]['state'], 'DUPLICATE', self.trace_table())
        # DUPLICATE rows keep the request id (the invocation is derivable as inv-<request_id>).
        self.assertEqual(self.rows[-1]['request_id'], rid, self.trace_table())


class RelayScoping(Probe):
    """Variant E: burst suspension is per (relay, control); relays stay independent."""

    def test_suspended_watch_does_not_silence_a_second_relay(self):
        watch_cid = self.vol_up()
        phone = FakeCompanion()
        phone.clock = self.clock
        self.server.relays.enroll('r-phone', KEY, 'h-ph-1',
                                  {'capabilities': ['remote_controls'], 'permissions': {}})
        self.server.relays.relays['r-phone']['send'] = phone
        st = self.rc.set_controls({'relay_id': 'r-phone', 'controls': [
            {'label': 'TV volume +', 'skill_id': 'tv_volume_step',
             'target': self.keys['tv'],
             'params': {'direction': 'up'}}], 'consent': True})
        phone_cid = next(c['control_id'] for c in st['controls'] if c['relay_id'] == 'r-phone')
        for i in range(4):   # suspend the watch control with a live burst
            self.companion.press(watch_cid, request_id='%032x' % (0xF00 + i))
            self.clock.t += 2.0
            self.rc.poll_once()
        self.assertTrue(any(s.startswith('r-watch/') for s in self.rc.state()['suspended']))
        watch_calls = len(self.calls)
        self.clock.t += 2.0
        phone.press(phone_cid, request_id='%032x' % 0xBEAC, seq=1, gesture='long_press')
        self.rc.poll_once()
        self.verdict('relay-scope', len(self.calls), len(self.rows))
        self.assertEqual(len(self.calls), watch_calls + 1, self.trace_table())
        self.assertIn(self.rows[-1]['state'], ('EXECUTED', 'VERIFIED'), self.trace_table())
        self.assertEqual(self.rows[-1]['relay_id'], 'r-phone')
        self.assertFalse(any(s.startswith('r-phone/') for s in self.rc.state()['suspended']))


if __name__ == '__main__':
    unittest.main()
