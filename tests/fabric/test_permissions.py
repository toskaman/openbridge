"""§10 permission center: catalog, verify parsers, live states, intents."""
import unittest

from src.fabric import permissions as P


class Parsers(unittest.TestCase):
    def test_parse_appops_modes(self):
        self.assertEqual(P.parse_appops('BLUETOOTH_SCAN: allow; time=+1d2h', 'BLUETOOTH_SCAN'), 'granted')
        self.assertEqual(P.parse_appops('BLUETOOTH_SCAN: deny; time=+1d', 'BLUETOOTH_SCAN'), 'denied')
        self.assertEqual(P.parse_appops('BLUETOOTH_SCAN: ignore;', 'BLUETOOTH_SCAN'), 'denied')
        self.assertEqual(P.parse_appops('BLUETOOTH_SCAN: foreground;', 'BLUETOOTH_SCAN'), 'granted')
        self.assertEqual(P.parse_appops('BLUETOOTH_SCAN: default;', 'BLUETOOTH_SCAN'), 'default')
        self.assertIsNone(P.parse_appops('No operations.', 'BLUETOOTH_SCAN'))
        self.assertIsNone(P.parse_appops('', 'BLUETOOTH_SCAN'))
        self.assertIsNone(P.parse_appops('OTHER_OP: allow;', 'BLUETOOTH_SCAN'))

    def test_parse_whitelist(self):
        self.assertTrue(P.parse_whitelist('system-excidle whitelist:\n  fr.openbridge.companion\n', 'fr.openbridge.companion'))
        self.assertTrue(P.parse_whitelist('system-excidle,fr.openbridge.companion,10345\n', 'fr.openbridge.companion'))
        self.assertFalse(P.parse_whitelist('system-excidle,com.other,10057\n', 'fr.openbridge.companion'))
        self.assertFalse(P.parse_whitelist('whitelist:\n  com.other\n', 'fr.openbridge.companion'))
        self.assertIsNone(P.parse_whitelist('', 'fr.openbridge.companion'))

    def test_parse_perm_grant(self):
        self.assertTrue(P.parse_perm_grant('install permissions:\n  android.permission.X: granted=true\n', 'android.permission.X'))
        self.assertFalse(P.parse_perm_grant('android.permission.X: granted=false', 'android.permission.X'))
        self.assertIsNone(P.parse_perm_grant('no permissions here', 'android.permission.X'))
        self.assertIsNone(P.parse_perm_grant('', 'android.permission.X'))

    def test_parse_setting_contains(self):
        self.assertTrue(P.parse_setting_contains('fr.openbridge.companion/.Svc', 'fr.openbridge.companion'))
        self.assertFalse(P.parse_setting_contains('null', 'fr.openbridge.companion'))
        self.assertIsNone(P.parse_setting_contains('', 'fr.openbridge.companion'))

    def test_parse_device_admin(self):
        self.assertTrue(P.parse_device_admin('admin=ComponentInfo{fr.openbridge.companion/.R}', 'fr.openbridge.companion'))
        self.assertTrue(P.parse_device_admin('Enabled Device Admins (User 0):\n  33: fr.openbridge.companion\n', 'fr.openbridge.companion'))
        self.assertFalse(P.parse_device_admin('no admins', 'fr.openbridge.companion'))
        self.assertIsNone(P.parse_device_admin('', 'fr.openbridge.companion'))

    def test_parse_resolve(self):
        self.assertTrue(P.parse_resolve('package:/x\n  com.android.settings/.A\n'))
        self.assertFalse(P.parse_resolve('no matching activity'))
        self.assertIsNone(P.parse_resolve(''))


class Catalog(unittest.TestCase):
    def test_every_entry_complete(self):
        self.assertGreaterEqual(len(P.CATALOG), 10)
        for e in P.CATALOG:
            for k in ('id', 'os', 'title', 'applies_to', 'declared', 'why', 'breaks', 'verify', 'steps'):
                self.assertIn(k, e, e.get('id'))
            self.assertTrue(e['why'] and e['breaks'] and e['steps'])
            self.assertIn(e['verify']['method'], ('appops', 'whitelist', 'setting', 'admin', 'permgrant', 'interactive'))
            if e['verify']['method'] != 'interactive':
                self.assertTrue(e['verify'].get('argv'))

    def test_companion_declared_match_manifest(self):
        by_id = {e['id']: e for e in P.CATALOG}
        for pid in ('bluetooth_scan', 'bluetooth_connect', 'fine_location', 'record_audio'):
            self.assertTrue(by_id[pid]['declared'], pid)
        for pid in ('post_notifications', 'overlay', 'device_admin'):
            self.assertFalse(by_id[pid]['declared'], pid)


class Verify(unittest.TestCase):
    def test_verify_all_with_fake_runner(self):
        def run(*argv):
            cmd = ' '.join(argv)
            if 'BLUETOOTH_SCAN' in cmd:
                return 'BLUETOOTH_SCAN: allow;'
            if 'BLUETOOTH_CONNECT' in cmd:
                return 'BLUETOOTH_CONNECT: deny;'
            if 'FINE_LOCATION' in cmd:
                return 'No operations.'
            if 'RECORD_AUDIO' in cmd:
                return 'RECORD_AUDIO: foreground;'
            if 'deviceidle' in cmd:
                return 'whitelist:\n  fr.openbridge.companion\n'
            if 'enabled_accessibility_services' in cmd:
                return 'null'
            if 'device_policy' in cmd:
                return 'no admins'
            if 'dumpsys package' in cmd:
                return 'install permissions:\n  android.permission.WRITE_SECURE_SETTINGS: granted=true\n'
            raise OSError('unknown ' + cmd)
        states = {s['id']: s for s in P.verify_all(run, package='fr.openbridge.companion', sdk=33)}
        self.assertEqual(states['bluetooth_scan']['state'], 'granted')
        self.assertEqual(states['bluetooth_connect']['state'], 'denied')
        self.assertEqual(states['fine_location']['state'], 'unknown')
        self.assertEqual(states['record_audio']['state'], 'granted')
        self.assertEqual(states['battery_opt_out']['state'], 'granted')
        self.assertEqual(states['accessibility']['state'], 'denied')
        self.assertEqual(states['write_secure_settings']['state'], 'granted')
        self.assertEqual(states['media_projection']['state'], 'session')
        self.assertTrue(all(s['method'] for s in states.values()))

    def test_sdk_gating(self):
        states = {s['id']: s for s in P.verify_all(lambda *a: 'x', sdk=29)}
        self.assertEqual(states['bluetooth_scan']['state'], 'na')
        self.assertEqual(states['exact_alarm']['state'], 'na')

    def test_verify_one_single_entry(self):
        s = P.verify_one(lambda *a: 'BLUETOOTH_SCAN: allow;', 'bluetooth_scan',
                         package='fr.openbridge.companion', sdk=33)
        self.assertEqual((s['id'], s['state']), ('bluetooth_scan', 'granted'))
        with self.assertRaises(P.PermissionsError):
            P.verify_one(lambda *a: 'x', 'nope')

    def test_runner_failure_is_unknown_never_guessed(self):
        def run(*argv):
            raise OSError('adb down')
        for s in P.verify_all(run, sdk=33):
            if s['id'] != 'media_projection':
                self.assertEqual(s['state'], 'unknown')


class Intents(unittest.TestCase):
    def test_intent_and_grant_commands(self):
        by_id = {e['id']: e for e in P.CATALOG}
        cmd = P.intent_command(by_id['overlay'], 'fr.openbridge.companion')
        self.assertEqual(cmd[:3], ['am', 'start', '-a'])
        self.assertIn('package:fr.openbridge.companion', cmd)
        self.assertIsNone(P.intent_command(by_id['media_projection'], 'x'))
        g = P.grant_command(by_id['write_secure_settings'], 'x')
        self.assertIn('WRITE_SECURE_SETTINGS', ' '.join(g))
        self.assertIsNone(P.grant_command(by_id['overlay'], 'x'))

    def test_capability_map_covers_explorer_matchers(self):
        self.assertIn('bluetooth_scan', P.CAPABILITY_MAP)
        self.assertTrue(all(isinstance(v, list) for v in P.CAPABILITY_MAP.values()))
