"""Companion 0.15 consistency checks that need no phone: French text for every on-screen string, the relay
operations and modules agree between the Companion (Java) and the PC, the manifest declares every new screen and
service, and the phone command model sees the same system line it was trained with."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'companion' / 'android' / 'src' / 'fr' / 'openbridge' / 'companion'
MANIFEST = ROOT / 'companion' / 'android' / 'AndroidManifest.xml'
NEW_FILES = ('GlassesActivity', 'DevicesActivity', 'SensorsActivity', 'SettingsActivity', 'DiagnosticsActivity',
             'AiActivity', 'VisionActivity', 'GlassesRemoteService', 'SensorService', 'WakeService', 'GlassesTile',
             'OracleTile', 'GlassesWidget', 'PhotoProvider', 'Look', 'FrameMirror', 'GlassesPanel', 'StandaloneHub',
             'Profiles', 'PhoneSensors', 'LocalAi', 'PhoneActions', 'Diag', 'AL')


def java(name):
    return (SRC / (name + '.java')).read_text(encoding='utf-8')


class CompanionTests(unittest.TestCase):
    def test_new_pages_are_translated(self):
        fr = set(re.findall(r'FR\.put\("((?:[^"\\]|\\.)*)"', java('L')))
        missing = set()
        for name in NEW_FILES:
            for s in re.findall(r'L\.t\("((?:[^"\\]|\\.)*)"\)', java(name)):
                if s not in fr:
                    missing.add('%s: %s' % (name, s))
        self.assertEqual(sorted(missing), [])

    def test_manifest_declares_every_screen_and_service(self):
        m = MANIFEST.read_text(encoding='utf-8')
        for name in NEW_FILES[:14]:
            self.assertIn('android:name=".%s"' % name, m, name)
        self.assertIn('android:versionName="0.15.0"', m)

    def test_relay_operations_match(self):
        from src.fabric import relay as R
        rs = java('RelayServer')
        for op in ('set_cards', 'get_sensors', 'get_sessions', 'set_modules'):
            self.assertIn(op, R.OPERATIONS)
            self.assertIn('case "%s"' % op, rs)
        modules = re.search(r'MODULES = \{([^}]*)\}', rs).group(1)
        self.assertEqual(tuple(re.findall(r'"(\w+)"', modules)), R.COMPANION_MODULES)

    def test_sensors_module_is_off_by_default(self):
        self.assertIn('!"sensors".equals(m)', java('RelayServer'))

    def test_phone_command_model_system_line(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('mpd', ROOT / 'dev' / 'ai_training' / 'make_phone_dataset.py')
        mpd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mpd)
        self.assertIn('INTENT_SYSTEM = "%s"' % mpd.SYSTEM, java('LocalAi'))

    def test_phone_dataset_keeps_test_templates_out_of_training(self):
        import importlib.util
        import tempfile
        spec = importlib.util.spec_from_file_location('mpd', ROOT / 'dev' / 'ai_training' / 'make_phone_dataset.py')
        mpd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mpd)
        import json
        with tempfile.TemporaryDirectory() as d:
            mpd.main(['--out', d])
            train = [json.loads(l) for l in open(Path(d) / 'train.jsonl', encoding='utf-8')]
            test = [json.loads(l) for l in open(Path(d) / 'test.jsonl', encoding='utf-8')]
        self.assertGreater(len(train), 1500)
        self.assertFalse({r['prompt'] for r in train} & {r['prompt'] for r in test})
        allowed = {'nav', 'module', 'profile', 'sport', 'luma', 'standalone', 'ask'}
        self.assertTrue(all(r['reply']['a'] in allowed for r in train + test))

    def test_phone_actions_never_reach_other_devices(self):
        src = java('PhoneActions')
        for forbidden in ('submitCommand', 'device_action', 'tv_', 'tuya'):
            self.assertNotIn(forbidden, src)

    def test_phone_orders_need_their_words(self):
        src = java('PhoneActions')
        for kind in ('standalone', 'sport', 'luma', 'module'):
            self.assertIn('case "%s": return p.matches(' % kind, src)
        self.assertIn('if ("sensors".equals(m) && on) return', src)            # never switched on by voice
        self.assertIn('!("sensors".equals(k) && m.optBoolean(k))', java('Profiles'))   # ...or by a profile

    def test_standalone_hub_draws_in_the_native_frame(self):
        p = java('GlassesPanel')
        self.assertIn('W - 1 - x', p)
        self.assertIn('H - 1 - y', p)
        self.assertIn('AL.text(fx(x), fy(y), 4,', p)


if __name__ == '__main__':
    unittest.main()
