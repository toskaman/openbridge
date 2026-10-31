"""Tuya vacuum, owner-linked local protocol (SIMULATED_VERIFIED with a fake device; no real robot in CI)."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.adapters import tuya_local as t
from src.fabric.discovery import ingest_tuya
from src.fabric.registry import Registry
from src.runtime.primitives import Executor

LINK = {'device_id': 'bfxxxxxxxxxxxxxxxxxxds', 'ip': '192.168.1.25', 'local_key': 'k' * 16, 'version': '3.4'}


class FakeDev:
    dps = {'5': 'charging', '6': 87, '14': 'strong', '104': 'vol_normal', '7': 90}
    sets = []
    def set_socketTimeout(self, s): pass
    def set_socketRetryLimit(self, n): pass
    def status(self): return {'dps': dict(FakeDev.dps)}
    def set_value(self, dp, v):
        FakeDev.sets.append((dp, v)); FakeDev.dps[str(dp)] = v


def vac():
    FakeDev.dps = {'5': 'charging', '6': 87, '14': 'strong', '104': 'vol_normal', '7': 90}; FakeDev.sets = []
    v = t.TuyaVacuum(LINK, device_factory=FakeDev); t._sleep = lambda s: None
    return v


class Tuya(unittest.TestCase):
    def tearDown(self):
        import time; t._sleep = time.sleep

    def test_owner_link_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'tuya.json'
            self.assertIsNone(t.owner_link(p))
            p.write_text(json.dumps(LINK)); self.assertEqual(t.owner_link(p)['ip'], '192.168.1.25')
            p.write_text(json.dumps(dict(LINK, local_key='short'))); self.assertIsNone(t.owner_link(p))
        with self.assertRaises(t.TuyaBlocked):
            t.TuyaVacuum(None)

    def test_facts_and_reversible_setting(self):
        v = vac()
        names = {f['name']: f['value'] for f in v.facts()}
        self.assertEqual(names['battery_level'], 87)
        r = v.set_reversible('suction', 'gentle')
        self.assertEqual((r['before'], r['after'], r['verified']), ('strong', 'gentle', True))
        u = v.undo('suction')
        self.assertTrue(u['exact']); self.assertEqual(FakeDev.dps['14'], 'strong')
        with self.assertRaises(t.TuyaBlocked):
            v.undo('suction')

    def test_second_change_refused_while_restore_pending(self):
        v = vac()
        v.set_reversible('suction', 'gentle')
        with self.assertRaises(t.TuyaBlocked) as e:
            v.set_reversible('suction', 'strong')
        self.assertIn('pending restore', str(e.exception))
        v.undo('suction')   # undo-first discipline: change works again after
        v.set_reversible('suction', 'gentle')
        self.assertEqual(FakeDev.dps['14'], 'gentle')

    def test_restart_loses_pending_restore(self):
        v = vac()
        v.set_reversible('suction', 'gentle')
        fresh = t.TuyaVacuum(LINK, device_factory=FakeDev)  # new process, same robot
        with self.assertRaises(t.TuyaBlocked) as e:
            fresh.undo('suction')
        self.assertIn('nothing to undo', str(e.exception))

    def test_inexact_restore_is_not_reverted(self):
        v = vac()
        v.set_reversible('suction', 'gentle')
        real_status = FakeDev.status
        FakeDev.status = lambda self: {'dps': dict(FakeDev.dps, **{'14': 'wrong'})}
        try:
            u = v.undo('suction')
        finally:
            FakeDev.status = real_status
        self.assertFalse(u['exact'])
        # Pending restore kept for retry; primitive level reports RESTORE_NOT_EXACT.
        self.assertIn('suction', v._before)

    def test_primitive_inexact_restore_blocked_with_code(self):
        v = vac(); reg = Registry()
        ingest_tuya(reg, v, b's')
        key = next(iter(reg.devices))
        c = SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(), fabric_adapters=lambda p=None: {'tuya': v})
        ex = Executor(c)
        ex.execute('tuya_setting', key, {'setting': 'volume', 'value': 'vol_mute'}, consent=True)
        real_status = FakeDev.status
        FakeDev.status = lambda self: {'dps': dict(FakeDev.dps, **{'104': 'vol_high'})}
        try:
            r = ex.execute('tuya_undo', key, {'setting': 'volume'}, consent=True)
        finally:
            FakeDev.status = real_status
        self.assertEqual(r['state'], 'BLOCKED')
        self.assertIn('RESTORE_NOT_EXACT', r['errors'][0])

    def test_full_control_commands(self):
        v = vac()
        r = t.command(v, 'move', 'forward', move_s=10)
        self.assertEqual(FakeDev.sets[-2:], [(4, 'forward'), (4, 'stop')])     # auto-stop, capped duration
        self.assertTrue(r['auto_stopped']); self.assertFalse(r['reversible'])
        t.command(v, 'start'); self.assertEqual(FakeDev.sets[-1], (2, True))
        FakeDev.dps['5'] = 'goto_charge'
        self.assertTrue(t.command(v, 'dock')['verified'])
        self.assertTrue(t.command(v, 'water_level', 'high')['verified'])
        self.assertIsNone(t.command(v, 'seek')['verified'])
        for name, val in (('move', 'jump'), ('mode', 'turbo'), ('format', None)):
            with self.subTest(name=name), self.assertRaises(t.TuyaBlocked):
                t.command(v, name, val)
        with self.assertRaises(t.TuyaBlocked):
            t.refuse_dp(2)

    def test_bad_values_blocked_before_sending(self):
        v = vac()
        for s, val in (('mode', 'smart'), ('suction', 'turbo'), ('power', True)):
            with self.subTest(s=s), self.assertRaises(t.TuyaBlocked):
                v.set_reversible(s, val)
        FakeDev.dps['5'] = 'cleaning'
        with self.assertRaises(t.TuyaBlocked):
            v.set_reversible('volume', 'vol_mute')
        self.assertEqual(FakeDev.sets, [])

    def test_graph_and_primitives(self):
        v = vac(); reg = Registry()
        self.assertEqual(ingest_tuya(reg, v, b's')['status'], 'OK')
        key, dev = next(iter(reg.devices.items()))
        self.assertEqual(dev['category'], 'vacuum')
        self.assertNotIn('bfxx', repr(reg.snapshot()))
        c = SimpleNamespace(fabric_registry=reg, fabric_snapshot=reg.snapshot(), fabric_adapters=lambda p=None: {'tuya': v})
        ex = Executor(c)
        self.assertEqual(ex.execute('read_facts', key, {})['state'], 'VERIFIED')
        self.assertEqual(ex.execute('tuya_setting', key, {'setting': 'volume', 'value': 'vol_mute'})['state'], 'BLOCKED')
        r = ex.execute('tuya_setting', key, {'setting': 'volume', 'value': 'vol_mute'}, consent=True)
        self.assertEqual((r['state'], r['before'], r['after']), ('VERIFIED', 'vol_normal', 'vol_mute'))
        r = ex.execute('tuya_undo', key, {'setting': 'volume'}, consent=True)
        self.assertEqual((r['state'], r['verified']), ('REVERTED', True))
        self.assertEqual(ex.execute('tuya_command', key, {'command': 'seek'})['state'], 'BLOCKED')
        self.assertEqual(ex.execute('tuya_command', key, {'command': 'seek'}, consent=True)['state'], 'EXECUTED_UNVERIFIED')


if __name__ == '__main__':
    unittest.main()
