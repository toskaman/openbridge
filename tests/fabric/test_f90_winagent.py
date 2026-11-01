"""Campaign One section 6: BridgeWindows agent recovery (TESTS ONLY, no src changes).

Covers the recovery contract of src/adapters/windows_bridge.py plus the two
fabric surfaces a restart touches: relay pairing durability
(src/fabric/relay_store.py) and per-session Windows grants
(src/fabric/discovery.ingest_windows):

- transport drop clears the session and a fresh agent can reconnect;
- a relay/bridge restart with an in-flight command fails closed: the caller
  gets BridgeUnavailable, a late reply is dropped (no phantom result), and the
  pc_job primitive reports FAILED, never a VERIFIED receipt;
- there is no offline queue: calls while disconnected raise at once, consume
  no request ids, and nothing stale is flushed after a reconnect; on the
  Companion side a dying relay is marked offline after 3 bounded failures;
- a PSK mismatch refuses the agent, drops the link, and leaks nothing;
- frame desync (oversize / bad session MAC / bad envelope body) drops the
  link with a structured last_error, and the next agent recovers cleanly;
- a restart voids session grants (old session keys verify nothing, replayed
  handshakes are refused) while durable pairings persist in RelayStore until
  explicitly removed, and Windows link grants are re-derived per session.

Deterministic, no real network: in-memory socket doubles only (FakeConn for
fully synchronous runs, PipeConn where a live peer thread is needed).
"""
import base64
import hashlib
import hmac
import json
import queue
import socket
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.adapters import windows_bridge as WB
from src.adapters.windows_bridge import WindowsBridge, BridgeUnavailable, frame, MAX_FRAME
from src.fabric import relay as R
from src.fabric.contracts import Identifier
from src.fabric import discovery
from src.fabric.registry import Registry
from src.fabric.relay_store import RelayStore
from src.runtime.primitives import Executor

PSK = 'test-psk-0123456789abcdef01234567'
WRONG_PSK = 'wrong-psk-0123456789abcdef0123'
AGENT_ID = 'TESTPC'
A_NONCE = 'aa' * 16
A_NONCE_2 = 'bb' * 16
M_NONCE_1 = '11' * 16
M_NONCE_2 = '22' * 16
M_NONCE_3 = '33' * 16


def wait(cond, t=5.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def agent_handshake_bytes(psk, agent_nonce, master_nonce, response_psk=None,
                          agent_id=AGENT_ID, version='4.2.0'):
    hello = frame({'jsonrpc': '2.0', 'method': 'agent.hello',
                   'params': {'version': version, 'arch': 'x86', 'pid': 1,
                              'agent_id': agent_id, 'agent_nonce': agent_nonce}})
    rk = response_psk or psk
    resp = frame({'jsonrpc': '2.0', 'method': 'auth.response',
                  'params': {'agent_id': agent_id,
                             'hmac': hmac.new(rk.encode(), (agent_nonce + master_nonce + agent_id).encode(),
                                              hashlib.sha256).hexdigest()}})
    return hello + resp


def sesskey(psk, agent_nonce, master_nonce):
    return hashlib.sha256(psk.encode() + agent_nonce.encode() + master_nonce.encode()).digest()


def seal(key, msg):
    b64 = base64.b64encode(json.dumps(msg, separators=(',', ':')).encode()).decode('ascii')
    return frame({'v': 4, 'body_b64': b64,
                  'mac': hmac.new(key, b64.encode('ascii'), hashlib.sha256).hexdigest()})


def split_frames(data):
    out, i = [], 0
    data = bytes(data)
    while i + 4 <= len(data):
        (n,) = struct.unpack('!I', data[i:i + 4])
        out.append(json.loads(data[i + 4:i + 4 + n].decode()))
        i += 4 + n
    assert i == len(data), 'trailing %d bytes' % (len(data) - i)
    return out


def open_envelope(key, env):
    assert hmac.compare_digest(
        hmac.new(key, env['body_b64'].encode('ascii'), hashlib.sha256).hexdigest(), env['mac'])
    return json.loads(base64.b64decode(env['body_b64'], validate=True).decode('utf-8'))


class FakeConn:
    """Synchronous socket double: preloaded inbound bytes, recorded outbound.

    Inbound exhaustion reads as EOF (orderly peer close), so a _read_loop run
    over a fixed transcript always terminates deterministically.
    """

    def __init__(self, inbound=b''):
        self._in = bytearray(inbound)
        self.sent = bytearray()
        self.closed = False
        self.on_sendall = None

    def settimeout(self, _t):
        pass

    def sendall(self, data):
        if self.closed:
            raise OSError('closed')
        self.sent += data
        if self.on_sendall is not None:
            self.on_sendall(bytes(data))

    def recv(self, n):
        if not self._in:
            return b''
        out = bytes(self._in[:n])
        del self._in[:n]
        return out

    def feed(self, data):
        self._in += data

    def close(self):
        self.closed = True


class PipeConn(FakeConn):
    """Live-peer socket double: recv blocks for fed bytes instead of EOF.

    feed() delivers peer bytes, eof() an orderly peer close; close() unblocks
    a waiting recv. A 5 s watchdog turns a test-scripting bug into a loud
    OSError instead of a hang.
    """

    def __init__(self):
        super().__init__()
        self._q = queue.Queue()

    def recv(self, n):
        while not self._in:
            if self.closed:
                return b''
            try:
                chunk = self._q.get(timeout=5)
            except queue.Empty:
                raise OSError('test pipe drained without close')
            if chunk is None:
                return b''
            self._in += chunk
        return super().recv(n)

    def feed(self, data):
        self._q.put(bytes(data))

    def eof(self):
        self._q.put(None)

    def close(self):
        if not self.closed:
            self.closed = True
            self._q.put(None)


class FakeListener:
    def __init__(self):
        self.conns = queue.Queue()
        self.closed = False
        self.bound = None

    def setsockopt(self, *a):
        pass

    def bind(self, addr):
        self.bound = addr

    def listen(self, _n):
        pass

    def settimeout(self, _t):
        pass

    def accept(self):
        try:
            return self.conns.get(timeout=1.0), ('192.168.1.2', 5000)
        except queue.Empty:
            raise socket.timeout()

    def close(self):
        self.closed = True


def do_handshake(bridge, conn, master_nonce, agent_nonce=A_NONCE, psk=PSK, response_psk=None):
    """Run the client side of the v4 handshake against `bridge` synchronously."""
    conn.feed(agent_handshake_bytes(psk, agent_nonce, master_nonce, response_psk=response_psk))
    bridge._conn, bridge.peer_ip = conn, '192.168.1.2'
    with mock.patch.object(WB.secrets, 'token_hex', return_value=master_nonce):
        bridge.hello = bridge._handshake(conn)
    return bridge.hello


def run_read_loop(bridge, conn):
    """Drive _read_loop the way _accept_loop does (sets _conn first)."""
    bridge._conn, bridge.peer_ip = conn, '192.168.1.2'
    bridge._read_loop(conn)


def call_async(bridge, method, timeout=5):
    box = {}

    def work():
        try:
            box['result'] = bridge.call(method, timeout=timeout)
        except BridgeUnavailable as e:
            box['error'] = str(e)
        finally:
            box['done'] = True

    t = threading.Thread(target=work, daemon=True)
    t.start()
    box['thread'] = t
    return box


class TransportDropReconnectTests(unittest.TestCase):
    def test_drop_clears_session_wakes_pending_reports_cause(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        conn = FakeConn(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1))
        ev = {'event': threading.Event()}
        b._pending[7] = ev
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_1):
            run_read_loop(b, conn)      # handshake OK, then EOF: orderly drop
        self.assertTrue(ev['event'].is_set())
        self.assertEqual(ev.get('error'), 'agent disconnected')
        self.assertFalse(b.connected())
        self.assertIsNone(b._conn)
        self.assertIsNone(b.hello)
        self.assertIsNone(b._sesskey)
        self.assertEqual(b.last_error, 'ConnectionError: closed')
        self.assertNotIn(PSK, b.last_error)
        b.close()

    def test_reconnect_needs_fresh_handshake_old_session_key_dead(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        c1 = FakeConn()
        do_handshake(b, c1, M_NONCE_1)
        key1 = b._sesskey
        self.assertTrue(b.connected())
        b._drop(c1)
        self.assertFalse(b.connected())
        c2 = FakeConn()
        do_handshake(b, c2, M_NONCE_2, agent_nonce=A_NONCE_2)
        key2 = b._sesskey
        self.assertTrue(b.connected())
        self.assertNotEqual(key1, key2)
        # An envelope sealed under the dead session no longer verifies.
        body = base64.b64encode(b'{"jsonrpc":"2.0","id":1}').decode('ascii')
        stale_mac = hmac.new(key1, body.encode('ascii'), hashlib.sha256).hexdigest()
        self.assertFalse(hmac.compare_digest(
            hmac.new(key2, body.encode('ascii'), hashlib.sha256).hexdigest(), stale_mac))
        # The agent id survives; the session key does not.
        self.assertEqual(b.hello['agent_id'], AGENT_ID)
        b.close()

    def test_one_agent_slot_freed_after_drop_next_agent_accepted(self):
        listener = FakeListener()
        b = WindowsBridge(PSK, '127.0.0.1', sock_factory=lambda *a: listener)
        b.start()
        try:
            c1 = PipeConn()
            c1.feed(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1))
            with mock.patch.object(WB.secrets, 'token_hex', side_effect=[M_NONCE_1, M_NONCE_3]):
                listener.conns.put(c1)
                self.assertTrue(wait(b.connected), 'first agent never authenticated')
                self.assertIs(b._conn, c1)
                c2 = PipeConn()
                c2.feed(agent_handshake_bytes(PSK, A_NONCE_2, M_NONCE_2))
                listener.conns.put(c2)
                self.assertTrue(wait(lambda: c2.closed), 'second agent not refused')
                self.assertIs(b._conn, c1)          # slot kept by the live agent
                c1.eof()                            # transport drop
                self.assertTrue(wait(lambda: not b.connected()), 'drop never noticed')
                c3 = PipeConn()
                c3.feed(agent_handshake_bytes(PSK, A_NONCE_2, M_NONCE_3))
                listener.conns.put(c3)
                self.assertTrue(wait(b.connected), 'reconnect never authenticated')
                self.assertIs(b._conn, c3)
                self.assertEqual(b.hello['agent_id'], AGENT_ID)
                c3.eof()
                self.assertTrue(wait(lambda: not b.connected()))
        finally:
            b.close()


class InFlightNoPhantomTests(unittest.TestCase):
    def test_in_flight_call_fails_closed_on_drop(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        conn = PipeConn()
        do_handshake(b, conn, M_NONCE_1)
        flushed = threading.Event()
        conn.on_sendall = lambda _d: flushed.set()
        box = call_async(b, 'sys.ping', timeout=5)
        self.assertTrue(flushed.wait(5), 'request never hit the wire')
        self.assertEqual(sorted(b._pending), [1])
        b._drop(conn)                       # relay/bridge restart mid-command
        box['thread'].join(5)
        self.assertTrue(box.get('done'))
        self.assertEqual(box.get('error'), 'agent disconnected')
        self.assertNotIn('result', box)     # no phantom result fabricated
        self.assertEqual(b._pending, {})
        self.assertFalse(b.connected())
        b.close()

    def test_late_reply_after_timeout_is_dropped_session_survives(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        conn = PipeConn()
        key = sesskey(PSK, A_NONCE, M_NONCE_1)
        conn.feed(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1))
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_1):
            b._conn, b.peer_ip = conn, '192.168.1.2'
            threading.Thread(target=b._read_loop, args=(conn,), daemon=True).start()
            self.assertTrue(wait(b.connected), 'handshake never completed')
        box = call_async(b, 'sys.ping', timeout=0.05)
        box['thread'].join(5)
        self.assertRegex(box.get('error', ''), 'no answer')
        self.assertEqual(b._pending, {})    # timed-out id retired
        # The agent's late reply for the retired id must go nowhere.
        conn.feed(seal(key, {'jsonrpc': '2.0', 'id': 1, 'result': {'pong': 'late'}}))
        del conn.sent[:]                # forget handshake bytes; count fresh traffic
        # ... and the session still transacts with fresh ids.
        flushed2 = threading.Event()
        conn.on_sendall = lambda _d: flushed2.set()
        box2 = call_async(b, 'sys.ping', timeout=5)
        self.assertTrue(flushed2.wait(5), 'second request never hit the wire')
        (req_env,) = split_frames(conn.sent)
        req = open_envelope(key, req_env)
        self.assertEqual(req['id'], 2)
        conn.feed(seal(key, {'jsonrpc': '2.0', 'id': req['id'], 'result': {'pong': 1}}))
        box2['thread'].join(5)
        self.assertEqual(box2.get('result'), {'pong': 1})   # never the stale 'late'
        self.assertTrue(b.connected())
        self.assertIsNone(b.last_error)
        conn.eof()
        self.assertTrue(wait(lambda: not b.connected()))
        b.close()

    def test_pc_job_reports_failed_never_verified_when_link_dies(self):
        reg = Registry()
        key = reg.upsert([Identifier('windows_machine_guid', 'id-pc2', True)],
                         category='computer', label='PC 2')

        class DyingBridge:
            ident = 'id-pc2'

            def connected(self):
                return True

            def identity(self, _salt):
                return self.ident

            def run_job(self, _c, _sh, _t):
                raise BridgeUnavailable('agent disconnected')

        ex = Executor(SimpleNamespace(fabric_registry=reg, fabric_salt=b's',
                                      fabric_adapters=lambda _p=None: {'windows': DyingBridge()}))
        r = ex.execute('pc_job', key, {'command': 'hostname'}, consent=True)
        self.assertNotEqual(r['state'], 'VERIFIED')
        self.assertFalse(r['verified'])
        self.assertTrue(r['errors'][0].startswith('FAILED:'), r['errors'])
        self.assertEqual(r['result'], {})   # no phantom stdout/exit code


class OfflineQueueBoundsTests(unittest.TestCase):
    def test_calls_while_offline_fail_fast_nothing_queued(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        for _ in range(25):
            with self.assertRaisesRegex(BridgeUnavailable, 'no authenticated agent'):
                b.call('sys.ping', timeout=1)
        self.assertEqual(b._pending, {})
        self.assertEqual(b._next, 1)        # no request ids consumed: zero backlog
        b.close()

    def test_reconnect_flushes_no_stale_requests(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        with self.assertRaises(BridgeUnavailable):
            b.call('sys.ping')
        conn = PipeConn()
        do_handshake(b, conn, M_NONCE_1)
        del conn.sent[:]                # forget handshake bytes; count fresh traffic
        flushed = threading.Event()
        conn.on_sendall = lambda _d: flushed.set()
        box = call_async(b, 'sys.ping', timeout=5)
        self.assertTrue(flushed.wait(5))
        # Agent answers the one live request (same dispatch _read_loop performs).
        (req_env,) = split_frames(conn.sent)
        req = open_envelope(b._sesskey, req_env)
        self.assertEqual((req['method'], req['id']), ('sys.ping', 1))
        b._pending[req['id']]['reply'] = {'jsonrpc': '2.0', 'id': req['id'], 'result': {'pong': 1}}
        b._pending[req['id']]['event'].set()
        box['thread'].join(5)
        self.assertEqual(box.get('result'), {'pong': 1})
        self.assertEqual(len(split_frames(conn.sent)), 1)   # exactly one request ever sent
        b.close()

    def test_dying_relay_marked_offline_after_bounded_failures(self):
        calls = []
        mgr = R.RelayManager(lambda r, m: calls.append(m) or (_ for _ in ()).throw(OSError('down')))
        mgr.enroll('relay-abcdef012345', R.derive_key('123456', 'rn', 'pn'), 'dev-1',
                   {'capabilities': ['ble_scan'],
                    'permissions': {'BLUETOOTH_SCAN': True, 'owner_enabled': True}})
        for _ in range(3):
            with self.assertRaisesRegex(R.RelayError, 'Relay unreachable'):
                mgr.scan(seconds=1)
            self.assertFalse(mgr.relays['relay-abcdef012345']['busy'])
        self.assertFalse(mgr.relays['relay-abcdef012345']['online'])
        self.assertEqual(mgr.eligible('ble_scan'), [])
        with self.assertRaisesRegex(R.RelayError, 'No authorized relay'):
            mgr.scan(seconds=1)
        # Bounded: one start + one best-effort stop per attempt, then silence.
        self.assertEqual(len(calls), 6)


class PskMismatchTests(unittest.TestCase):
    def test_wrong_psk_refused_link_dropped_nothing_leaked(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        conn = FakeConn(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1, response_psk=WRONG_PSK))
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_1):
            run_read_loop(b, conn)
        self.assertFalse(b.connected())
        self.assertIsNone(b._conn)
        self.assertIsNone(b.hello)
        self.assertIsNone(b._sesskey)
        self.assertEqual(b.last_error, 'ValueError: agent failed authentication')
        self.assertNotIn(PSK, b.last_error)
        self.assertNotIn(PSK.encode(), bytes(conn.sent))
        methods = [f.get('method') for f in split_frames(conn.sent)]
        self.assertEqual(methods, ['auth.challenge'])   # no confirm ever sent
        b.close()

    def test_correct_psk_accepted_after_refusal_same_bridge(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        bad = FakeConn(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1, response_psk=WRONG_PSK))
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_1):
            run_read_loop(b, bad)
        self.assertFalse(b.connected())
        good = FakeConn()
        do_handshake(b, good, M_NONCE_2, agent_nonce=A_NONCE_2)
        self.assertTrue(b.connected())
        self.assertEqual(b.hello['agent_id'], AGENT_ID)
        b.close()


class FrameDesyncTests(unittest.TestCase):
    def _desync(self, attack):
        b = WindowsBridge(PSK, '127.0.0.1')
        conn = FakeConn(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1) + attack)
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_1):
            run_read_loop(b, conn)
        self.addCleanup(b.close)
        return b

    def test_oversize_frame_drops_link(self):
        b = self._desync(struct.pack('!I', MAX_FRAME + 1))
        self.assertFalse(b.connected())
        self.assertIsNone(b._sesskey)
        self.assertEqual(b.last_error, 'ValueError: frame too large')

    def test_bad_session_mac_drops_link(self):
        key = sesskey(PSK, A_NONCE, M_NONCE_1)
        body = base64.b64encode(b'{"jsonrpc":"2.0","id":1,"result":{}}').decode('ascii')
        forged = frame({'v': 4, 'body_b64': body, 'mac': '00' * 32})
        self.assertFalse(hmac.compare_digest(
            hmac.new(key, body.encode('ascii'), hashlib.sha256).hexdigest(), '00' * 32))
        b = self._desync(forged)
        self.assertFalse(b.connected())
        self.assertEqual(b.last_error, 'ValueError: bad session MAC')
        self.assertNotIn(PSK, b.last_error)

    def test_bad_envelope_body_drops_link(self):
        key = sesskey(PSK, A_NONCE, M_NONCE_1)
        body = '!!!not-base64!!!'
        env = frame({'v': 4, 'body_b64': body,
                     'mac': hmac.new(key, body.encode('ascii'), hashlib.sha256).hexdigest()})
        b = self._desync(env)
        self.assertFalse(b.connected())
        self.assertEqual(b.last_error, 'ValueError: bad envelope body')

    def test_next_agent_recovers_and_transacts_after_desync(self):
        b = WindowsBridge(PSK, '127.0.0.1')
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_1):
            run_read_loop(b, FakeConn(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1)
                                          + struct.pack('!I', MAX_FRAME + 1)))
        self.assertEqual(b.last_error, 'ValueError: frame too large')
        key2 = sesskey(PSK, A_NONCE_2, M_NONCE_2)
        ev = {'event': threading.Event()}
        b._pending[7] = ev
        fresh = FakeConn(agent_handshake_bytes(PSK, A_NONCE_2, M_NONCE_2)
                         + seal(key2, {'jsonrpc': '2.0', 'id': 7, 'result': {'pong': 7}}))
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_2):
            run_read_loop(b, fresh)       # handshake + one command reply, then EOF
        self.assertTrue(ev['event'].is_set())
        self.assertEqual(ev['reply']['result'], {'pong': 7})
        b.close()


class RestartGrantPersistenceTests(unittest.TestCase):
    def test_restart_voids_session_replayed_handshake_refused(self):
        first = WindowsBridge(PSK, '127.0.0.1')
        do_handshake(first, FakeConn(), M_NONCE_1)
        first.close()
        rebooted = WindowsBridge(PSK, '127.0.0.1')
        # Attacker replays the old hello + old response against a fresh challenge.
        replay = FakeConn(agent_handshake_bytes(PSK, A_NONCE, M_NONCE_1))
        with mock.patch.object(WB.secrets, 'token_hex', return_value=M_NONCE_2):
            run_read_loop(rebooted, replay)
        self.assertFalse(rebooted.connected())
        self.assertEqual(rebooted.last_error, 'ValueError: agent failed authentication')
        # A legitimate fresh handshake still works.
        do_handshake(rebooted, FakeConn(), M_NONCE_3, agent_nonce=A_NONCE_2)
        self.assertTrue(rebooted.connected())
        rebooted.close()

    def test_relay_store_persists_pairing_until_removed(self):
        class MemVault:
            def __init__(self):
                self.available = True
                self._d = {}

            def put(self, name, value):
                self._d[name] = value

            def get(self, name):
                return self._d.get(name)

            def delete(self, name):
                self._d.pop(name, None)

        with tempfile.TemporaryDirectory() as tmp:
            vault, path = MemVault(), Path(tmp) / 'relays.json'
            store = RelayStore(path, vault)
            key = bytes(range(32))
            self.assertTrue(store.save('relay-abcdef012345', 'serial-1', key,
                                       {'capabilities': ['ble_scan'], 'battery_powered': False}))
            # "Restart": a new store object over the same file + vault.
            loaded = RelayStore(path, vault).load()
            self.assertEqual(len(loaded), 1)
            rid, serial, back, declared, aead = loaded[0]
            self.assertEqual((rid, serial, back), ('relay-abcdef012345', 'serial-1', key))
            self.assertEqual(declared['capabilities'], ['ble_scan'])
            # Voided vault key: metadata persists but the pairing grants nothing.
            vault.delete('relay-key-abcdef012345')
            self.assertEqual(RelayStore(path, vault).load(), [])
            # Explicit removal clears both sides.
            vault.put('relay-key-abcdef012345', key.hex())
            RelayStore(path, vault).remove('relay-abcdef012345')
            self.assertEqual(RelayStore(path, vault).load(), [])
            self.assertIsNone(vault.get('relay-key-abcdef012345'))

    def test_relay_store_corrupt_fails_closed_nothing_restored(self):
        class MemVault:
            available = True

            def get(self, _name):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'relays.json'
            path.write_text('not json{{{', encoding='utf-8')
            store = RelayStore(path, MemVault())
            self.assertEqual(store.load(), [])
            self.assertIn('nothing restored', store.error)

    def test_windows_grants_rederived_per_session(self):
        class StubBridge:
            def __init__(self):
                self._up = False
                self.peer_ip = '192.168.1.5'
                self.hello = {'version': '4.2.0', 'arch': 'x86', 'agent_id': AGENT_ID}

            def connected(self):
                return self._up

            def identity(self, _salt):
                return 'windows_machine_guid:abc123'

            def call(self, method, _params=None, _timeout=10):
                assert method == 'sys.diag'
                return {'os_build': 19045, 'architecture': 'x86', 'cpu_cores': 4}

        reg, salt, bridge = Registry(), b'f90-test-salt', StubBridge()
        self.assertEqual(discovery.ingest_windows(reg, bridge, salt)['status'], 'NO_AGENT')
        bridge._up = True
        self.assertEqual(discovery.ingest_windows(reg, bridge, salt)['status'], 'OK')
        dev_key = next(iter(reg.devices))
        link = reg.links[('pc', dev_key, 'LAN', 'WINDOWS_AGENT')]
        self.assertEqual(tuple(link.grants), ('observe', 'read'))
        self.assertEqual(reg.devices[dev_key]['handles']['WINDOWS_AGENT'], 'windows-agent')
        # Session lost: live grants void (no device actions), stored record persists.
        bridge._up = False
        self.assertEqual(discovery.ingest_windows(reg, bridge, salt)['status'], 'NO_AGENT')
        stored = [g for l in reg.snapshot()['links'] for g in [l['grants']]][0]
        self.assertEqual(sorted(stored), ['observe', 'read'])


if __name__ == '__main__':
    unittest.main()
