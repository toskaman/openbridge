"""§9 hardware API: facts/rank/bench over fake + real-local sources."""
import unittest
from types import SimpleNamespace

from src.runtime import api_v2


def snap():
    return {'devices': [{'key': 'dev-ph', 'category': 'phone', 'label': 'Phone',
                         'capabilities': [{'name': 'inspect', 'status': 'REAL_HARDWARE_VERIFIED',
                                           'level': 'read'}],
                         'handles': {'USB': 'h1'}}],
            'links': [{'child': 'dev-ph', 'grants': ['read', 'control'], 'transport': 'USB',
                       'source': 'adb'}]}


WIFI = 'mWifiInfo SSID: "H", freq=5180\n'


def srv(snapshot, android=None, session='/tmp/s9-test-session.sqlite'):
    return SimpleNamespace(fabric_snapshot=snapshot, fabric_registry=None,
                           runtime_executor=SimpleNamespace(), android=android,
                           session_journal=SimpleNamespace(path=session))


def fake_android():
    def shell(*args):
        cmd = ' '.join(args)
        if cmd == 'echo ob-bench':
            return 'ob-bench'
        if 'wifi' in cmd:
            return WIFI
        if 'battery' in cmd:
            return 'level: 80\nscale: 100\npresent: true\nstatus: 3\nplugged: 0\n'
        if 'cpuinfo' in cmd:
            return 'processor\t: 0\nprocessor\t: 1\n'
        if 'meminfo' in cmd:
            return 'MemTotal:        5944568 kB\n'
        if 'SurfaceFlinger' in cmd:
            return 'GLES: ARM, Mali-G78\n'
        if 'telephony' in cmd:
            return 'mServiceState={mVoiceRegState=0, mDataRegState=0}'
        raise OSError('unknown ' + cmd)
    actions = SimpleNamespace(shell=shell)
    ex = SimpleNamespace(_actions=lambda key: actions)
    inspect = lambda h: {'evidence': [{'key': 'battery_percent', 'value': 80, 'source': 'ADB',
                                       'observed_at': '2026-10-30T00:00:00Z'}],
                         'unavailable': []}
    return SimpleNamespace(_ex=ex, inspect=inspect)


class Facts(unittest.TestCase):
    def test_pc_facts_always_present(self):
        code, body = api_v2.get(srv(snap()), '/api/v2/hardware/facts', '')
        self.assertEqual(code, 200)
        pc = next(d for d in body['devices'] if d['key'] == 'pc')
        names = {m['name'] for m in pc['metrics']}
        self.assertIn('cpu_threads', names)
        self.assertIn('os', names)

    def test_android_merged_with_fake_transport(self):
        a = fake_android()
        s = srv(snap(), android=a)
        s.runtime_executor = a._ex
        code, body = api_v2.get(s, '/api/v2/hardware/facts', 'device=dev-ph')
        self.assertEqual(code, 200)
        self.assertEqual(len(body['devices']), 1)
        by_name = {m['name']: m for m in body['devices'][0]['metrics']}
        self.assertEqual(by_name['wifi_band']['value'], '5GHz')
        self.assertEqual(by_name['battery_percent']['value'], 80)
        self.assertEqual(by_name['battery_percent']['unit'], '%')

    def test_no_graph_409(self):
        code, _ = api_v2.get(srv(None), '/api/v2/hardware/facts', '')
        self.assertEqual(code, 409)


class Rank(unittest.TestCase):
    def test_rank_minecraft(self):
        code, body = api_v2.post(srv(snap()), '/api/v2/hardware/rank', {'task': 'minecraft'})
        self.assertEqual(code, 200)
        self.assertEqual(body['task'], 'minecraft')
        self.assertTrue(body['ranking'])
        self.assertIn('benchmark_offer', body)

    def test_rank_unknown_task_400(self):
        code, body = api_v2.post(srv(snap()), '/api/v2/hardware/rank', {'task': 'teleport'})
        self.assertEqual(code, 400)

    def test_rank_recharge_excludes_pc(self):
        code, body = api_v2.post(srv(snap()), '/api/v2/hardware/rank', {'task': 'recharge_first'})
        self.assertEqual(code, 200)
        self.assertNotIn('pc', [r['key'] for r in body['ranking']])


class Bench(unittest.TestCase):
    def test_cpu_bench(self):
        code, body = api_v2.post(srv(snap()), '/api/v2/hardware/bench',
                                 {'kind': 'cpu_loop', 'consent': True, 'iterations': 5000})
        self.assertEqual(code, 200)
        self.assertEqual(body['unit'], 'ms')

    def test_bench_needs_consent(self):
        code, _ = api_v2.post(srv(snap()), '/api/v2/hardware/bench', {'kind': 'cpu_loop'})
        self.assertEqual(code, 400)

    def test_bench_bad_kind_400(self):
        code, _ = api_v2.post(srv(snap()), '/api/v2/hardware/bench', {'kind': 'nope', 'consent': True})
        self.assertEqual(code, 400)

    def test_device_rtt_uses_device_runner(self):
        a = fake_android()
        s = srv(snap(), android=a)
        s.runtime_executor = a._ex
        code, body = api_v2.post(s, '/api/v2/hardware/bench',
                                 {'kind': 'device_rtt', 'consent': True, 'device': 'dev-ph',
                                  'attempts': 2})
        self.assertEqual(code, 200)
        self.assertEqual(body['unit'], 'ms')
