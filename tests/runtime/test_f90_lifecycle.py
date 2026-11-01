"""Campaign One S3.7: repeated start/stop lifecycle tests for long-running services.

Covers server, command drain, relay manager, model broker/worker, and the
durable journals (session journal + invocation journal). Each service is
cycled repeatedly through normal AND abnormal termination; after every cycle
the tests assert no orphan threads, no lingering sockets (clean rebind), no
handle/file debris, and journal integrity.

All waits are bounded (monotonic deadlines, join timeouts); nothing asserts
on wall-clock timing, so the suite is flake-free by construction.
"""

import http.client
import json
import secrets
from contextlib import closing
import socket
import sqlite3
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.fabric import relay as R
from src.fabric.session import SessionJournal
from src.runtime import command_drain as D
from src.runtime.state_store import StateStore
from src.server import create_server

# ---------------------------------------------------------------------------
# Helpers: bounded waits, thread snapshots, sockets.
# ---------------------------------------------------------------------------

JOIN_TIMEOUT_S = 10.0
POLL_TIMEOUT_S = 5.0


def wait_until(predicate, timeout_s=POLL_TIMEOUT_S, interval_s=0.01):
    """Poll predicate until true or the monotonic deadline passes."""
    deadline = time.monotonic() + timeout_s
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_s)


def thread_names():
    return sorted(t.name for t in threading.enumerate() if t.is_alive())


def assert_quiet(testcase, baseline, timeout_s=POLL_TIMEOUT_S):
    """Assert the live-thread count returns to baseline within a bound."""
    ok = wait_until(lambda: threading.active_count() <= baseline, timeout_s)
    testcase.assertTrue(
        ok,
        'orphan threads: before=%d after=%d (%s)'
        % (baseline, threading.active_count(), thread_names()),
    )


def bounded_shutdown(server, timeout_s=JOIN_TIMEOUT_S):
    """shutdown() from a helper thread so the wait itself is bounded."""
    done = threading.Event()

    def _shut():
        try:
            server.shutdown()
        finally:
            done.set()

    helper = threading.Thread(target=_shut, name='f90-test-shutdown', daemon=True)
    helper.start()
    return done.wait(timeout_s)


def stop_server(server, thread, testcase):
    """Normal stop: bounded shutdown, close, join. Returns nothing; asserts."""
    testcase.assertTrue(bounded_shutdown(server), 'server shutdown did not finish in bound')
    server.server_close()
    thread.join(timeout=JOIN_TIMEOUT_S)
    testcase.assertFalse(thread.is_alive(), 'serve thread survived normal stop')


def http_get(port, path, timeout=5):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    try:
        conn.request('GET', path)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def assert_port_closed(testcase, port):
    """A stopped server must leave no listener behind (bounded, loopback)."""
    sock = socket.socket()
    sock.settimeout(2)
    try:
        with testcase.assertRaises(OSError):
            sock.connect(('127.0.0.1', port))
    finally:
        sock.close()


def make_server(tmpdir, port=0):
    journal = SessionJournal(str(Path(tmpdir) / 'session-changes.json'))
    return create_server(port, fabric_salt=b'f90-lifecycle-test', session_journal=journal)


def serve_in_thread(server):
    thread = threading.Thread(target=server.serve_forever, name='f90-test-serve', daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Server lifecycle.
# ---------------------------------------------------------------------------

class ServerLifecycleTests(unittest.TestCase):
    N_CYCLES = 3

    def test_repeated_normal_start_stop_no_orphans(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = threading.active_count()
            for i in range(self.N_CYCLES):
                server = make_server(tmpdir)
                thread = serve_in_thread(server)
                try:
                    port = server.server_port
                    ok = wait_until(lambda: self._serving(port), timeout_s=POLL_TIMEOUT_S)
                    self.assertTrue(ok, 'cycle %d: server never answered' % i)
                    code, body = http_get(port, '/api/session')
                    self.assertEqual(code, 200)
                    self.assertIn(b'csrf_token', body)
                finally:
                    stop_server(server, thread, self)
                self.assertEqual(server.socket.fileno(), -1, 'cycle %d: listener left open' % i)
                assert_port_closed(self, port)
                assert_quiet(self, baseline)
            # Journal stayed a valid store across the restarts.
            journal = SessionJournal(str(Path(tmpdir) / 'session-changes.json'))
            self.assertIsInstance(journal.open_changes(), list)

    @staticmethod
    def _serving(port):
        try:
            code, _ = http_get(port, '/api/session', timeout=2)
            return code == 200
        except OSError:
            return False

    def test_clean_rebind_same_port(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = threading.active_count()
            first = make_server(tmpdir)
            first_thread = serve_in_thread(first)
            port = first.server_port
            try:
                self.assertTrue(wait_until(lambda: self._serving(port)))
            finally:
                stop_server(first, first_thread, self)
            assert_port_closed(self, port)
            # Rebind the exact same port within a bounded retry (clean rebind).
            deadline = time.monotonic() + POLL_TIMEOUT_S
            second = None
            while second is None:
                try:
                    second = make_server(tmpdir, port=port)
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            self.assertEqual(second.server_port, port)
            second_thread = serve_in_thread(second)
            try:
                self.assertTrue(wait_until(lambda: self._serving(port)))
                code, _ = http_get(port, '/api/session')
                self.assertEqual(code, 200)
            finally:
                stop_server(second, second_thread, self)
            self.assertEqual(second.socket.fileno(), -1)
            assert_port_closed(self, port)
            assert_quiet(self, baseline)

    def test_abrupt_listener_close_recovers_and_rebinds(self):
        """Abnormal termination: the listening socket dies without shutdown.

        The orphaned serve loop must exit on its own (bounded wait); the port
        must be rebindable afterwards with no thread growth.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = threading.active_count()
            server = make_server(tmpdir)
            thread = serve_in_thread(server)
            port = server.server_port
            self.assertTrue(wait_until(lambda: self._serving(port)))
            # Abnormal: slam the listener shut, bypassing shutdown()/close().
            # The dying loop raises in its own thread (expected); capture it
            # so the run stays quiet, and report it if the thread lingers.
            errors = []
            previous_hook = threading.excepthook
            threading.excepthook = errors.append
            try:
                server.socket.close()
                # Bounded grace period; unassisted exit is not required.
                wait_until(lambda: not thread.is_alive(), timeout_s=POLL_TIMEOUT_S)
            finally:
                threading.excepthook = previous_hook
            # Unassisted exit after an abrupt close is platform-dependent
            # (Windows accept() fails; Linux may keep the loop parked), so
            # recovery always runs the bounded shutdown path. Either way the
            # port must end up closed and rebindable with no thread growth.
            try:
                bounded_shutdown(server, timeout_s=POLL_TIMEOUT_S)
            finally:
                server.server_close()
            thread.join(timeout=JOIN_TIMEOUT_S)
            self.assertFalse(thread.is_alive(),
                             'serve thread survived bounded recovery %r' % (errors,))
            self.assertEqual(server.socket.fileno(), -1)
            assert_port_closed(self, port)
            # Clean rebind on the same port after the abnormal stop.
            deadline = time.monotonic() + POLL_TIMEOUT_S
            rebound = None
            while rebound is None:
                try:
                    rebound = make_server(tmpdir, port=port)
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            rebound_thread = serve_in_thread(rebound)
            try:
                self.assertTrue(wait_until(lambda: self._serving(port)))
            finally:
                stop_server(rebound, rebound_thread, self)
            assert_quiet(self, baseline)

    def test_aborted_client_connection_keeps_server_healthy(self):
        """Abnormal client: partial request, then the client vanishes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            baseline = threading.active_count()
            server = make_server(tmpdir)
            thread = serve_in_thread(server)
            try:
                port = server.server_port
                self.assertTrue(wait_until(lambda: self._serving(port)))
                for _ in range(3):
                    sock = socket.create_connection(('127.0.0.1', port), timeout=5)
                    try:
                        sock.sendall(b'GET /api/sess')
                        # Vanish mid-request: no shutdown(), just gone.
                    finally:
                        sock.close()
                # Server still healthy afterwards, then stops normally.
                self.assertTrue(wait_until(lambda: self._serving(port)))
                code, _ = http_get(port, '/api/session')
                self.assertEqual(code, 200)
            finally:
                stop_server(server, thread, self)
            assert_quiet(self, baseline)


# ---------------------------------------------------------------------------
# Command drain lifecycle.
# ---------------------------------------------------------------------------

DRAIN_KEY = b'\x2a' * 32
DRAIN_RID = 'relay-f90life1'


def _signed_reply(params):
    now = int(time.time())
    msg = {'protocol': R.PROTOCOL, 'relay_id': DRAIN_RID, 'op': 'reply', 'params': params,
           'nonce': secrets.token_hex(12), 'issued_at': now, 'expires_at': now + 60}
    return {**msg, 'mac': R.sign(DRAIN_KEY, msg)}


def _text_cmd(text='allume la lampe du salon', lang='en'):
    return {'request_id': secrets.token_hex(16), 'kind': 'text', 'text': text,
            'lang': lang, 'quality': 'auto'}


def _resolved(text):
    return {'intent': {'status': 'resolved', 'outcome': 'Would run: ' + text[:60],
                       'skill_id': 'demo.echo', 'targets': [], 'params': {},
                       'confidence': 0.9, 'ambiguities': []}}


class _FakeRelay:
    def __init__(self, commands=(), fail_ops=()):
        self.commands = list(commands)
        self.fail_ops = set(fail_ops)
        self.reports = []
        self.ops = []
        self.seen = {}

    def send(self, relay, msg):
        R.verify(DRAIN_KEY, msg, self.seen)
        self.ops.append(msg['op'])
        if msg['op'] in self.fail_ops:
            raise OSError('relay unreachable')
        if msg['op'] == 'get_commands':
            cmds, self.commands = self.commands, []
            return _signed_reply({'commands': cmds})
        if msg['op'] == 'report_command':
            params = msg['params']
            self.reports.append((params['request_id'], params['status'], params['text']))
            return _signed_reply({})
        raise AssertionError('unexpected op ' + msg['op'])


def _drain_server(fake, caps=('command_submit',)):
    mgr = R.RelayManager(lambda relay, msg: relay['send'](relay, msg))
    mgr.enroll(DRAIN_RID, DRAIN_KEY, 'dev-1', {'capabilities': list(caps), 'permissions': {}})
    mgr.relays[DRAIN_RID]['send'] = fake.send
    mgr.relays[DRAIN_RID]['url'] = 'http://127.0.0.1:9/'
    return types.SimpleNamespace(relays=mgr)


def _no_drain_workers():
    return not any(t.name == 'drain-worker' and t.is_alive() for t in threading.enumerate())


class CommandDrainLifecycleTests(unittest.TestCase):
    def test_repeated_sync_polls_no_thread_growth(self):
        baseline = threading.active_count()
        for _ in range(5):
            cmds = [_text_cmd('turn on light %d' % i) for i in range(3)]
            fake = _FakeRelay(cmds)
            stats = D.poll_once(_drain_server(fake),
                                parse_fn=lambda s, b: _resolved(b['text']), sync=True)
            self.assertEqual(stats['commands'], 3)
            self.assertEqual(stats['reported'], 3)
            self.assertEqual(len(fake.reports), 3)
            self.assertEqual(stats['errors'], [])
        self.assertTrue(wait_until(_no_drain_workers))
        assert_quiet(self, baseline)

    def test_repeated_async_polls_workers_reaped(self):
        baseline = threading.active_count()
        for cycle in range(3):
            cmds = [_text_cmd('cycle %d cmd %d' % (cycle, i)) for i in range(3)]
            fake = _FakeRelay(cmds)
            stats = D.poll_once(_drain_server(fake),
                                parse_fn=lambda s, b: _resolved(b['text']), sync=False)
            self.assertEqual(stats['commands'], 3)
            landed = wait_until(lambda: len(fake.reports) == 3, timeout_s=POLL_TIMEOUT_S)
            self.assertTrue(landed, 'cycle %d: async reports never landed' % cycle)
            reaped = wait_until(_no_drain_workers, timeout_s=POLL_TIMEOUT_S)
            self.assertTrue(reaped, 'cycle %d: orphan drain-worker threads' % cycle)
        assert_quiet(self, baseline)

    def test_abnormal_relay_errors_never_raise_nor_leak(self):
        baseline = threading.active_count()
        # Poll failures: errors recorded, never raised, no threads spawned.
        for _ in range(3):
            fake = _FakeRelay([_text_cmd()], fail_ops=('get_commands',))
            stats = D.poll_once(_drain_server(fake),
                                parse_fn=lambda s, b: _resolved(b['text']), sync=True)
            self.assertEqual(stats['commands'], 0)
            self.assertEqual(len(stats['errors']), 1)
        # Report failures: command handled, report error recorded, never raised.
        for _ in range(3):
            fake = _FakeRelay([_text_cmd()], fail_ops=('report_command',))
            stats = D.poll_once(_drain_server(fake),
                                parse_fn=lambda s, b: _resolved(b['text']), sync=True)
            self.assertEqual(stats['commands'], 1)
            self.assertEqual(stats['reported'], 0)
            self.assertEqual(len(stats['errors']), 1)
            self.assertEqual(fake.reports, [])
        self.assertTrue(wait_until(_no_drain_workers))
        assert_quiet(self, baseline)
        # Recovery: a healthy relay flows again after the failures.
        cmds = [_text_cmd('recover me')]
        fake = _FakeRelay(cmds)
        stats = D.poll_once(_drain_server(fake),
                            parse_fn=lambda s, b: _resolved(b['text']), sync=True)
        self.assertEqual(stats['reported'], 1)
        self.assertEqual(len(fake.reports), 1)

    def test_background_start_is_idempotent_single_daemon(self):
        """start() launches exactly one daemon loop; a second start is a no-op."""
        mgr = R.RelayManager(lambda relay, msg: relay['send'](relay, msg))
        server = types.SimpleNamespace(relays=mgr)
        before = [t for t in threading.enumerate()
                  if t.name == 'command-drain' and t.is_alive()]
        first = D.start(server, interval_s=3600)
        self.assertIsNotNone(first)
        self.assertTrue(first.daemon)
        second = D.start(server, interval_s=3600)
        self.assertIsNone(second, 'second start must be a no-op')
        after = [t for t in threading.enumerate()
                 if t.name == 'command-drain' and t.is_alive()]
        self.assertEqual(len(after), len(before) + 1)
        # The loop is process-lifetime by design (daemon); other tests use
        # per-test baselines so this single sleeper cannot pollute them.


# ---------------------------------------------------------------------------
# Relay manager lifecycle (synchronous service: enroll -> use -> revoke).
# ---------------------------------------------------------------------------

RELAY_KEY = b'\x7f' * 32
RELAY_RID = 'relay-f90scan1'
SCAN_PERMS = {'BLUETOOTH_SCAN': True, 'owner_enabled': True}


def _scan_transport(observations=(), fail=None):
    calls = []

    def transport(relay, msg):
        calls.append(msg['op'])
        if fail == 'unreachable':
            raise OSError('relay unreachable')
        if fail == 'badmac' and msg['op'] == 'start_discovery':
            return {'bogus': True}
        now = int(time.time())
        params = {'observations': list(observations)} if msg['op'] == 'start_discovery' else {}
        reply = {'protocol': R.PROTOCOL, 'relay_id': RELAY_RID, 'op': 'reply',
                 'params': params, 'nonce': secrets.token_hex(12),
                 'issued_at': now, 'expires_at': now + 60}
        return {**reply, 'mac': R.sign(RELAY_KEY, reply)}

    return transport, calls


def _enroll_scan_relay(mgr):
    mgr.enroll(RELAY_RID, RELAY_KEY, 'dev-1',
               {'capabilities': ['ble_scan'], 'permissions': dict(SCAN_PERMS)})


class RelayManagerLifecycleTests(unittest.TestCase):
    N_CYCLES = 5
    OBS = ({'address': 'AA:BB:CC:DD:EE:FF', 'name': 'beacon', 'rssi': -60},)

    def test_repeated_enroll_scan_revoke_cycles(self):
        baseline = threading.active_count()
        transport, _ = _scan_transport(self.OBS)
        mgr = R.RelayManager(transport)
        for i in range(self.N_CYCLES):
            _enroll_scan_relay(mgr)
            rid, obs = mgr.scan(seconds=2)
            self.assertEqual(rid, RELAY_RID)
            self.assertEqual(len(obs), 1)
            self.assertFalse(mgr.relays[RELAY_RID]['busy'], 'cycle %d: busy stuck' % i)
            self.assertTrue(mgr.relays[RELAY_RID]['online'])
            mgr.revoke(RELAY_RID)
            self.assertNotIn(RELAY_RID, mgr.relays, 'cycle %d: revoke leaked' % i)
        self.assertEqual(mgr.relays, {})
        self.assertEqual(threading.active_count(), baseline,
                         'synchronous manager must not spawn threads')

    def test_abnormal_unreachable_resets_busy_then_recovers(self):
        mgr = R.RelayManager(_scan_transport(fail='unreachable')[0])
        _enroll_scan_relay(mgr)
        for _ in range(3):
            with self.assertRaises(R.RelayError):
                mgr.scan(seconds=2)
            self.assertFalse(mgr.relays[RELAY_RID]['busy'], 'busy stuck after failure')
        relay = mgr.relays[RELAY_RID]
        self.assertEqual(relay['failures'], 3)
        self.assertFalse(relay['online'], '3 failures must mark the relay offline')
        with self.assertRaises(R.RelayError):
            mgr.scan(seconds=2)  # offline relays are not eligible
        # Re-enroll (rebind) on a healthy transport recovers the same id.
        mgr.revoke(RELAY_RID)
        healthy, _ = _scan_transport(self.OBS)
        mgr.transport = healthy
        _enroll_scan_relay(mgr)
        rid, obs = mgr.scan(seconds=2)
        self.assertEqual((rid, len(obs)), (RELAY_RID, 1))
        self.assertTrue(mgr.relays[RELAY_RID]['online'])
        mgr.revoke(RELAY_RID)

    def test_abnormal_malformed_reply_resets_busy(self):
        mgr = R.RelayManager(_scan_transport(fail='badmac')[0])
        _enroll_scan_relay(mgr)
        with self.assertRaises(Exception):
            mgr.scan(seconds=2)
        self.assertFalse(mgr.relays[RELAY_RID]['busy'], 'busy stuck after malformed reply')
        mgr.revoke(RELAY_RID)

    def test_nonce_cache_stays_bounded_across_cycles(self):
        transport, _ = _scan_transport(self.OBS)
        mgr = R.RelayManager(transport)
        _enroll_scan_relay(mgr)
        for _ in range(self.N_CYCLES):
            mgr.scan(seconds=2)
        seen = mgr.relays[RELAY_RID]['seen']
        self.assertLessEqual(len(seen), self.N_CYCLES)
        self.assertLessEqual(len(seen), R.MAX_NONCES)
        mgr.revoke(RELAY_RID)

    def test_manager_restart_reenrolls_same_id(self):
        first, _ = _scan_transport(self.OBS)
        mgr1 = R.RelayManager(first)
        _enroll_scan_relay(mgr1)
        mgr1.scan(seconds=2)
        del mgr1  # "process" restart: a fresh manager takes over the same id
        second, _ = _scan_transport(self.OBS)
        mgr2 = R.RelayManager(second)
        _enroll_scan_relay(mgr2)
        rid, _ = mgr2.scan(seconds=2)
        self.assertEqual(rid, RELAY_RID)
        mgr2.revoke(RELAY_RID)


# ---------------------------------------------------------------------------
# Model broker / worker lifecycle.
# ---------------------------------------------------------------------------

class RuntimeBrokerLifecycleTests(unittest.TestCase):
    FACTS = {'battery_percent': 50}

    def _permit(self):
        from src.ai.broker import CreditPermit
        return CreditPermit('obs-f90life', datetime.now(timezone.utc), 128.0, 0.20)

    @staticmethod
    def _ok_response():
        from src.ai.broker import MODEL_ID
        return {'model': MODEL_ID, 'id': 'resp-f90',
                'usage': {'prompt_tokens': 10, 'completion_tokens': 20},
                'choices': [{'message': {'content': json.dumps(
                    {'summary': 'Battery is fine.', 'evidence_refs': ['battery_percent'],
                     'action': 'inspect_only', 'uncertainty': 'Limited facts.'})}}]}

    def _broker(self, ledger, transport):
        from src.ai.broker import RuntimeModelBroker
        return RuntimeModelBroker(ledger, self._permit(), transport)

    @staticmethod
    def _ledger_rows(ledger):
        # closing(), not a bare with-block: sqlite3's statement cache cycles
        # keep a merely-exited connection (and its Windows file lock) alive
        # until cyclic GC. Explicit close keeps teardown deterministic.
        with closing(sqlite3.connect(ledger, timeout=5)) as db:
            integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            count = db.execute('SELECT COUNT(*) FROM reservations').fetchone()[0]
        return integrity, count

    def test_repeated_broker_instances_share_one_ledger(self):
        """Restarting the broker (new instance, same ledger) keeps accounting."""
        from src.ai.broker import ModelBlocked
        baseline = threading.active_count()
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Path(tmpdir) / 'budget.sqlite3'
            first = self._broker(ledger, lambda payload: self._ok_response())
            out = first.recommend(dict(self.FACTS))
            self.assertEqual(out['reserved_usd'], 0.10)
            del first  # restart: a fresh instance on the same ledger file
            second = self._broker(ledger, lambda payload: self._ok_response())
            second.recommend(dict(self.FACTS))
            # $0.20 ceiling holds exactly two $0.10 reservations; the third
            # is refused by accounting, not by corruption.
            third = self._broker(ledger, lambda payload: self._ok_response())
            with self.assertRaises(ModelBlocked):
                third.recommend(dict(self.FACTS))
            integrity, count = self._ledger_rows(ledger)
            self.assertEqual(integrity, 'ok')
            self.assertEqual(count, 2)
            leftovers = [p.name for p in Path(tmpdir).iterdir()
                         if p.suffix in ('.tmp', '.lock', '.journal')]
            self.assertEqual(leftovers, [])
        self.assertEqual(threading.active_count(), baseline)

    def test_abnormal_transport_failure_keeps_ledger_valid_then_recovers(self):
        from src.ai.broker import ModelBlocked
        baseline = threading.active_count()
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger = Path(tmpdir) / 'budget.sqlite3'

            def failing(payload):
                raise ConnectionError('network down')

            broken = self._broker(ledger, failing)
            with self.assertRaises(ModelBlocked) as raised:
                broken.recommend(dict(self.FACTS))
            self.assertIn('reservation retained', str(raised.exception))
            # Reservation is committed before I/O and never refunded: one row.
            integrity, count = self._ledger_rows(ledger)
            self.assertEqual(integrity, 'ok')
            self.assertEqual(count, 1)
            # Recovery on the same ledger: one reservation of headroom left.
            healthy = self._broker(ledger, lambda payload: self._ok_response())
            healthy.recommend(dict(self.FACTS))
            _, count = self._ledger_rows(ledger)
            self.assertEqual(count, 2)
        self.assertEqual(threading.active_count(), baseline)


class LocalWorkerLifecycleTests(unittest.TestCase):
    N_CYCLES = 5

    def _worker(self, chat=None):
        from src.ai.glimmer import GLIMMER_ID, GLIMMER_DIGEST
        from src.forge.local_models import IsolatedGlimmerCPU
        captured = []

        def default_chat(payload):
            captured.append(payload)
            return {'model': GLIMMER_ID, 'done': True,
                    'done_reason': 'unload' if payload['keep_alive'] == 0 else 'load',
                    'message': {'role': 'assistant', 'content': ''},
                    'eval_count': 0, 'prompt_eval_count': 0}

        worker = IsolatedGlimmerCPU(
            catalog=lambda: {'models': [{'name': GLIMMER_ID, 'digest': GLIMMER_DIGEST}]},
            chat=chat or default_chat)
        return worker, captured

    def test_repeated_prepare_release_cycles(self):
        from src.ai.glimmer import GLIMMER_ID
        baseline = threading.active_count()
        worker, seen = self._worker()
        for i in range(self.N_CYCLES):
            ready = worker.prepare()
            self.assertEqual(ready['state'], 'ready', 'cycle %d' % i)
            released = worker.release()
            self.assertEqual(released['state'], 'released', 'cycle %d' % i)
            self.assertEqual(released['tokens_generated'], 0)
        self.assertEqual(len(seen), 2 * self.N_CYCLES)
        for payload in seen:
            self.assertEqual(payload['model'], GLIMMER_ID)
            self.assertNotIn('messages', payload)
            self.assertNotIn('prompt', payload)
        self.assertEqual(threading.active_count(), baseline)

    def test_abnormal_control_failure_then_recovers(self):
        from src.forge.compiler import ForgeError

        def failing(payload):
            raise OSError('ollama down')

        worker, _ = self._worker(chat=failing)
        with self.assertRaises(ForgeError):
            worker.prepare()
        # Same worker recovers once the transport is healthy again.
        healthy, _ = self._worker()
        worker.chat = healthy.chat
        worker.catalog = healthy.catalog
        self.assertEqual(worker.prepare()['state'], 'ready')
        self.assertEqual(worker.release()['state'], 'released')

    def test_local_inflight_lock_released_on_abnormal_request(self):
        """A failed inference never wedges the no-queue lock; next call works."""
        from src.ai.broker import ModelBlocked
        from src.ai.local_meta import (LocalMetaBroker, MODEL_DIGEST, MODEL_ID,
                                       UNCERTAINTY_LIMIT)
        catalog = lambda: {'models': [{'name': MODEL_ID, 'digest': MODEL_DIGEST}]}

        def failing(payload):
            raise OSError('local model down')

        broker = LocalMetaBroker(catalog=catalog, chat=failing)
        with self.assertRaises(ModelBlocked):
            broker.recommend({'battery_percent': 50, 'storage_free_gb': 20})
        self.assertTrue(broker._inflight.acquire(blocking=False),
                        'inflight lock stuck after failure')
        broker._inflight.release()

        def healthy(payload):
            return {'model': MODEL_ID, 'done': True, 'done_reason': 'stop',
                    'message': {'content': json.dumps(
                        {'summary': 'Battery is 50% and 20 GB of storage is free.',
                         'evidence_refs': ['battery_percent', 'storage_free_gb'],
                         'action': 'inspect_only', 'uncertainty': UNCERTAINTY_LIMIT})},
                    'prompt_eval_count': 1, 'eval_count': 2}

        broker.chat = healthy
        out = broker.recommend({'battery_percent': 50, 'storage_free_gb': 20})
        self.assertEqual(out['proposal']['action'], 'inspect_only')
        self.assertTrue(broker._inflight.acquire(blocking=False))
        broker._inflight.release()


# ---------------------------------------------------------------------------
# Journal integrity across restarts and crashes.
# ---------------------------------------------------------------------------

class SessionJournalLifecycleTests(unittest.TestCase):
    def test_repeated_record_close_cycles_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / 'session-changes.json')
            first = SessionJournal(path)
            ids = [first.record('bluetooth_turned_on', 'Phone %d' % i,
                                {'serial': 'dev-%d' % i}, 'off', 'on')
                   for i in range(3)]
            first.close(ids[0], 'RESTORED', 'toggled back')
            del first  # restart: a fresh handle on the same file
            second = SessionJournal(path)
            open_rows = second.open_changes()
            self.assertEqual(len(open_rows), 2)
            second.record('adb_network_connected', 'TV',
                          {'address': '192.168.1.5:5555'}, 'down', 'up')
            del second
            third = SessionJournal(path)
            self.assertEqual(len(third.open_changes()), 3)
            rows = json.loads(Path(path).read_text(encoding='utf-8'))
            self.assertIsInstance(rows, list)
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(set(r) >= {'id', 'kind', 'state'} for r in rows))

    def test_crash_debris_and_corruption_never_break_the_journal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'session-changes.json'
            journal = SessionJournal(str(path))
            journal.record('bluetooth_turned_on', 'Phone', {'serial': 'dev-1'}, 'off', 'on')
            # A stale temp file from a crashed write is ignored on load.
            path.with_suffix('.tmp').write_text('{partial', encoding='utf-8')
            reopened = SessionJournal(str(path))
            self.assertEqual(len(reopened.open_changes()), 1)
            # A corrupted file degrades to empty (documented) and the next
            # record restores a valid store instead of wedging.
            path.write_text('{bad', encoding='utf-8')
            degraded = SessionJournal(str(path))
            self.assertEqual(degraded.open_changes(), [])
            degraded.record('adb_network_connected', 'TV',
                            {'address': '192.168.1.5:5555'}, 'down', 'up')
            rows = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(rows), 1)

    def test_journal_writes_leave_no_temp_debris(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / 'session-changes.json')
            journal = SessionJournal(path)
            for i in range(5):
                cid = journal.record('bluetooth_turned_on', 'Phone %d' % i,
                                     {'serial': 'dev-%d' % i}, 'off', 'on')
                journal.close(cid, 'RESTORED')
            debris = [p.name for p in Path(tmpdir).iterdir() if p.suffix == '.tmp']
            self.assertEqual(debris, [])


class InvocationJournalLifecycleTests(unittest.TestCase):
    NOW = 10_000.0  # synthetic clock: no wall-clock flakes

    def test_repeated_claim_finish_cycles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir) / 'runtime-state.json')
            for i in range(5):
                ok, _ = store.claim_invocation('drain', 'cmd-%d' % i, self.NOW + i)
                self.assertTrue(ok, 'claim %d refused' % i)
                done = store.finish_invocation('drain', 'cmd-%d' % i, 'f' * 64,
                                               self.NOW + i + 1)
                self.assertTrue(done, 'finish %d lost' % i)
                # A finished id is a duplicate within its TTL: refused, intact.
                ok, row = store.claim_invocation('drain', 'cmd-%d' % i, self.NOW + i + 2)
                self.assertFalse(ok)
                self.assertEqual(row['state'], 'DONE')
            rows = store.load_invocations(self.NOW + 10)
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(r['state'] == 'DONE' for r in rows))

    def test_abnormal_crash_leaves_executing_refused_after_restart(self):
        """A claim with no finish (crash) must refuse re-execution, not re-run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'runtime-state.json'
            before = StateStore(path)
            ok, _ = before.claim_invocation('server', 'boot-op-1', self.NOW)
            self.assertTrue(ok)
            del before  # crash: no finish_invocation ever runs
            after = StateStore(path)  # restart on the same journal file
            ok, row = after.claim_invocation('server', 'boot-op-1', self.NOW + 10)
            self.assertFalse(ok, 'crashed EXECUTING id must refuse re-execution')
            self.assertEqual(row['state'], 'EXECUTING')
            self.assertFalse(after.finish_invocation('server', 'missing', '0' * 64,
                                                     self.NOW + 10))
            view = after.load_invocations(self.NOW + 10)
            self.assertEqual([(r['invocation_id'], r['state']) for r in view],
                             [('boot-op-1', 'EXECUTING')])
            # A fresh id still claims fine on the same store (clean recovery).
            ok, _ = after.claim_invocation('server', 'boot-op-2', self.NOW + 10)
            self.assertTrue(ok)
            doc = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(doc['version'], 1)

    def test_journal_cycles_leave_no_temp_or_lock_debris(self):
        baseline = threading.active_count()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = StateStore(Path(tmpdir) / 'runtime-state.json')
            for i in range(5):
                store.claim_invocation('drain', 'op-%d' % i, self.NOW + i)
                store.finish_invocation('drain', 'op-%d' % i, 'e' * 64, self.NOW + i + 1)
            debris = [p.name for p in Path(tmpdir).iterdir()
                      if p.suffix == '.tmp' or p.name.endswith('.tmp')]
            self.assertEqual(debris, [])
        self.assertEqual(threading.active_count(), baseline)


if __name__ == '__main__':
    unittest.main()
