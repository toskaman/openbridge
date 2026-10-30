"""§7 stdlib-only PNG montage. No third-party packages (repo policy).

Decodes 8-bit non-interlaced PNGs (gray, gray+alpha, RGB, RGBA) and
re-encodes the combination. Anything else is rejected honestly, never
guessed: exotic PNGs fail with MontageError instead of producing garbage.
"""
import math
import struct
import zlib

MAX_IMAGES = 16
MAX_PIXELS = 64 * 1024 * 1024  # 64 MP cap per decode/combine
_SIG = b'\x89PNG\r\n\x1a\n'


class MontageError(ValueError):
    pass


def _chunks(raw):
    if raw[:8] != _SIG:
        raise MontageError('not a PNG')
    pos, out = 8, []
    try:
        while pos + 8 <= len(raw):
            (ln,) = struct.unpack('>I', raw[pos:pos + 4])
            typ = raw[pos + 4:pos + 8]
            data = raw[pos + 8:pos + 8 + ln]
            if len(data) != ln or pos + 12 + ln > len(raw):
                raise MontageError('truncated PNG')
            if zlib.crc32(typ + data) & 0xffffffff != struct.unpack('>I', raw[pos + 8 + ln:pos + 12 + ln])[0]:
                raise MontageError('PNG CRC mismatch')
            out.append((typ, data))
            pos += 12 + ln
            if typ == b'IEND':
                break
    except struct.error as e:
        raise MontageError('truncated PNG') from e
    return out


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png(raw):
    """Decode to (width, height, RGBA bytes). 8-bit, non-interlaced only."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > 64 * 1024 * 1024:
        raise MontageError('PNG too large or not bytes')
    chunks = _chunks(bytes(raw))
    ihdr = next((d for t, d in chunks if t == b'IHDR'), None)
    if ihdr is None or len(ihdr) != 13:
        raise MontageError('PNG without IHDR')
    w, h, depth, ctype, comp, filt, inter = struct.unpack('>IIBBBBB', ihdr)
    if depth != 8 or ctype not in (0, 2, 4, 6) or comp or filt or inter:
        raise MontageError(f'unsupported PNG: depth={depth} type={ctype} interlace={inter}')
    if w <= 0 or h <= 0 or w * h > MAX_PIXELS:
        raise MontageError('PNG dimensions out of bounds')
    try:
        scan = zlib.decompress(b''.join(d for t, d in chunks if t == b'IDAT'))
    except zlib.error as e:
        raise MontageError('PNG IDAT corrupt') from e
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    stride = w * ch
    if len(scan) != h * (stride + 1):
        raise MontageError('PNG scanline length mismatch')
    px = bytearray(w * h * 4)
    prev = bytearray(stride)
    for y in range(h):
        f = scan[y * (stride + 1)]
        if f > 4:
            raise MontageError('unknown PNG filter')
        line = bytearray(scan[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b = prev[i]
            c = prev[i - ch] if i >= ch else 0
            line[i] = (line[i] + (0, a, b, (a + b) // 2, _paeth(a, b, c))[f]) & 0xff
        for x in range(w):
            s = line[x * ch:(x + 1) * ch]
            if ctype == 0:
                r, g, b_, a_ = s[0], s[0], s[0], 255
            elif ctype == 2:
                r, g, b_, a_ = s[0], s[1], s[2], 255
            elif ctype == 4:
                r, g, b_, a_ = s[0], s[0], s[0], s[1]
            else:
                r, g, b_, a_ = s[0], s[1], s[2], s[3]
            o = (y * w + x) * 4
            px[o:o + 4] = bytes((r, g, b_, a_))
        prev = line
    return w, h, bytes(px)


def png_size(raw):
    chunks = _chunks(bytes(raw))
    ihdr = next((d for t, d in chunks if t == b'IHDR'), None)
    if ihdr is None or len(ihdr) != 13:
        raise MontageError('PNG without IHDR')
    w, h = struct.unpack('>II', ihdr[:8])
    if w <= 0 or h <= 0 or w * h > MAX_PIXELS:
        raise MontageError('PNG dimensions out of bounds')
    return w, h


def encode_png(w, h, rgba):
    """Encode RGBA bytes to an 8-bit RGBA PNG (filter 0 rows)."""
    if w <= 0 or h <= 0 or w * h > MAX_PIXELS or len(rgba) != w * h * 4:
        raise MontageError('bad dimensions for encode')
    stride = w * 4
    scan = b''.join(b'\x00' + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(h))
    out = [b'\x89PNG\r\n\x1a\n']

    def chunk(typ, data):
        out.append(struct.pack('>I', len(data)) + typ + data +
                   struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff))
    chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
    chunk(b'IDAT', zlib.compress(bytes(scan), 6))
    chunk(b'IEND', b'')
    return b''.join(out)


def combine(images, layout='row', bg=(0, 0, 0, 255)):
    """Combine PNG byte strings into one PNG. layout: 'row' or 'grid'."""
    if layout not in ('row', 'grid'):
        raise MontageError(f'unknown layout {layout!r}')
    if not images or len(images) > MAX_IMAGES:
        raise MontageError(f'need 1..{MAX_IMAGES} images')
    if len(bg) != 4 or any(not 0 <= c <= 255 for c in bg):
        raise MontageError('bad background color')
    decoded = [decode_png(im) for im in images]
    if layout == 'row':
        total_w = sum(w for w, _, _ in decoded)
        total_h = max(h for _, h, _ in decoded)
        cells = []
        x = 0
        for w, h, _ in decoded:
            cells.append((x, 0))
            x += w
    else:
        ncols = math.ceil(math.sqrt(len(decoded)))
        cell_w = max(w for w, _, _ in decoded)
        cell_h = max(h for _, h, _ in decoded)
        total_w, total_h = ncols * cell_w, math.ceil(len(decoded) / ncols) * cell_h
        cells = [((i % ncols) * cell_w, (i // ncols) * cell_h) for i in range(len(decoded))]
    if total_w * total_h > MAX_PIXELS:
        raise MontageError('montage too large')
    canvas = bytearray(bytes(bg) * (total_w * total_h))
    for (w, h, px), (ox, oy) in zip(decoded, cells):
        for y in range(h):
            src = y * w * 4
            dst = ((oy + y) * total_w + ox) * 4
            canvas[dst:dst + w * 4] = px[src:src + w * 4]
    return encode_png(total_w, total_h, bytes(canvas))
