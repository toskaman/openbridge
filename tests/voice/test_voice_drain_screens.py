"""Campaign Two §4.6: deterministic voice screens inside the command drain.

Voice transcripts (STT output) pass through fail-closed screens before the
model tier: refusals, conflicts, control presses, control-surface moves and
locate-my-device requests are reported directly, without spending model
inference. Typed text is certain input and always reaches the model tier.
Volume is deliberately NOT screened: the model may legitimately resolve
'monte le son' to tv_volume_step.
"""
import unittest

from tests.runtime.test_command_drain import (
    FakeRelay, make_server, text_cmd, voice_cmd,
)


def drain_once(commands, parse_fn, transcribe):
    from src.runtime import command_drain as D
    pcm = b'\x00\x01' * 8000
    fake = FakeRelay(commands)
    stats = D.poll_once(
        make_server(fake), parse_fn=parse_fn,
        fetch_voice_fn=lambda *a, **k: pcm,
        transcribe_fn=(lambda p, lang: transcribe) if transcribe is not None else None,
        sync=True)
    return stats, fake


class DrainVoiceScreens(unittest.TestCase):
    def test_conflict_voice_reported_without_model_call(self):
        calls = []

        def parse(server, body):
            calls.append(body)
            raise AssertionError('model tier must not run for screened voice')

        stats, fake = drain_once(
            [voice_cmd(b'\x00\x01' * 8000)], parse, 'start and stop the vacuum')
        self.assertEqual(stats['reported'], 1)
        self.assertEqual(fake.reports[0][1], 'needs_clarification')
        self.assertIn('Start or stop?', fake.reports[0][2])
        self.assertEqual(calls, [])

    def test_refusal_voice_reported_without_model_call(self):
        def parse(server, body):
            raise AssertionError('model tier must not run for screened voice')

        stats, fake = drain_once(
            [voice_cmd(b'\x00\x01' * 8000)], parse, 'redémarre la télé')
        self.assertEqual(stats['reported'], 1)
        self.assertEqual(fake.reports[0][1], 'unsupported')
        self.assertIn('manuelle', fake.reports[0][2])

    def test_watch7_row_reports_migration_guidance(self):
        def parse(server, body):
            raise AssertionError('model tier must not run for screened voice')

        stats, fake = drain_once(
            [voice_cmd(b'\x00\x01' * 8000)], parse,
            'mais les boutons de volume sur la tellée')
        self.assertEqual(stats['reported'], 1)
        self.assertEqual(fake.reports[0][1], 'needs_clarification')
        self.assertIn('migration', fake.reports[0][2])

    def test_typed_text_always_reaches_model_tier(self):
        seen = []

        def parse(server, body):
            seen.append(body['text'])
            return {'intent': {'status': 'resolved', 'outcome': 'ok',
                              'skill_id': 'demo.echo', 'targets': [],
                              'params': {}, 'confidence': 0.9,
                              'ambiguities': []}}

        stats, fake = drain_once([text_cmd('start and stop the vacuum')], parse, None)
        self.assertEqual(seen, ['start and stop the vacuum'])
        self.assertEqual(fake.reports[0][1], 'resolved')

    def test_volume_voice_still_reaches_model_tier(self):
        seen = []

        def parse(server, body):
            seen.append(body['text'])
            return {'intent': {'status': 'resolved', 'outcome': 'Would run volume step',
                              'skill_id': 'demo.echo', 'targets': [],
                              'params': {}, 'confidence': 0.9,
                              'ambiguities': []}}

        stats, fake = drain_once(
            [voice_cmd(b'\x00\x01' * 8000)], parse, 'monte le son')
        self.assertEqual(seen, ['monte le son'])
        self.assertEqual(fake.reports[0][1], 'resolved')

    def test_plain_voice_still_reaches_model_tier(self):
        seen = []

        def parse(server, body):
            seen.append(body['text'])
            return {'intent': {'status': 'resolved', 'outcome': 'ok',
                              'skill_id': 'demo.echo', 'targets': [],
                              'params': {}, 'confidence': 0.9,
                              'ambiguities': []}}

        stats, fake = drain_once(
            [voice_cmd(b'\x00\x01' * 8000)], parse, 'allume la lampe')
        self.assertEqual(seen, ['allume la lampe'])
        self.assertEqual(fake.reports[0][1], 'resolved')

    def test_report_text_fits_relay_cap(self):
        from src.fabric import relay as R

        def parse(server, body):
            raise AssertionError('model tier must not run for screened voice')

        long_conflict = 'découvre mes appareils et termine la session ' * 6
        stats, fake = drain_once(
            [voice_cmd(b'\x00\x01' * 8000)], parse, long_conflict[:400])
        self.assertEqual(stats['reported'], 1)
        self.assertLessEqual(len(fake.reports[0][2]), R.MAX_COMMAND_REPORT)


if __name__ == '__main__':
    unittest.main()
