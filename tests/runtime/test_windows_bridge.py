"""BridgeWindows adapter against a fake agent speaking the real framing over loopback (SIMULATED_VERIFIED)."""
import base64
import hashlib
import hmac
import json
import secrets
import socket
import struct
import threading
import time
import unittest

from src.adapters.windows_bridge import WindowsBridge, BridgeUnavailable, frame
from src.fabric import discovery
from src.fabric.registry import Registry
from src.runtime import diagnostics
from src.runtime.primitives import Executor
from types import SimpleNamespace

DIAG = {'hostname': 'PC2', 'version': '4.0.0', 'architecture': 'x86', 'os_build': 19045, 'cpu_cores': 4, 'cpu_load_percent': 12.5,
        'ram_total_bytes': 4 * 1024 ** 3, 'ram_avail_bytes': 300 * 1024 ** 2, 'uptime_seconds': 7200,
        'disks': [{'mount': 'C:\\', 'total_bytes': 100 * 1024 ** 3, 'free_bytes': 5 * 1024 ** 3}], 'gpu_temp_c': 0}


class FakeAgent:
    def __init__(self, port, token='psk', guid='GUID-1', version='4.0.0'):
        self.port, self.token, self.guid, self.version = port, token, guid, version
        self.methods = []
        self._sess = None
        self.sock = socket.create_connection(('127.0.0.1', port))
        try:
            a_nonce = secrets.token_hex(16)
            self.sock.sendall(frame({'jsonrpc': '2.0', 'method': 'agent.hello',
                                     'params': {'version': version, 'arch': 'x86', 'pid': 1,
                                                'agent_id': 'TESTPC', 'agent_nonce': a_nonce}}))
            ch = self._frame()
            m_nonce = ch['params'].get('master_nonce') if ch.get('method') == 'auth.challenge' else None
            if m_nonce is None:
                raise OSError('handshake rejected')
            self.sock.sendall(frame({'jsonrpc': '2.0', 'method': 'auth.response', 'params': {
                'agent_id': 'TESTPC', 'hmac': hmac.new(
                    token.encode(), (a_nonce + m_nonce + 'TESTPC').encode(), hashlib.sha256).hexdigest()}}))
            cf = self._frame()
            expect = hmac.new(token.encode(), (m_nonce + a_nonce + 'TESTPC').encode(), hashlib.sha256).hexdigest()
            if cf.get('method') != 'auth.confirm' or not hmac.compare_digest(cf['params'].get('hmac', ''), expect):
                raise OSError('master failed authentication')      # v4 agent verifies the master too
            self._sess = hashlib.sha256(token.encode() + a_nonce.encode() + m_nonce.encode()).digest()
        except (OSError, ValueError, KeyError):
            try:
                self.sock.close()
            except OSError:
                pass
            return
        threading.Thread(target=self.loop, daemon=True).start()

    def _frame(self):
        (n,) = struct.unpack('!I', self._r(4))
        return json.loads(self._r(n))

    def loop(self):
        try:
            while True:
                env = self._frame()
                mac = hmac.new(self._sess, env['body_b64'].encode('ascii'), hashlib.sha256).hexdigest()
                if env.get('v') != 4 or not hmac.compare_digest(mac, env.get('mac', '')):
                    break
                req = json.loads(base64.b64decode(env['body_b64'], validate=True).decode('utf-8'))
                self.methods.append(req['method'])
                if req['method'] == 'sys.diag':
                    res = {'result': DIAG}
                elif req['method'] == 'reg.read':
                    name = req['params']['value_name']
                    if name == 'MachineGuid' and self.guid is None:     # WOW64 view: value absent
                        res = {'error': {'code': -32010, 'message': 'RegQueryValueExA failed'}}
                    else:
                        res = {'result': {'value': {'MachineGuid': self.guid, 'HwProfileGuid': '{hw-1}'}.get(name), 'reg_type': 1}}
                elif req['method'] == 'exec.run':
                    res = {'result': {'pid': 9, 'exit_code': 0, 'timed_out': False, 'stdout_b64': base64.b64encode(b'hello from PC2').decode(), 'stderr_b64': ''}}
                elif req['method'] == 'proc.list':
                    res = {'result': {'processes': [{'name': 'secret.exe', 'pid': 1}] * 3}}
                else:
                    res = {'result': {}}
                inner = json.dumps(dict(jsonrpc='2.0', id=req['id'], **res), separators=(',', ':')).encode()
                b64 = base64.b64encode(inner).decode('ascii')
                self.sock.sendall(frame({'v': 4, 'body_b64': b64,
                                         'mac': hmac.new(self._sess, b64.encode('ascii'),
                                                         hashlib.sha256).hexdigest()}))
        except (OSError, ValueError, KeyError, UnicodeDecodeError):
            pass

    def _r(self, n):
        b = b''
        while len(b) < n:
            c = self.sock.recv(n - len(b))
            if not c:
                raise OSError()
            b += c
        return b

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


def wait(cond, t=2.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Bridge(unittest.TestCase):
    def setUp(self):
        self.b = WindowsBridge('psk', '127.0.0.1', 0)
        s = socket.socket(); s.bind(('127.0.0.1', 0)); self.port = s.getsockname()[1]; s.close()
        self.b.port = self.port
        self.b.start()

    def tearDown(self):
        self.b.close()

    def test_refuses_wildcard_bind_and_missing_key(self):
        for args in (('psk', '0.0.0.0'), ('', '127.0.0.1')):
            with self.assertRaises(BridgeUnavailable):
                WindowsBridge(*args)

    def test_allowlist_enforced_before_sending(self):
        a = FakeAgent(self.port)
        self.assertTrue(wait(self.b.connected))
        for m in ('exec.run', 'fs.delete', 'reg.write', 'gui.input', 'agent.update', 'opt.run', 'svc.op'):
            with self.assertRaises(BridgeUnavailable):
                self.b.call(m, {'cmd': 'whoami'})
        with self.assertRaises(BridgeUnavailable):
            self.b.call('reg.read', {'hive': 'HKLM', 'subkey': r'SAM\SAM', 'value_name': 'x'})
        self.assertEqual(a.methods, [])                    # nothing forbidden ever reached the agent
        a.close()

    def test_job_only_through_run_job_with_bounds(self):
        a = FakeAgent(self.port)
        self.assertTrue(wait(self.b.connected))
        r = self.b.run_job('Get-Date', 'powershell', 30)
        self.assertEqual(r['exit_code'], 0)
        for args in (('', 'cmd', 5), ('x' * 2001, 'cmd', 5), ('dir', 'bash', 5), ('dir', 'cmd', 0), ('dir', 'cmd', 601)):
            with self.assertRaises(BridgeUnavailable):
                self.b.run_job(*args)
        with self.assertRaises(BridgeUnavailable):
            self.b.call('exec.run', {'command': 'dir'})
        self.assertEqual(a.methods.count('exec.run'), 1)
        a.close()

    def test_diagnostics_identity_and_privacy(self):
        a = FakeAgent(self.port)
        self.assertTrue(wait(self.b.connected))
        f = {x['name']: x for x in diagnostics.windows(self.b.call)}
        self.assertEqual(f['os_build']['value'], 19045)
        self.assertEqual(f['memory_pressure']['kind'], 'INFERRED')
        self.assertEqual(f['disk_C_low']['kind'], 'INFERRED')
        self.assertEqual(f['process_count']['value'], 3)
        self.assertNotIn('secret.exe', repr(f)); self.assertNotIn('PC2', repr(f))
        self.assertNotIn('gpu_temperature', f)             # 0 means no sensor, not 0 °C
        ident = self.b.identity(b'salt')
        self.assertTrue(ident.startswith('windows_machine_guid:')); self.assertNotIn('GUID-1', ident)
        a.close()

    def test_identity_fallback_under_wow64(self):
        a = FakeAgent(self.port, guid=None)
        self.assertTrue(wait(self.b.connected))
        i1 = self.b.identity(b'salt')
        self.assertTrue(i1 and i1.startswith('windows_machine_guid:'))
        self.assertEqual(i1, self.b.identity(b'salt'))            # stable
        a.close()

    def test_bad_token_or_protocol_rejected(self):
        a = FakeAgent(self.port, token='wrong')
        self.assertFalse(wait(self.b.connected, 0.5))
        a.close()
        self.assertTrue(wait(lambda: self.b._conn is None))
        a = FakeAgent(self.port, version='2.0.0')
        self.assertFalse(wait(self.b.connected, 0.5))
        a.close()

    def test_disconnect_is_unavailable_not_success(self):
        a = FakeAgent(self.port)
        self.assertTrue(wait(self.b.connected))
        a.close()
        self.assertTrue(wait(lambda: not self.b.connected()))
        with self.assertRaises(BridgeUnavailable):
            self.b.call('sys.diag')

    def test_ingest_and_read_facts_with_identity_check(self):
        a = FakeAgent(self.port)
        self.assertTrue(wait(self.b.connected))
        reg = Registry()
        self.assertEqual(discovery.ingest_windows(reg, self.b, b's')['status'], 'OK')
        key = next(iter(reg.devices))
        caps = {n: c.status for (n, _), c in reg.devices[key]['capabilities'].items()}
        self.assertEqual(caps['run_command'], 'BLOCKED')
        ctx = SimpleNamespace(fabric_registry=reg, fabric_salt=b's', fabric_adapters=lambda p=None: {'windows': self.b},
                              android=SimpleNamespace(_handles={}), fabric_snapshot=reg.snapshot())
        ex = Executor(ctx)
        r = ex.execute('read_facts', key, {})
        self.assertEqual(r['state'], 'VERIFIED')
        a.close(); self.assertTrue(wait(lambda: not self.b.connected()))
        a2 = FakeAgent(self.port, guid='GUID-OTHER')       # another PC takes the slot
        self.assertTrue(wait(self.b.connected))
        self.assertIn('IDENTITY_CHANGED', ex.execute('read_facts', key, {})['errors'][0])
        a2.close()


if __name__ == '__main__':
    unittest.main()


class PcJobPrimitive(unittest.TestCase):
    def test_consent_identity_and_receipt(self):
        import base64
        from types import SimpleNamespace
        from src.fabric.contracts import Identifier
        from src.fabric.registry import Registry
        from src.runtime.primitives import Executor
        reg = Registry()
        key = reg.upsert([Identifier('windows_machine_guid', 'id-pc2', True)], category='computer', label='PC 2')
        class B:
            def connected(self): return True
            def identity(self, salt): return self.ident
            def run_job(self, c, sh, t): return {'exit_code': 0, 'timed_out': False, 'stdout_b64': base64.b64encode(b'ok').decode(), 'stderr_b64': ''}
        b = B(); b.ident = 'id-pc2'
        ex = Executor(SimpleNamespace(fabric_registry=reg, fabric_salt=b's', fabric_adapters=lambda p=None: {'windows': b}))
        self.assertEqual(ex.execute('pc_job', key, {'command': 'hostname'})['state'], 'BLOCKED')
        r = ex.execute('pc_job', key, {'command': 'hostname'}, consent=True)
        self.assertEqual((r['state'], r['result']['stdout']), ('VERIFIED', 'ok'))
        self.assertEqual(len(r['result']['command_sha256']), 64)
        b.ident = 'other'
        self.assertEqual(ex.execute('pc_job', key, {'command': 'hostname'}, consent=True)['state'], 'BLOCKED')
