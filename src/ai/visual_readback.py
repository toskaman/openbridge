"""Visual read-back (V4-07): a screenshot judged by local Muse Glimmer, checked against a structured read.

Trust order (spec): the structured ADB read (focused window, power state) is primary; the image is a second,
independent opinion. Agreement -> CONFIRMED; disagreement -> INCONCLUSIVE (stop, ask the owner); model or capture
unavailable -> STRUCTURED_ONLY. The model never clicks and never chooses an action.

Privacy: the frame stays on this PC (Glimmer runs locally, no cloud path here); the status-bar strip (notifications,
account badges) is cropped away before the model sees it; only the SHA-256 of the cropped frame is kept.
"""
import base64
import hashlib
import json
import re
import struct
import time
import zlib

from src.ai.broker import ModelBlocked

SCREEN_CLASSES = ('home_launcher', 'settings', 'media_playback', 'other_app', 'dialog', 'screen_off_or_black')
STATUS_BAR_FRACTION = 0.08
SETTINGS_PKGS = ('com.android.tv.settings', 'com.android.settings', 'com.google.android.tv.settings')
MEDIA_HINTS = ('youtube', 'netflix', 'player', 'video', 'tv.player', 'plex', 'vlc', 'disney', 'primevideo', 'canal')


# ---------- minimal PNG crop (8-bit RGB/RGBA, non-interlaced, as produced by `screencap -p`) ----------
def _chunks(png):
    i = 8
    while i < len(png):
        n, = struct.unpack('>I', png[i:i + 4]); kind = png[i + 4:i + 8]
        yield kind, png[i + 8:i + 8 + n]
        i += 12 + n


def _unfilter(raw, w, h, bpp):
    stride = w * bpp
    out, prev, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]; line = bytearray(raw[i + 1:i + 1 + stride]); i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]; c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out.append(bytes(line)); prev = line
    return out


def crop_status_bar(png, fraction=STATUS_BAR_FRACTION, step=1):
    """Return a new PNG without the top `fraction` of rows (optionally keeping every `step`-th row/col)."""
    if not png.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('not a PNG')
    ihdr = next(d for k, d in _chunks(png) if k == b'IHDR')
    w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', ihdr)
    if depth != 8 or ctype not in (2, 6) or interlace:
        raise ValueError('unsupported PNG layout')
    if w * h > 4096 * 4096:
        raise ValueError('frame too large')
    bpp = 4 if ctype == 6 else 3
    rows = _unfilter(zlib.decompress(b''.join(d for k, d in _chunks(png) if k == b'IDAT')), w, h, bpp)
    rows = rows[int(h * fraction):][::step]
    if step > 1:
        rows = [b''.join(r[x:x + bpp] for x in range(0, len(r), bpp * step)) for r in rows]
        w = len(rows[0]) // bpp
    body = zlib.compress(b''.join(b'\x00' + r for r in rows), 6)
    chunk = lambda k, d: struct.pack('>I', len(d)) + k + d + struct.pack('>I', zlib.crc32(k + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, len(rows), 8, ctype, 0, 0, 0)) + chunk(b'IDAT', body) + chunk(b'IEND', b'')


# ---------- structured side ----------
def structured_class(window_dump, power_state):
    if power_state in ('asleep', 'dozing'):
        return 'screen_off_or_black', 'dumpsys power'
    m = re.search(r'mCurrentFocus=Window\{[^ ]+ [^ ]+ ([A-Za-z0-9_.]+)/', window_dump or '')
    if not m:
        m2 = re.search(r'mCurrentFocus=Window\{[^}]*\b(Application Not Responding|PopupWindow|Toast)', window_dump or '')
        return ('dialog', 'dumpsys window') if m2 else (None, 'dumpsys window (no focused window)')
    pkg = m[1].lower()
    if 'launcher' in pkg or pkg.endswith('.home'):
        return 'home_launcher', 'dumpsys window'
    if pkg in SETTINGS_PKGS:
        return 'settings', 'dumpsys window'
    if any(h in pkg for h in MEDIA_HINTS):
        return 'media_playback', 'dumpsys window'
    return 'other_app', 'dumpsys window'


# ---------- model side ----------
def glimmer_classify(broker, png):
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['screen', 'evidence', 'confidence'],
              'properties': {'screen': {'type': 'string', 'enum': list(SCREEN_CLASSES)},
                             'evidence': {'type': 'string'}, 'confidence': {'type': 'string', 'enum': ['low', 'medium', 'high']}}}
    payload = {'model': broker.model_id, 'stream': False, 'format': schema, 'keep_alive': '60s', **broker.extra,
               'options': dict(broker.options),
               'messages': [{'role': 'system', 'content':
                             'You classify one screenshot of an Android TV or phone. Respond only as JSON matching the schema. '
                             'evidence: at most 20 words naming what is visible (no personal names, account names or text from '
                             'notifications). Do not suggest any action.'},
                            {'role': 'user', 'content': 'Which screen class is shown?', 'images': [base64.b64encode(png).decode()]}]}
    started = time.monotonic()
    out, resp = broker._call(payload)
    if not isinstance(out, dict) or out.get('screen') not in SCREEN_CLASSES or out.get('confidence') not in ('low', 'medium', 'high'):
        raise ModelBlocked('Invalid visual classification')
    return {'screen': out['screen'], 'confidence': out['confidence'], 'evidence': str(out.get('evidence', ''))[:160],
            'model_id': broker.model_id, 'elapsed_ms': round((time.monotonic() - started) * 1000)}


def readback(capture, read, broker):
    """capture() -> PNG bytes; read(*args) -> allowlisted ADB shell output; broker: local Glimmer or None."""
    try:
        power = re.search(r'mWakefulness=(\w+)', read('dumpsys', 'power') or '')
        power = power[1].lower() if power else None
    except (ValueError, OSError):
        power = None
    try:
        windows = read('dumpsys', 'window', 'windows')
    except (ValueError, OSError):
        windows = ''
    s_class, s_src = structured_class(windows, power)
    result = {'structured': {'screen': s_class, 'source': s_src}, 'visual': None, 'frame_sha256': None}
    try:
        frame = crop_status_bar(capture())
        result['frame_sha256'] = hashlib.sha256(frame).hexdigest()
    except (ValueError, OSError) as e:
        result.update(verdict='STRUCTURED_ONLY', reason=f'capture unavailable ({type(e).__name__})')
        return result
    if broker is None or not getattr(broker, 'ready', lambda: False)():
        result.update(verdict='STRUCTURED_ONLY', reason='local Muse Glimmer not running; no cloud fallback')
        return result
    try:
        result['visual'] = glimmer_classify(broker, frame)
    except Exception as e:
        result.update(verdict='STRUCTURED_ONLY', reason=f'visual model failed ({type(e).__name__})')
        return result
    if s_class is None:
        result.update(verdict='VISUAL_ONLY', reason='no structured value to compare; visual opinion shown as INFERRED')
    elif s_class == result['visual']['screen']:
        result.update(verdict='CONFIRMED', reason='structured read and screenshot agree')
    else:
        result.update(verdict='INCONCLUSIVE', reason='structured read and screenshot disagree; stop and let the owner check')
    return result
