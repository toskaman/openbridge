"""§10 permissions API: catalog/state/open/recheck over a fake transport."""
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


def srv(snapshot, runner=None):
    actions = SimpleNamespace(shell=runner) if runner else None
    ex = SimpleNamespace(_actions=lambda key: actions)
    return SimpleNamespace(fabric_snapshot=snapshot, fabric_registry=None,
                           runtime_executor=ex, android=None,
                           session_journal=SimpleNamespace(path='/tmp/s10-test-session.sqlite'))


def fake_shell(*args):
    cmd = ' '.join(args)
    if 'version.sdk' in cmd:
        return '33\n'
    if 'BLUETOOTH_SCAN' in cmd:
        return 'BLUETOOTH_SCAN: allow;'
    if 'BLUETOOTH_CONNECT' in cmd:
        return 'BLUETOOTH_CONNECT: deny;'
    if 'deviceidle' in cmd:
        return 'whitelist:\n  com.other\n'
    if cmd.startswith('am start'):
        return 'Starting: Intent { act=android.settings.BLUETOOTH_SETTINGS }\nStatus: ok\n'
    if cmd.startswith('pm grant com.android.shell'):
        return ''
    raise OSError('unknown ' + cmd)


class Catalog(unittest.TestCase):
    def test_lists_entries(self):
        code, body = api_v2.get(srv(snap()), '/api/v2/permissions/catalog', '')
        self.assertEqual(code, 200)
        self.assertEqual(body['package'], 'fr.openbridge.companion')
        self.assertGreaterEqual(len(body['permissions']), 10)
        self.assertTrue(all(p['steps'] for p in body['permissions']))
        self.assertIn('bluetooth_scan', body['capability_map'])


class State(unittest.TestCase):
    def test_live_states(self):
        code, body = api_v2.get(srv(snap(), fake_shell), '/api/v2/permissions/state', 'device=dev-ph')
        self.assertEqual(code, 200)
        states = {s['id']: s['state'] for s in body['devices'][0]['states']}
        self.assertEqual(states['bluetooth_scan'], 'granted')
        self.assertEqual(states['bluetooth_connect'], 'denied')
        self.assertEqual(states['battery_opt_out'], 'denied')
        self.assertEqual(body['devices'][0]['sdk'], 33)

    def test_unknown_device_404(self):
        code, _ = api_v2.get(srv(snap(), fake_shell), '/api/v2/permissions/state', 'device=nope')
        self.assertEqual(code, 404)

    def test_no_graph_409(self):
        code, _ = api_v2.get(srv(None, fake_shell), '/api/v2/permissions/state', '')
        self.assertEqual(code, 409)


class OpenRecheck(unittest.TestCase):
    def test_open_intent(self):
        code, body = api_v2.post(srv(snap(), fake_shell), '/api/v2/permissions/open',
                                 {'device': 'dev-ph', 'permission': 'bluetooth_scan', 'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(body['argv'][:3], ['am', 'start', '-a'])
        self.assertIn('ok', body['output'])

    def test_open_grant_command(self):
        code, body = api_v2.post(srv(snap(), fake_shell), '/api/v2/permissions/open',
                                 {'device': 'dev-ph', 'permission': 'write_secure_settings',
                                  'consent': True})
        self.assertEqual(code, 200)
        self.assertEqual(body['argv'][:2], ['pm', 'grant'])
        self.assertIn('android.permission.WRITE_SECURE_SETTINGS', body['argv'])

    def test_open_needs_consent_and_known_perm(self):
        s = srv(snap(), fake_shell)
        code, _ = api_v2.post(s, '/api/v2/permissions/open',
                              {'device': 'dev-ph', 'permission': 'bluetooth_scan'})
        self.assertEqual(code, 400)
        code, _ = api_v2.post(s, '/api/v2/permissions/open',
                              {'device': 'dev-ph', 'permission': 'nope', 'consent': True})
        self.assertEqual(code, 400)

    def test_recheck_single(self):
        code, body = api_v2.post(srv(snap(), fake_shell), '/api/v2/permissions/recheck',
                                 {'device': 'dev-ph', 'permission': 'bluetooth_scan'})
        self.assertEqual(code, 200)
        self.assertEqual(body['state'], 'granted')
        self.assertEqual(body['id'], 'bluetooth_scan')
