"""V4-10 voice: typed intents only, refusal of risky requests, STT client against a fake WebSocket (SIMULATED)."""
import base64
import json
import os
import struct
import unittest

from src.ai import voice_intent as vi
from src.ai import voice_stt as stt

DEV = [{'key': 'dev-tv', 'category': 'tv'}, {'key': 'dev-ph', 'category': 'phone'}]


class Intents(unittest.TestCase):
    def test_sample_phrases_fr_en(self):
        cases = {
            'Find the nearby Bluetooth devices through the living-room TV': ('ble_scan_via_tv', 'dev-tv'),
            'Trouve les appareils Bluetooth via la télé du salon': ('ble_scan_via_tv', 'dev-tv'),
            'Pourquoi la télé se déconnecte ?': ('why_disconnect', 'dev-tv'),
            'Why does my phone disconnect?': ('why_disconnect', 'dev-ph'),
            'Découvre mes appareils': ('discover', 'fabric'),
            'Fais un diagnostic': ('diagnose', 'fabric'),
            'Termine la session': ('finish_session', 'fabric'),
        }
        for phrase, (intent, dev) in cases.items():
            with self.subTest(phrase=phrase):
                p = vi.compile_intent(phrase, DEV)
                self.assertEqual((p['intent'], p['device_key']), (intent, dev))
                self.assertIn('Proposal only', p['note'])

    def test_risky_or_unknown_requests_never_become_intents(self):
        for phrase in ('Éteins la télé', 'shutdown the TV', 'install this app', 'factory reset the router', 'what is the weather',
                       'adb shell rm -rf /', '', 'x' * 500, 'mot de passe du wifi'):
            with self.subTest(phrase=phrase[:30]):
                self.assertIsNone(vi.compile_intent(phrase, DEV)['intent'])

    def test_ambiguous_target_asks(self):
        p = vi.compile_intent('Bluetooth through the TV', DEV + [{'key': 'dev-tv2', 'category': 'tv'}])
        self.assertTrue(p['needs_target'])


class FakeSock:
    """Server side of a WebSocket: answers the handshake and the transcription events."""
    def __init__(self, final='Trouve les appareils Bluetooth', error=None):
        self.buf, self.sent, self.final, self.error, self.stage = b'', b'', final, error, 0
    def sendall(self, data):
        self.sent += data
        if self.stage == 0 and b'\r\n\r\n' in self.sent:
            self.buf += b'HTTP/1.1 101 Switching Protocols\r\n\r\n'; self.stage = 1
        elif self.stage == 1 and b'input_audio_buffer.commit' in self._client_texts():
            ev = {'type': 'error', 'error': {'message': self.error}} if self.error else \
                {'type': 'conversation.item.input_audio_transcription.completed', 'transcript': self.final}
            for e in ({'type': 'conversation.item.input_audio_transcription.delta', 'delta': 'Tro'}, ev):
                d = json.dumps(e).encode(); self.buf += bytes([0x81, 126]) + struct.pack('>H', len(d)) + d
            self.stage = 2
    def _client_texts(self):
        out, i = b'', self.sent.index(b'\r\n\r\n') + 4
        s = self.sent
        while i + 2 <= len(s):
            n = s[i + 1] & 0x7f; j = i + 2
            if n == 126: n, = struct.unpack('>H', s[j:j + 2]); j += 2
            elif n == 127: n, = struct.unpack('>Q', s[j:j + 8]); j += 8
            if j + 4 + n > len(s): break
            m = s[j:j + 4]; out += bytes(b ^ m[k % 4] for k, b in enumerate(s[j + 4:j + 4 + n])); i = j + 4 + n
        return out
    def recv(self, n):
        d, self.buf = self.buf[:n], self.buf[n:]; return d
    def close(self): pass


class STT(unittest.TestCase):
    def test_transcribe_protocol(self):
        sock = FakeSock()
        r = stt.transcribe(b'\x00\x01' * 16000, 'k', 'fr', connect=lambda addr, timeout: sock)
        self.assertEqual(r['transcript'], 'Trouve les appareils Bluetooth')
        msgs = sock._client_texts()
        self.assertIn(b'session.update', msgs); self.assertIn(b'"language": "fr"', msgs)
        self.assertIn(b'Authorization: Bearer k', sock.sent)

    def test_bounds_and_errors(self):
        c = lambda addr, timeout: FakeSock()
        for args in ((b'', 'k'), (b'\x00' * 3, 'k'), (b'\x00\x00' * (16000 * 16), 'k'), (b'\x00\x00', '')):
            with self.subTest(n=len(args[0])), self.assertRaises(stt.STTBlocked):
                stt.transcribe(*args, connect=c)
        with self.assertRaises(stt.STTBlocked):
            stt.transcribe(b'\x00\x00', 'k', 'de', connect=c)
        with self.assertRaises(stt.STTBlocked):
            stt.transcribe(b'\x00\x00', 'k', connect=lambda a, timeout: FakeSock(error='quota'))


if __name__ == '__main__':
    unittest.main()
