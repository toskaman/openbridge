"""state.audio / audio_state: read-only parse of dumpsys audio (fixture = real BV9300 Android 13 output shape)."""
import unittest

from src.fabric.android_actions import AndroidActions
from src.substrate.registry import NATIVE_PRIMITIVE_REGISTRY, BACKEND

REAL = """- STREAM_VOICE_CALL:
   Muted: false
   Max: 7
   streamVolume:5
- STREAM_MUSIC:
     Muted: true
     Muted Internally: false
     Min: 0
     Max: 15
     streamVolume:0
     Current: 1 (earpiece): 15, 2 (speaker): 0, 80 (bt_a2dp): 8
     Devices: speaker(2)
  - STREAM_ALARM:
   Muted: false
"""


class Shell:
    def __init__(self, out):
        self.out, self.calls = out, []

    def __call__(self, *a):
        self.calls.append(a)
        return self.out if a == ('dumpsys', 'audio') else ''


class AudioState(unittest.TestCase):
    def test_parses_music_stream_not_neighbours(self):
        sh = Shell(REAL)
        st = AndroidActions(sh, 'tv').run('audio_state', {})
        self.assertEqual(st, {'stream': 'music', 'muted': True, 'volume_index': 0, 'max_index': 15,
                              'devices': ['speaker'], 'readable': True})
        self.assertEqual(sh.calls, [('dumpsys', 'audio')])   # read-only: nothing else sent

    def test_android_tv_shape(self):
        tv = '- STREAM_MUSIC:\r\n   Muted: false\r\n   Max: 100\r\n   streamVolume:20\r\n   Devices: headphone\r\n- STREAM_ALARM:\r\n   Muted: true\r\n'
        st = AndroidActions(Shell(tv), 'tv').audio_state()
        self.assertEqual((st['muted'], st['volume_index'], st['max_index'], st['devices']), (False, 20, 100, ['headphone']))

    def test_unmuted(self):
        st = AndroidActions(Shell(REAL.replace('Muted: true', 'Muted: false', 1)), 'tv').audio_state()
        self.assertIs(st['muted'], False)

    def test_unknown_format_is_null_never_guessed(self):
        st = AndroidActions(Shell('Audio service not available'), 'tv').audio_state()
        self.assertEqual((st['muted'], st['volume_index'], st['readable']), (None, None, False))

    def test_registry_entry_is_read_only_and_routed(self):
        d = NATIVE_PRIMITIVE_REGISTRY['state.audio']
        self.assertEqual((d['side_effect_class'], d['required_permissions'], d['manifest_allowed']), ('READ', ['read'], True))
        self.assertEqual(BACKEND['state.audio'][0], 'device_action')
        self.assertEqual(BACKEND['state.audio'][1]({}), {'action': 'audio_state'})


if __name__ == '__main__':
    unittest.main()
