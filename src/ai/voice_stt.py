"""Muse Voice Transcribe 1.0 realtime client (wss://api.meta.ai/v1/asr/realtime), push-to-talk, server side.

The API key never reaches the browser. The browser posts one short PCM16 mono 16 kHz clip (push-to-talk, max 15 s).
Protocol per https://dev.meta.ai/docs/speech-to-text: first text frame carries authorization.accessToken,
audioEncoding PCM_16KHZ, mode PUSH_TO_TALK and languageBias; the server acknowledges with {sessionId}; audio goes
as binary frames paced near real time; {"type":"endStream"} ends input; {"type":"transcript","final":true} is the
result. Stdlib only (minimal RFC 6455 client).
Egress disclosure: the audio clip goes to Meta; nothing else does."""
import base64
import json
import os
import socket
import ssl
import struct
import time
from urllib.parse import urlsplit

MODEL_ID = 'muse-voice-transcribe-1.0'
URL = 'wss://api.meta.ai/v1/asr/realtime'
LANG = {'fr': ['French'], 'en': ['English']}
CHUNK = 3200          # 100 ms of 16 kHz PCM16
MAX_SECONDS = 15
RATE = 16000


class STTBlocked(ValueError):
    pass


class _WS:
    def __init__(self, url, headers, timeout=20, connect=None):
        u = urlsplit(url)
        if u.scheme != 'wss' or u.hostname != 'api.meta.ai':
            raise STTBlocked('only the official Meta endpoint is allowed')
        raw = (connect or socket.create_connection)((u.hostname, 443), timeout=timeout)
        self.s = ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname) if connect is None else raw
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f'GET {u.path}?{u.query} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
               f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in headers.items()) + '\r\n')
        self.s.sendall(req.encode())
        head = b''
        while b'\r\n\r\n' not in head:
            c = self.s.recv(1)
            if not c or len(head) > 8192:
                raise STTBlocked('handshake failed')
            head += c
        if b' 101 ' not in head.split(b'\r\n')[0]:
            raise STTBlocked('handshake refused: ' + head.split(b'\r\n')[0].decode(errors='replace')[:60])

    def send(self, obj, binary=False):
        data = obj if binary else json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        hdr = bytes([0x82 if binary else 0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        b = b''
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise STTBlocked('connection closed')
            b += c
        return b

    def recv(self):
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7f
            if n == 126: n, = struct.unpack('>H', self._read(2))
            elif n == 127: n, = struct.unpack('>Q', self._read(8))
            if n > 1 << 20:
                raise STTBlocked('frame too large')
            data = self._read(n)
            op = b0 & 0x0f
            if op == 8:
                return {'type': 'closed'}
            if op == 1:
                return json.loads(data)

    def close(self):
        try: self.s.close()
        except OSError: pass


def transcribe(pcm16, api_key, language='fr', connect=None, max_events=400, pace=True):
    if not api_key:
        raise STTBlocked('Meta credential unavailable')
    if not isinstance(pcm16, (bytes, bytearray)) or not pcm16 or len(pcm16) > MAX_SECONDS * RATE * 2 or len(pcm16) % 2:
        raise STTBlocked(f'push-to-talk clip must be 16 kHz PCM16 mono, at most {MAX_SECONDS} s')
    if language not in ('fr', 'en'):
        raise STTBlocked('language must be fr or en')
    ws = _WS(URL, {}, connect=connect)
    try:
        ws.send({'authorization': {'accessToken': 'Bearer ' + api_key}, 'audioEncoding': 'PCM_16KHZ', 'model': MODEL_ID,
                 'mode': 'PUSH_TO_TALK', 'partialMode': 'CUMULATIVE', 'emitAudioProgress': False, 'languageBias': LANG[language]})
        ack = ws.recv()
        if ack.get('type') == 'error' or 'sessionId' not in ack:
            raise STTBlocked('Meta STT refused the session: ' + str(ack.get('message', ''))[:120])
        for i in range(0, len(pcm16), CHUNK):
            ws.send(bytes(pcm16[i:i + CHUNK]), binary=True)
            if pace:
                time.sleep(0.09)
        ws.send({'type': 'endStream'})
        last = ''
        for _ in range(max_events):
            ev = ws.recv()
            if ev.get('type') == 'closed':
                break
            if ev.get('type') == 'transcript':
                last = ev.get('transcript') if isinstance(ev.get('transcript'), str) else last
                if ev.get('final') is True:
                    return {'transcript': last[:400], 'model': MODEL_ID, 'language': language, 'seconds': round(len(pcm16) / 2 / RATE, 1),
                            'session_id': str(ack['sessionId'])[:80]}
            if ev.get('type') == 'error':
                raise STTBlocked('Meta STT error: ' + str(ev.get('message', ''))[:120])
        raise STTBlocked('no final transcript')
    finally:
        ws.close()
