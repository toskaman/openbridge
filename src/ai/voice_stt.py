"""Muse Voice Transcribe 1.0 realtime client (wss://api.meta.ai/v1/asr/realtime), push-to-talk, server side.

The API key never reaches the browser. The browser posts one short PCM16 mono 16 kHz clip (push-to-talk, max 15 s);
this module opens one WebSocket, sends `session.update` (language), `input_audio_buffer.append` chunks and
`input_audio_buffer.commit`, then waits for `conversation.item.input_audio_transcription.completed`.
Stdlib only (minimal RFC 6455 client). Status: IMPLEMENTED_UNVERIFIED until a live receipt is recorded.
Egress disclosure: the audio clip goes to Meta; nothing else does."""
import base64
import json
import os
import socket
import ssl
import struct
from urllib.parse import urlsplit

MODEL_ID = 'muse-voice-transcribe-1.0'
URL = 'wss://api.meta.ai/v1/asr/realtime'
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

    def send(self, obj):
        data = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(data)
        hdr = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack('>H', n) if n < 65536 else bytes([0x80 | 127]) + struct.pack('>Q', n))
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
                raise STTBlocked('server closed the session')
            if op == 1:
                return json.loads(data)

    def close(self):
        try: self.s.close()
        except OSError: pass


def transcribe(pcm16, api_key, language='fr', connect=None, max_events=400):
    if not api_key:
        raise STTBlocked('Meta credential unavailable')
    if not isinstance(pcm16, (bytes, bytearray)) or not pcm16 or len(pcm16) > MAX_SECONDS * RATE * 2 or len(pcm16) % 2:
        raise STTBlocked(f'push-to-talk clip must be 16 kHz PCM16 mono, at most {MAX_SECONDS} s')
    if language not in ('fr', 'en'):
        raise STTBlocked('language must be fr or en')
    ws = _WS(URL + f'?model={MODEL_ID}&intent=transcription', {'Authorization': 'Bearer ' + api_key}, connect=connect)
    try:
        ws.send({'type': 'session.update', 'session': {'input_audio_format': 'pcm16', 'transcription': {'model': MODEL_ID, 'language': language}}})
        for i in range(0, len(pcm16), 32000):
            ws.send({'type': 'input_audio_buffer.append', 'audio': base64.b64encode(pcm16[i:i + 32000]).decode()})
        ws.send({'type': 'input_audio_buffer.commit'})
        for _ in range(max_events):
            ev = ws.recv()
            if ev.get('type') == 'conversation.item.input_audio_transcription.completed':
                t = ev.get('transcript')
                if not isinstance(t, str):
                    raise STTBlocked('invalid transcript')
                return {'transcript': t[:400], 'model': MODEL_ID, 'language': language, 'seconds': round(len(pcm16) / 2 / RATE, 1)}
            if ev.get('type') == 'error':
                raise STTBlocked('Meta STT error: ' + str((ev.get('error') or {}).get('message', ''))[:120])
        raise STTBlocked('no final transcript')
    finally:
        ws.close()
