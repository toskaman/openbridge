"""Read-only adapter for the owner's BridgeWindows agent (protocol 3.x: 4-byte big-endian length + JSON-RPC 2.0).

The agent dials the PC (reverse TCP). OpenBridge plays the master side. `call()` exposes ONLY an allowlist of read
methods; the one exception is `run_job()`, reachable only from the consent-gated `pc_job` primitive (the client PC
runs what the owner asks, like any other client device).
The agent's own command, file, registry-write, input and update methods are never sent: the allowlist is enforced
here before any byte leaves the PC. Listening is bound to the LAN interface (never 0.0.0.0), one agent at a time,
frames capped at 1 MiB, every call time-bounded. The pre-shared key comes from the OS vault or the environment
and is never logged or returned."""
import hashlib
import hmac
import json
import socket
import struct
import threading

PROTOCOL_MAJOR = '3'
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
        if not psk or not bind_ip or bind_ip in ('0.0.0.0', ''):
            raise BridgeUnavailable('a pre-shared key and a specific LAN address are required')
        self._psk, self.bind_ip, self.port = psk, bind_ip, port
        self._sock_factory = sock_factory
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._conn = None
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
            self._conn, self.hello = None, None
        for ev in list(self._pending.values()):
            ev['error'] = 'agent disconnected'
            ev['event'].set()

    def _read_loop(self, conn):
        try:
            while True:
                (n,) = struct.unpack('!I', self._recv(conn, 4))
                if n > MAX_FRAME:
                    raise ValueError('frame too large')
                msg = json.loads(self._recv(conn, n))
                if not isinstance(msg, dict):
                    raise ValueError('bad frame')
                if msg.get('method') == 'agent.hello':
                    p = msg.get('params') or {}
                    if not hmac.compare_digest(str(p.get('token', '')).encode(), self._psk.encode()):
                        raise ValueError('agent failed authentication')
                    if not str(p.get('version', '')).startswith(PROTOCOL_MAJOR + '.'):
                        raise ValueError('incompatible protocol')
                    self.hello = {'version': str(p.get('version'))[:16], 'arch': str(p.get('arch'))[:8]}
                    continue
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
        if conn is None or self.hello is None:
            raise BridgeUnavailable('no authenticated agent connected')
        with self._lock:
            rid = self._next; self._next += 1
            ev = {'event': threading.Event()}
            self._pending[rid] = ev
        req = {'jsonrpc': '2.0', 'id': rid, 'token': self._psk, 'method': method}
        if params:
            req.update(params); req['params'] = params
        try:
            with self._send_lock:
                conn.sendall(frame(req))
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
