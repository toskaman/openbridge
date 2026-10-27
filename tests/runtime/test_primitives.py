"""Executor reliability scenarios (SIMULATED_VERIFIED: fakes stand in for devices; no physical claim)."""
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from types import SimpleNamespace

from src.core.agent import AgentBlocked
from src.fabric.contracts import Identifier, Link, Capability
from src.fabric.registry import Registry
from src.fabric.relay import RelayError
from src.fabric.session import SessionJournal
from src.runtime import primitives
from src.runtime.primitives import Executor, PRIMITIVES, validate, PrimitiveError
from src.runtime.contract import ReversibilityClass


class FakeAndroid:
    def __init__(self):
        self._handles = {'SERIAL1': 'h1'}
        self.identity = 'id-1'
        self.runs = []

    def stable_identifier(self, handle, salt):
        return self.identity if handle in self._handles.values() else None

    def discover(self):
        return {'devices': []}

    def _run(self, args, max_bytes=131072):
        self.runs.append(args)
        if args[3:] == ['cat', '/proc/uptime']:
            return '3600 1'
        raise ValueError('no')


class FakeAgent:
    def __init__(self):
        self.mode = 'ok'
        self.plans = {'p1': {'handle': 'h1'}, 'p2': {'handle': 'other'}}

    def _get(self, pid):
        if pid not in self.plans:
            raise AgentBlocked('Unknown or expired plan')
        return self.plans[pid]

    def execute(self, pid, consent):
        if self.mode == 'unplug':
            raise OSError('adb: device not found')          # USB pulled during the write
        if self.mode == 'readback':
            raise AgentBlocked('Independent read-back failed')
        if self.mode == 'hang':
            time.sleep(1.5)
        return {'state': 'VERIFIED', 'before_code': 1, 'observed_code': 3, 'verified': True, 'package': 'x'}

    def undo(self, pid):
        if self.mode == 'inexact':
            raise AgentBlocked('Exact restoration not verified')
        return {'restored_code': 1, 'exact': True}


def ctx(tmp):
    reg = Registry()
    key = reg.upsert([Identifier('android_serial', 'id-1', True)], category='phone', label='Phone')
    reg.devices[key]['handles'] = {'USB': 'h1'}
    reg.link(Link('pc', key, 'USB', ('read', 'control'), 'ADB:device'))
    relays = SimpleNamespace(relays={'r1': {'device_key': 'h1', 'permissions': {}, 'online': True}}, revoked=[])
    relays.revoke = lambda rid: (relays.revoked.append(rid), relays.relays.pop(rid, None))
    c = SimpleNamespace(fabric_registry=reg, fabric_salt=b's', android=FakeAndroid(), relays=relays, agent=FakeAgent(),
                        session_journal=SessionJournal(tmp + '/s.json'), fabric_lock=threading.Lock(),
                        fabric_adapters=lambda providers=None: {}, fabric_snapshot=reg.snapshot())
    c.relay_action = lambda path, body: {'providers': {'relay': {'devices': 4}}}
    return c, key


class Registry_(unittest.TestCase):
    def test_every_primitive_is_complete(self):
        for p in PRIMITIVES.values():
            self.assertTrue(p.input_schema and p.verification and p.errors and p.timeout_s > 0, p.primitive_id)
            self.assertIn(p.reversibility, {r.value for r in ReversibilityClass})
            self.assertIn(p.concurrency, ('single-per-device', 'single-global', 'parallel'))
            if p.inverse:
                self.assertIn(p.inverse, PRIMITIVES)
            if p.reversibility != 'NONE':
                self.assertTrue(p.requires_consent, p.primitive_id)
            self.assertIn(p.primitive_id, Executor.RUNNERS)

    def test_schema_is_strict(self):
        s = PRIMITIVES['relay_ble_scan'].input_schema
        validate(s, {'relay_id': 'r', 'seconds': 15})
        for bad in ({'relay_id': 'r', 'seconds': 16}, {'relay_id': 'r', 'seconds': True}, {}, {'relay_id': 'r', 'cmd': 'rm -rf'}):
            with self.assertRaises(PrimitiveError):
                validate(s, bad)


class Reliability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c, self.key = ctx(self.tmp)
        self.ex = Executor(self.c)

    def run_(self, pid, params=None, consent=True, key=None):
        return self.ex.execute(pid, key or self.key, params or {}, consent)

    def test_unknown_primitive_and_free_form_refused(self):
        self.assertEqual(self.run_('adb_shell', {'cmd': 'reboot'})['state'], 'BLOCKED')
        self.assertIn('UNEXPECTED', self.run_('read_facts', {'cmd': 'x'})['errors'][0].upper())

    def test_consent_required_for_writes(self):
        r = self.run_('android_optional_app_state', {'plan_id': 'p1'}, consent=False)
        self.assertEqual(r['state'], 'BLOCKED'); self.assertIn('CONSENT_REQUIRED', r['errors'][0])

    def test_success_is_verified_with_before_after(self):
        r = self.run_('android_optional_app_state', {'plan_id': 'p1'})
        self.assertEqual((r['state'], r['before'], r['after'], r['verified']), ('VERIFIED', 1, 3, True))
        self.assertTrue(self.run_('undo_transaction', {'plan_id': 'p1'})['verified'])

    def test_usb_unplugged_during_write(self):
        self.c.agent.mode = 'unplug'
        r = self.run_('android_optional_app_state', {'plan_id': 'p1'})
        self.assertEqual(r['state'], 'FAILED'); self.assertFalse(r['verified'])
        self.assertIn(r['transaction_id'], primitives.to_json(self.ex.recovery())['pending_transactions'])

    def test_inconsistent_readback(self):
        self.c.agent.mode = 'readback'
        r = self.run_('android_optional_app_state', {'plan_id': 'p1'})
        self.assertEqual(r['state'], 'BLOCKED'); self.assertFalse(r['verified']); self.assertIn('read-back', r['errors'][0])

    def test_inexact_undo_never_reported_verified(self):
        self.c.agent.mode = 'inexact'
        r = self.run_('undo_transaction', {'plan_id': 'p1'})
        self.assertFalse(r['verified']); self.assertIn('RESTORE_NOT_EXACT', r['errors'][0])

    def test_device_replaced_under_same_link(self):
        self.c.android.identity = 'id-2'
        r = self.run_('android_optional_app_state', {'plan_id': 'p1'})
        self.assertIn('IDENTITY_CHANGED', r['errors'][0])

    def test_tv_off_or_unauthorized(self):
        self.c.android.identity = None
        self.assertIn('DEVICE_UNAVAILABLE', self.run_('read_facts')['errors'][0])
        self.c.android._handles = {}
        self.assertIn('DEVICE_UNAVAILABLE', self.run_('read_facts')['errors'][0])

    def test_reattach_by_identity_after_reconnect(self):
        self.c.android._handles = {'SERIAL1': 'h9'}          # same device, new ADB handle
        self.assertEqual(self.run_('read_facts')['state'], 'VERIFIED')
        self.assertEqual(self.c.fabric_registry.devices[self.key]['handles']['USB'], 'h9')
        self.c.android.identity = 'id-other'
        self.c.android._handles = {'SERIAL2': 'h10'}         # a different device must never be adopted
        self.assertIn('DEVICE_UNAVAILABLE', self.run_('read_facts')['errors'][0])

    def test_link_lost_during_reads_is_partial(self):
        a = self.c.android
        orig = a._run
        def drop(args, **kw):
            a._handles = {}
            raise ValueError('device offline')
        a._run = drop
        r = self.run_('read_facts')
        self.assertEqual((r['state'], r['verified'], r['result']['lost_link']), ('PARTIAL', False, True))
        self.assertNotIn(r['transaction_id'], primitives.to_json(self.ex.recovery())['pending_transactions'])

    def test_plan_for_other_device_refused(self):
        self.assertIn('PLAN_DEVICE_MISMATCH', self.run_('android_optional_app_state', {'plan_id': 'p2'})['errors'][0])

    def test_read_facts_uses_allowlist_only(self):
        r = self.run_('read_facts')
        self.assertEqual(r['state'], 'VERIFIED')
        names = {f['name'] for f in r['result']['facts']}
        self.assertIn('uptime', names)
        for args in self.c.android.runs:
            self.assertIn(tuple(args[3:]), primitives.diagnostics.ANDROID_READS)

    def test_concurrent_requests_on_same_device(self):
        self.c.agent.mode = 'hang'
        out = []
        t = threading.Thread(target=lambda: out.append(self.run_('android_optional_app_state', {'plan_id': 'p1'})))
        t.start(); time.sleep(0.2)
        second = self.run_('read_facts')
        t.join()
        self.assertIn('CONCURRENT', second['errors'][0])
        self.assertEqual(out[0]['state'], 'VERIFIED')

    def test_timeout_is_unknown_and_keeps_lock(self):
        self.c.agent.mode = 'hang'
        old = PRIMITIVES['android_optional_app_state']
        PRIMITIVES['android_optional_app_state'] = old.__class__(**{**old.__dict__, 'timeout_s': 0.3})
        try:
            r = self.run_('android_optional_app_state', {'plan_id': 'p1'})
            self.assertEqual(r['state'], 'UNKNOWN_TIMEOUT'); self.assertFalse(r['verified'])
            self.assertIn('CONCURRENT', self.run_('read_facts')['errors'][0])   # unfinished write still owns the device
            time.sleep(1.5)
            self.assertEqual(self.run_('read_facts')['state'], 'VERIFIED')
        finally:
            PRIMITIVES['android_optional_app_state'] = old

    def test_relay_disappears_and_revocation(self):
        self.assertEqual(self.run_('relay_ble_scan', {'relay_id': 'r1', 'seconds': 5})['result']['advertisers'], 4)
        def gone(path, body):
            raise RelayError('Relay unreachable: TimeoutError')
        self.c.relay_action = gone
        self.assertIn('RELAY_UNAVAILABLE', self.run_('relay_ble_scan', {'relay_id': 'r1'})['errors'][0])
        self.assertTrue(self.run_('relay_revoke', {'relay_id': 'r1'})['verified'])
        self.assertIn('RELAY_UNAVAILABLE', self.run_('relay_ble_scan', {'relay_id': 'r1'})['errors'][0])

    def test_server_restart_keeps_recovery_state(self):
        self.c.session_journal.record('adb_network_connected', 'TV', {'address': 'x'}, 'not connected', 'connected')
        fresh = Executor(ctx(self.tmp)[0])        # new process, same journal file
        self.assertEqual(len(primitives.to_json(fresh.recovery())['open_session_changes']), 1)

    def test_events_ring_buffer(self):
        self.run_('read_facts')
        ev = self.ex.events_since(0)
        self.assertEqual([e['kind'] for e in ev], ['started', 'receipt'])
        self.assertEqual(self.ex.events_since(ev[-1]['seq']), [])

    def test_receipts_are_bounded(self):
        for _ in range(600):
            self.ex.execute('no-such-primitive', self.key, {})
        self.assertLessEqual(len(self.ex.receipts), 512)


class Http(unittest.TestCase):
    def test_v2_routes_local_and_csrf(self):
        from src.server import create_server
        s = create_server(0, fabric_salt=b't', session_journal=SessionJournal(tempfile.mkdtemp() + '/s.json'))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{s.server_port}'
        try:
            get = lambda p: json.loads(urllib.request.urlopen(base + p).read())
            self.assertEqual(get('/api/v2/contract')['version'], '1.0.0')
            self.assertEqual(len(get('/api/v2/primitives')['primitives']), len(PRIMITIVES))
            self.assertIn('pending_transactions', get('/api/v2/recovery'))
            self.assertEqual(get('/api/v2/relays'), {'routes': [], 'advertisers': []})
            self.assertEqual(get('/api/v2/diagnosis')['findings'][0]['value'], 'empty')
            body = json.dumps({'primitive_id': 'read_facts', 'device_key': 'x'}).encode()
            req = urllib.request.Request(base + '/api/v2/execute', body, {'Content-Type': 'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 403); e.exception.close()
            csrf = get('/api/session')['csrf_token']
            req = urllib.request.Request(base + '/api/v2/execute', body, {'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Origin': base})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 409)
            self.assertIn('DEVICE_UNKNOWN', json.loads(e.exception.read())['errors'][0]); e.exception.close()
        finally:
            s.shutdown(); s.server_close()


if __name__ == '__main__':
    unittest.main()
