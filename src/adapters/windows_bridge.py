"""Read-only adapter for the owner's BridgeWindows agent (protocol 4.x: mutual auth + session-MAC envelopes).

The agent dials the PC (reverse TCP). OpenBridge plays the master side. `call()` exposes ONLY an allowlist of read
methods; the one exception is `run_job()`, reachable only from the consent-gated `pc_job` primitive (the client PC
runs what the owner asks, like any other client device).
The agent's own command, file, registry-write, input and update methods are never sent: the allowlist is enforced
here before any byte leaves the PC. Listening is bound to the LAN interface (never 0.0.0.0), one agent at a time,
frames capped at 1 MiB, every call time-bounded. The pre-shared key comes from the OS vault or the environment,
proves possession via HMAC challenge-response, and is never sent, logged or returned."""
import base64
import hashlib
import hmac
import json
import secrets
import socket
import struct
import threading

PROTOCOL_MAJOR = '4'
HANDSHAKE_TIMEOUT = 10.0
# Minimum accepted pre-shared key length, in characters. The v4 handshake proves possession with
# HMAC-SHA256, so anyone who captures one handshake can guess a short PSK offline; below this
# threshold the bridge refuses to start (fail closed) instead of offering weak authentication.
MIN_PSK_LENGTH = 16


def _is_hex(value, length):
    return isinstance(value, str) and len(value) == length and all(c in '0123456789abcdef' for c in value)


def _valid_agent_id(value):
    return isinstance(value, str) and bool(value) and len(value) <= 32 and value[0].isalnum() and all(
        c.isalnum() or c in '_-' for c in value)
MAX_FRAME = 1 << 20
CALL_TIMEOUT = 10.0
# Exact registry values readable through reg.read (hive, subkey, value_name).
REG_ALLOWLIST = {
    ('HKLM', r'SOFTWARE\Microsoft\Cryptography', 'MachineGuid'),
    ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'ProductName'),
    ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'DisplayVersion'),
    ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentBuild'),
    ('HKLM', r'SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001', 'HwProfileGuid'),
}
ALLOWED_METHODS = ('sys.ping', 'sys.diag', 'proc.list', 'reg.read')


class BridgeUnavailable(ValueError):
    pass


def frame(obj):
    data = json.dumps(obj, separators=(',', ':')).encode()
    return struct.pack('!I', len(data)) + data


class WindowsBridge:
    def __init__(self, psk, bind_ip, port=9876, sock_factory=socket.socket):
        if not isinstance(psk, str) or len(psk) < MIN_PSK_LENGTH:
            raise BridgeUnavailable(
                'a pre-shared key of at least %d characters is required' % MIN_PSK_LENGTH)
        if not bind_ip or bind_ip in ('0.0.0.0', ''):
            raise BridgeUnavailable('a specific LAN address to listen on is required')
        self._psk, self.bind_ip, self.port = psk, bind_ip, port
        self._sock_factory = sock_factory
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._conn = None
        self._sesskey = None
        self._pending = {}
        self._next = 1
        self.hello = None
        self.peer_ip = None
        self._listener = None
        self._stop = threading.Event()
        self.last_error = None          # why the last agent link ended (never contains secrets)

    # ---------- lifecycle ----------
    def start(self):
        s = self._sock_factory(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.bind_ip, self.port))
        s.listen(1)
        s.settimeout(1.0)
        self._listener = s
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return self

    def close(self):
        self._stop.set()
        for s in (self._listener, self._conn):
            try:
                s and s.close()
            except OSError:
                pass

    def connected(self):
        return self._conn is not None and self.hello is not None

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, addr = self._listener.accept()
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                return
            if self._conn is not None:            # one agent only
                conn.close()
                continue
            conn.settimeout(None)
            self._conn, self.peer_ip = conn, addr[0]
            threading.Thread(target=self._read_loop, args=(conn,), daemon=True).start()

    def _recv(self, conn, n):
        buf = b''
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError('closed')
            buf += chunk
        return buf

    def _drop(self, conn):
        try:
            conn.close()
        except OSError:
            pass
        if self._conn is conn:
            self._conn, self.hello, self._sesskey = None, None, None
        for ev in list(self._pending.values()):
            ev['error'] = 'agent disconnected'
            ev['event'].set()

    def _read_frame(self, conn):
        (n,) = struct.unpack('!I', self._recv(conn, 4))
        if n > MAX_FRAME:
            raise ValueError('frame too large')
        msg = json.loads(self._recv(conn, n))
        if not isinstance(msg, dict):
            raise ValueError('bad frame')
        return msg

    def _handshake(self, conn):
        """Mutual HMAC challenge-response. Returns the hello dict, or raises (fail closed)."""
        conn.settimeout(HANDSHAKE_TIMEOUT)
        try:
            hello = self._read_frame(conn)
            p = hello.get('params') if hello.get('method') == 'agent.hello' else None
            agent_id = p.get('agent_id') if isinstance(p, dict) else None
            agent_nonce = p.get('agent_nonce') if isinstance(p, dict) else None
            if not isinstance(p, dict) or 'token' in p or not _valid_agent_id(agent_id) or not _is_hex(agent_nonce, 32):
                raise ValueError('auth.required: v4 hello with agent_id + agent_nonce')
            if not str(p.get('version', '')).startswith(PROTOCOL_MAJOR + '.'):
                raise ValueError('incompatible protocol')
            master_nonce = secrets.token_hex(16)
            conn.sendall(frame({'jsonrpc': '2.0', 'method': 'auth.challenge',
                                'params': {'master_nonce': master_nonce, 'agent_id': agent_id}}))
            resp = self._read_frame(conn)
            rp = resp.get('params') if resp.get('method') == 'auth.response' else None
            peer = rp.get('hmac') if isinstance(rp, dict) else None
            expect = hmac.new(self._psk.encode(), (agent_nonce + master_nonce + agent_id).encode(),
                              hashlib.sha256).hexdigest()
            if not isinstance(rp, dict) or rp.get('agent_id') != agent_id or not _is_hex(peer, 64) \
                    or not hmac.compare_digest(peer, expect):
                raise ValueError('agent failed authentication')
            conn.sendall(frame({'jsonrpc': '2.0', 'method': 'auth.confirm',
                                'params': {'hmac': hmac.new(
                                    self._psk.encode(), (master_nonce + agent_nonce + agent_id).encode(),
                                    hashlib.sha256).hexdigest()}}))
            self._sesskey = hashlib.sha256(
                self._psk.encode() + agent_nonce.encode() + master_nonce.encode()).digest()
            return {'version': str(p.get('version'))[:16], 'arch': str(p.get('arch'))[:8], 'agent_id': agent_id}
        finally:
            conn.settimeout(None)

    def _read_loop(self, conn):
        try:
            self.hello = self._handshake(conn)
            while True:
                env = self._read_frame(conn)
                body_b64, mac = env.get('body_b64'), env.get('mac')
                if env.get('v') != 4 or not isinstance(body_b64, str) or not _is_hex(mac, 64) \
                        or not hmac.compare_digest(hmac.new(
                            self._sesskey, body_b64.encode('ascii'), hashlib.sha256).hexdigest(), mac):
                    raise ValueError('bad session MAC')
                try:
                    msg = json.loads(base64.b64decode(body_b64, validate=True).decode('utf-8'))
                except (ValueError, UnicodeDecodeError):
                    raise ValueError('bad envelope body')
                if not isinstance(msg, dict):
                    raise ValueError('bad frame')
                pend = self._pending.get(msg.get('id'))
                if pend:
                    pend['reply'] = msg
                    pend['event'].set()
        except (OSError, ValueError, ConnectionError, struct.error) as e:
            self.last_error = f'{type(e).__name__}: {str(e)[:80]}'
            self._drop(conn)

    # ---------- jobs (owner-requested, consent-gated by the pc_job primitive) ----------
    def run_job(self, command, shell, timeout_s):
        """Run ONE owner-typed command on the client PC through the agent's exec.run. Only reachable through the
        pc_job primitive (owner consent per job); bounds checked here too."""
        if not isinstance(command, str) or not 0 < len(command) <= 2000 or '\x00' in command:
            raise BridgeUnavailable('command must be 1..2000 characters')
        if shell not in ('cmd', 'powershell'):
            raise BridgeUnavailable('shell must be cmd or powershell')
        if not isinstance(timeout_s, int) or not 1 <= timeout_s <= 600:
            raise BridgeUnavailable('timeout must be 1..600 s')
        return self._send('exec.run', {'command': command, 'shell': shell, 'timeout_ms': timeout_s * 1000}, timeout_s + 15)

    # ---------- calls ----------
    def call(self, method, params=None, timeout=CALL_TIMEOUT):
        if method not in ALLOWED_METHODS:
            raise BridgeUnavailable(f'method not allowed: {method}')
        if method == 'reg.read':
            key = (params or {}).get('hive'), (params or {}).get('subkey'), (params or {}).get('value_name')
            if key not in REG_ALLOWLIST:
                raise BridgeUnavailable('registry value not allowlisted')
        return self._send(method, params, timeout)

    def _send(self, method, params, timeout):
        conn = self._conn
        if conn is None or self.hello is None or self._sesskey is None:
            raise BridgeUnavailable('no authenticated agent connected')
        with self._lock:
            rid = self._next; self._next += 1
            ev = {'event': threading.Event()}
            self._pending[rid] = ev
        req = {'jsonrpc': '2.0', 'id': rid, 'method': method}
        if params:
            req.update(params); req['params'] = params
        inner = json.dumps(req, separators=(',', ':')).encode()
        body_b64 = base64.b64encode(inner).decode('ascii')
        env = {'v': 4, 'body_b64': body_b64,
               'mac': hmac.new(self._sesskey, body_b64.encode('ascii'), hashlib.sha256).hexdigest()}
        try:
            with self._send_lock:
                conn.sendall(frame(env))
            if not ev['event'].wait(timeout):
                raise BridgeUnavailable(f'{method}: no answer in {timeout:.0f}s')
        except OSError:
            self._drop(conn)
            raise BridgeUnavailable('agent link lost') from None
        finally:
            self._pending.pop(rid, None)
        if 'error' in ev and 'reply' not in ev:
            raise BridgeUnavailable(ev['error'])
        reply = ev['reply']
        if 'error' in reply:
            raise BridgeUnavailable(f"{method}: agent error {str(reply['error'].get('message', ''))[:80]}")
        return reply.get('result') or {}

    def identity(self, salt):
        """Opaque per-install identity. MachineGuid when readable; a 32-bit agent on 64-bit Windows sees the
        WOW64 registry view where it is absent; HKLM\\SYSTEM is not redirected, so fall back to the per-install
        hardware-profile GUID. Values are hashed with the install salt, never stored raw."""
        def read(sub, name):
            try:
                v = self.call('reg.read', {'hive': 'HKLM', 'subkey': sub, 'value_name': name}).get('value')
                return str(v).strip() if v not in (None, '') else None
            except BridgeUnavailable as e:
                if 'agent error' in str(e):
                    return None
                raise
        guid = read(r'SOFTWARE\Microsoft\Cryptography', 'MachineGuid')
        raw = ('guid\0' + guid) if guid else None
        if raw is None:
            hw = read(r'SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001', 'HwProfileGuid')
            raw = ('hwprofile\0' + hw) if hw else None
        if raw is None:
            return None
        return 'windows_machine_guid:' + hmac.new(salt, f'windows_machine_guid\0{raw}'.encode(), hashlib.sha256).hexdigest()[:24]
