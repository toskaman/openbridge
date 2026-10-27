"""Typed Android action catalog (SIMULATED_VERIFIED with a fake ADB shell)."""
import tempfile
import unittest

from src.fabric.android_actions import AndroidActions, ActionError, KEYS
from src.runtime.primitives import Executor
from tests.runtime.test_primitives import ctx


class FakeShell:
    def __init__(self):
        self.calls, self.vol, self.bright = [], 7, 120
    def __call__(self, *a):
        self.calls.append(a)
        if a == ('wm', 'size'): return 'Physical size: 1920x1080'
        if a[:3] == ('cmd', 'media_session', 'volume'):
            if '--set' in a: self.vol = int(a[-1]); return ''
            return f'volume is {self.vol} in range [0..15]'
        if a[:2] == ('settings', 'get'): return str(self.bright) if a[3] == 'screen_brightness' else '600000'
        if a[:2] == ('settings', 'put'): self.bright = int(a[-1]) if a[3] == 'screen_brightness' else self.bright; return ''
        if a[:3] == ('cmd', 'package', 'query-activities'): return 'com.google.android.youtube.tv/.Main\ncom.netflix.ninja/.Main\n'
        if a == ('dumpsys', 'power'): return 'mWakefulness=Awake'
        if a == ('dumpsys', 'window'): return 'mCurrentFocus=Window{1 u0 com.netflix.ninja/x}'
        return ''


class Catalog(unittest.TestCase):
    def test_remote_mouse_text_apps(self):
        sh = FakeShell(); a = AndroidActions(sh, 'tv')
        for k in ('volume_up', 'channel_down', 'power', 'mute', 'ok'):
            a.run('key', {'key': k}); self.assertEqual(sh.calls[-1], ('input', 'keyevent', str(KEYS[k])))
        self.assertEqual(a.run('tap', {'x': 0.5, 'y': 0.5})['at_px'], [959, 539])
        a.run('swipe', {'x1': 0.1, 'y1': 0.5, 'x2': 0.9, 'y2': 0.5, 'ms': 200})
        a.run('text', {'text': 'hello world'}); self.assertEqual(sh.calls[-1], ('input', 'text', 'hello%sworld'))
        r = a.run('launch_app', {'package': 'com.netflix.ninja'}); self.assertEqual(r['screen']['focused_app'], 'com.netflix.ninja')
        a.run('open_url', {'url': 'https://example.org/a'})

    def test_settings_exact_restore(self):
        sh = FakeShell(); a = AndroidActions(sh, 'phone')
        r = a.run('set', {'setting': 'media_volume', 'value': 3})
        self.assertEqual((r['before'], r['after'], r['verified']), (7, 3, True))
        self.assertTrue(a.run('restore', {'setting': 'media_volume'})['exact']); self.assertEqual(sh.vol, 7)
        with self.assertRaises(ActionError): a.run('restore', {'setting': 'media_volume'})

    def test_volume_falls_back_to_keys(self):
        sh = FakeShell()
        def shell(*a):
            if a[:3] == ('cmd', 'media_session', 'volume') and '--set' in a: return ''      # ignored by this build
            if a == ('input', 'keyevent', '24'): sh.vol += 1; return ''
            if a == ('input', 'keyevent', '25'): sh.vol -= 1; return ''
            return sh(*a)
        a = AndroidActions(shell, 'watch')
        r = a.run('set', {'setting': 'media_volume', 'value': 4})
        self.assertEqual((r['before'], r['after'], r['verified']), (7, 4, True))
        self.assertTrue(a.run('restore', {'setting': 'media_volume'})['exact']); self.assertEqual(sh.vol, 7)

    def test_rejections_before_sending(self):
        sh = FakeShell(); a = AndroidActions(sh, 'tv')
        bad = [('key', {'key': 'reboot'}), ('text', {'text': 'a;rm -rf /'}), ('tap', {'x': 2, 'y': 0}), ('launch_app', {'package': 'com.evil.notinstalled'}),
               ('open_url', {'url': 'file:///sdcard'}), ('open_url', {'url': 'https://x.org/$(id)'}), ('set', {'setting': 'adb_enabled', 'value': 0}),
               ('set', {'setting': 'media_volume', 'value': 16}), ('shell', {})]
        n = len([c for c in sh.calls if c[0] in ('input', 'am', 'monkey') or '--set' in c or 'put' in c])
        for act, args in bad:
            with self.subTest(act=act, args=args), self.assertRaises(ActionError):
                a.run(act, args)
        self.assertEqual(n, len([c for c in sh.calls if c[0] in ('input', 'am', 'monkey') or '--set' in c or 'put' in c]))

    def test_probe(self):
        p = AndroidActions(FakeShell(), 'tv').probe()
        self.assertTrue(p['actions']['tap']); self.assertIn('channel_up', p['actions']['key']); self.assertEqual(p['launchable_apps'], 2)
        self.assertNotIn('channel_up', AndroidActions(FakeShell(), 'watch').probe()['actions']['key'])

    def test_primitives(self):
        with tempfile.TemporaryDirectory() as tmp:
            c, key = ctx(tmp); sh = FakeShell()
            c.android._run = lambda args, max_bytes=131072: sh(*args[3:])
            ex = Executor(c); ex._sleep = lambda s: None
            self.assertEqual(ex.execute('device_capabilities', key, {})['state'], 'VERIFIED')
            self.assertEqual(ex.execute('device_action', key, {'action': 'key', 'args': {'key': 'home'}})['state'], 'BLOCKED')
            self.assertEqual(ex.execute('device_action', key, {'action': 'key', 'args': {'key': 'home'}}, True)['state'], 'EXECUTED')
            r = ex.execute('device_action', key, {'action': 'set', 'args': {'setting': 'media_volume', 'value': 2}}, True)
            self.assertEqual((r['state'], r['before'], r['after']), ('VERIFIED', 7, 2))
            self.assertEqual(ex.execute('device_action', key, {'action': 'restore', 'args': {'setting': 'media_volume'}}, True)['state'], 'REVERTED')
            m = ex.execute('device_macro', key, {'steps': [{'action': 'key', 'args': {'key': 'home'}}, {'action': 'wait', 'args': {'ms': 100}},
                                                           {'action': 'key', 'args': {'key': 'nope'}}, {'action': 'key', 'args': {'key': 'ok'}}]}, True)
            self.assertEqual(m['state'], 'PARTIAL'); self.assertEqual(len(m['result']['steps']), 3)


if __name__ == '__main__':
    unittest.main()
