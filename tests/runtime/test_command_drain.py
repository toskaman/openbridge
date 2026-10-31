"""Companion command drain: get_commands -> parse/transcribe -> report_command.

The Companion queues owner-typed and owner-spoken commands on-device; without a
drain the queue is never read and the screen stays on "Got it" forever. These
tests pin the drain contract against a fake relay with REAL crypto both ways.
"""
import hashlib
import secrets
import time
import types
import unittest

from src.fabric import relay as R
from src.runtime import command as CMD

KEY = b'\x2a' * 32
RID = 'relay-draintest1'


def signed_reply(params):
    now = int(time.time())
    msg = {'protocol': R.PROTOCOL, 'relay_id': RID, 'op': 'reply', 'params': params,
           'nonce': secrets.token_hex(12), 'issued_at': now, 'expires_at': now + 60}
    return {**msg, 'mac': R.sign(KEY, msg)}


def text_cmd(text='allume la lampe du salon', lang='fr'):
    return {'request_id': secrets.token_hex(16), 'kind': 'text', 'text': text,
            'lang': lang, 'quality': 'auto'}


def voice_cmd(pcm, lang='fr'):
    return {'request_id': secrets.token_hex(16), 'kind': 'voice', 'clip_id': 'vabc12',
            'bytes': len(pcm), 'sha256': hashlib.sha256(pcm).hexdigest(),
            'lang': lang, 'quality': 'auto'}


class FakeRelay:
    """In-memory relay: verifies PC signatures, serves canned commands, records reports."""

    def __init__(self, commands=(), fail_ops=()):
        self.commands = list(commands)
        self.fail_ops = set(fail_ops)
        self.reports = []
        self.ops = []
        self.seen = {}

    def send(self, relay, msg):
        R.verify(KEY, msg, self.seen)
        self.ops.append(msg['op'])
        if msg['op'] in self.fail_ops:
            raise OSError('relay unreachable')
        if msg['op'] == 'get_commands':
            cmds, self.commands = self.commands, []
            return signed_reply({'commands': cmds})
        if msg['op'] == 'report_command':
            p = msg['params']
            self.reports.append((p['request_id'], p['status'], p['text']))
            return signed_reply({})
        raise AssertionError('unexpected op ' + msg['op'])


def make_server(fake, caps=('command_submit',)):
    mgr = R.RelayManager(lambda relay, msg: relay['send'](relay, msg))
    mgr.enroll(RID, KEY, 'dev-1', {'capabilities': list(caps), 'permissions': {}})
    mgr.relays[RID]['send'] = fake.send
    mgr.relays[RID]['url'] = 'http://127.0.0.1:9/'
    return types.SimpleNamespace(relays=mgr)


def resolved(text):
    return {'intent': {'status': 'resolved', 'outcome': 'Would run: ' + text[:60],
                       'skill_id': 'demo.echo', 'targets': [], 'params': {},
                       'confidence': 0.9, 'ambiguities': []}}


class DrainTests(unittest.TestCase):
    def test_text_command_reported(self):
        from src.runtime import command_drain as D
        c = text_cmd()
        fake = FakeRelay([c])
        stats = D.poll_once(make_server(fake), parse_fn=lambda s, b: resolved(b['text']), sync=True)
        self.assertEqual(stats['commands'], 1)
        self.assertEqual(stats['reported'], 1)
        self.assertEqual(len(fake.reports), 1)
        rid, status, text = fake.reports[0]
        self.assertEqual(rid, c['request_id'])
        self.assertEqual(status, 'resolved')
        self.assertIn('lampe', text)

    def test_empty_queue_nothing_reported(self):
        from src.runtime import command_drain as D
        fake = FakeRelay([])
        stats = D.poll_once(make_server(fake), parse_fn=lambda s, b: resolved('x'), sync=True)
        self.assertEqual(stats['commands'], 0)
        self.assertEqual(fake.reports, [])
        self.assertIn('get_commands', fake.ops)

    def test_relay_without_capability_skipped(self):
        from src.runtime import command_drain as D
        fake = FakeRelay([text_cmd()])
        stats = D.poll_once(make_server(fake, caps=('ble_scan',)),
                            parse_fn=lambda s, b: resolved('x'), sync=True)
        self.assertEqual(stats['relays_polled'], 0)
        self.assertEqual(fake.ops, [])

    def test_unreachable_relay_skipped_not_crashed(self):
        from src.runtime import command_drain as D
        fake = FakeRelay([text_cmd()], fail_ops=('get_commands',))
        stats = D.poll_once(make_server(fake), parse_fn=lambda s, b: resolved('x'), sync=True)
        self.assertEqual(stats['commands'], 0)
        self.assertEqual(fake.reports, [])
        self.assertTrue(stats['errors'])

    def test_voice_clip_transcribed_parsed_reported(self):
        from src.runtime import command_drain as D
        pcm = b'\x01\x02' * 9000  # 18000 bytes of fake 16 kHz PCM16
        c = voice_cmd(pcm)
        fake = FakeRelay([c])
        seen = {}

        def fetch(url, key, clip_id, nbytes, sha, **kw):
            seen['clip'] = clip_id
            self.assertEqual(nbytes, len(pcm))
            return pcm

        stats = D.poll_once(make_server(fake),
                            parse_fn=lambda s, b: resolved(b['text']),
                            fetch_voice_fn=fetch,
                            transcribe_fn=lambda p, lang: 'allume la lampe', sync=True)
        self.assertEqual(seen.get('clip'), 'vabc12')
        self.assertEqual(stats['reported'], 1)
        self.assertIn('lampe', fake.reports[0][2])

    def test_voice_without_transcription_reports_honestly(self):
        from src.runtime import command_drain as D
        pcm = b'\x00' * 32000  # 1 s of silence
        c = voice_cmd(pcm)
        fake = FakeRelay([c])
        stats = D.poll_once(make_server(fake),
                            parse_fn=lambda s, b: resolved('x'),
                            fetch_voice_fn=lambda *a, **k: pcm,
                            transcribe_fn=None,
                            stt_available=False, sync=True)
        self.assertEqual(stats['reported'], 1)
        rid, status, text = fake.reports[0]
        self.assertEqual(status, 'escalation_required')
        self.assertIn('transcription', text.lower())

    def test_parse_error_reported_not_stuck(self):
        from src.runtime import command_drain as D
        c = text_cmd('???')
        fake = FakeRelay([c])

        def bad_parse(s, b):
            raise CMD.CommandError(400, 'text must be 1..2000 characters')

        stats = D.poll_once(make_server(fake), parse_fn=bad_parse, sync=True)
        self.assertEqual(stats['reported'], 1)
        self.assertEqual(fake.reports[0][1], 'escalation_required')

    def test_async_workers_report_without_blocking(self):
        from src.runtime import command_drain as D
        c = text_cmd()
        fake = FakeRelay([c])
        stats = D.poll_once(make_server(fake), parse_fn=lambda s, b: resolved(b['text']))
        self.assertEqual(stats['commands'], 1)  # dispatched, worker still running
        for _ in range(100):
            if fake.reports:
                break
            time.sleep(0.05)
        self.assertEqual(len(fake.reports), 1)
        self.assertEqual(fake.reports[0][0], c['request_id'])

    def test_report_failure_counted_not_crashed(self):
        from src.runtime import command_drain as D
        fake = FakeRelay([text_cmd()], fail_ops=('report_command',))
        stats = D.poll_once(make_server(fake), parse_fn=lambda s, b: resolved('x'), sync=True)
        self.assertEqual(stats['commands'], 1)
        self.assertEqual(stats['reported'], 0)
        self.assertTrue(stats['errors'])


if __name__ == '__main__':
    unittest.main()
