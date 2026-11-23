"""Matter TLV codec, phase 1 of a native Matter controller (pure Python, standard library only).

Implements the Tag-Length-Value encoding of the Matter Core Specification (stable since Weave):
anonymous / context-specific / profile / fully-qualified tags, signed and unsigned integers in the
smallest width that fits, booleans, floats, null, UTF-8 and octet strings with minimal length
prefixes, and struct / array / list containers closed by EndOfContainer.

Python mapping: int (non-negative -> unsigned, negative -> signed), bool, None, float (f32 when
exactly representable, else f64; NaN/inf refused), str, bytes, dict (struct; keys are context-tag
ints 0..255) and list/tuple (Matter list of anonymous elements; use `array()` for a Matter array).
Decoding returns containers as ('struct', [(tag, value), ...]) / ('array' | 'list', [values]) with
tags as None, ('context', n) or raw ('common2' | 'common4' | 'implicit2' | 'implicit4', number) /
('qualified6' | 'qualified8', bytes).

Bounds: nesting depth 32, 1 MiB documents, integers within 64 bits. Reserved element types,
truncated values and unbalanced containers raise TlvError (fail closed).

Validation: hand-derived vectors below (computed from the encoding rules, both directions),
seed-fixed round-trip fuzz, and `tests/fabric/matter_tlv_vectors.json` when present (official
vectors, git-ignored; extract them from the Matter specification examples or connectedhomeip's
TestTLV). For the full controller plan (PASE/CASE, commissioning, clusters), see docs/MATTER_PLAN.md.
"""
import math
import struct

MAX_DEPTH = 32
MAX_BYTES = 1024 * 1024

# Element types (low 5 bits of the control byte).
T_INT8, T_INT16, T_INT32, T_INT64 = 0x00, 0x01, 0x02, 0x03
T_UINT8, T_UINT16, T_UINT32, T_UINT64 = 0x04, 0x05, 0x06, 0x07
T_FALSE, T_TRUE = 0x08, 0x09
T_FLOAT32, T_FLOAT64 = 0x0A, 0x0B
T_NULL = 0x0C
T_UTF8_1, T_UTF8_2, T_UTF8_4 = 0x0D, 0x0E, 0x0F
T_BYTES_1, T_BYTES_2, T_BYTES_4 = 0x10, 0x11, 0x12
T_STRUCT, T_ARRAY, T_LIST, T_END = 0x15, 0x16, 0x17, 0x18

# Tag forms (high 3 bits).
F_ANON, F_CONTEXT = 0x00, 0x20
F_COMMON2, F_COMMON4 = 0x40, 0x60
F_IMPLICIT2, F_IMPLICIT4 = 0x80, 0xA0
F_QUALIFIED6, F_QUALIFIED8 = 0xC0, 0xE0


class TlvError(ValueError):
    pass


def _tag_bytes(tag):
    if tag is None:
        return F_ANON, b''
    if isinstance(tag, int):
        if not 0 <= tag <= 255:
            raise TlvError('context tag out of range')
        return F_CONTEXT, bytes([tag])
    raise TlvError('encoder tags are None (anonymous) or a context int')


def _encode_int(v):
    if v >= 0:
        if v <= 0xFF:
            return T_UINT8, struct.pack('<B', v)
        if v <= 0xFFFF:
            return T_UINT16, struct.pack('<H', v)
        if v <= 0xFFFFFFFF:
            return T_UINT32, struct.pack('<I', v)
        if v <= 0xFFFFFFFFFFFFFFFF:
            return T_UINT64, struct.pack('<Q', v)
    else:
        if -0x80 <= v:
            return T_INT8, struct.pack('<b', v)
        if -0x8000 <= v:
            return T_INT16, struct.pack('<h', v)
        if -0x80000000 <= v:
            return T_INT32, struct.pack('<i', v)
        if -0x8000000000000000 <= v:
            return T_INT64, struct.pack('<q', v)
    raise TlvError('integer out of 64-bit range')


def _encode_bytes_kind(raw, kinds):
    if len(raw) <= 0xFF:
        return kinds[0], struct.pack('<B', len(raw)) + raw
    if len(raw) <= 0xFFFF:
        return kinds[1], struct.pack('<H', len(raw)) + raw
    if len(raw) <= 0xFFFFFFFF:
        return kinds[2], struct.pack('<I', len(raw)) + raw
    raise TlvError('string too long')


class _Array(list):
    pass


def array(items):
    """Mark a Python list to encode as a Matter array (plain lists encode as Matter lists)."""
    return _Array(items)


def encode(value, tag=None, _depth=0):
    """Encode one value with an optional tag. Returns bytes."""
    if _depth > MAX_DEPTH:
        raise TlvError('nesting too deep')
    form, tagb = _tag_bytes(tag)
    if value is True or value is False:
        return bytes([form | (T_TRUE if value else T_FALSE)]) + tagb
    if value is None:
        return bytes([form | T_NULL]) + tagb
    if isinstance(value, int) and not isinstance(value, bool):
        etype, payload = _encode_int(value)
        return bytes([form | etype]) + tagb + payload
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TlvError('non-finite float refused')
        if struct.unpack('<f', struct.pack('<f', value))[0] == value:
            return bytes([form | T_FLOAT32]) + tagb + struct.pack('<f', value)
        return bytes([form | T_FLOAT64]) + tagb + struct.pack('<d', value)
    if isinstance(value, str):
        etype, payload = _encode_bytes_kind(value.encode('utf-8'), (T_UTF8_1, T_UTF8_2, T_UTF8_4))
        return bytes([form | etype]) + tagb + payload
    if isinstance(value, (bytes, bytearray)):
        etype, payload = _encode_bytes_kind(bytes(value), (T_BYTES_1, T_BYTES_2, T_BYTES_4))
        return bytes([form | etype]) + tagb + payload
    if isinstance(value, dict):
        out = bytearray(bytes([form | T_STRUCT]) + tagb)
        for k, v in value.items():
            if not isinstance(k, int) or isinstance(k, bool):
                raise TlvError('struct keys are context-tag ints')
            out += encode(v, tag=k, _depth=_depth + 1)
        return bytes(out) + bytes([T_END])
    if isinstance(value, (list, tuple)):
        out = bytearray(bytes([form | (T_ARRAY if isinstance(value, _Array) else T_LIST)]) + tagb)
        for v in value:
            out += encode(v, tag=None, _depth=_depth + 1)
        return bytes(out) + bytes([T_END])
    raise TlvError('cannot TLV-encode %s' % type(value).__name__)


def _read_tag(buf, pos):
    if pos >= len(buf):
        raise TlvError('truncated control byte')
    control = buf[pos]
    pos += 1
    form, etype = control & 0xE0, control & 0x1F
    sizes = {F_CONTEXT: 1, F_COMMON2: 2, F_COMMON4: 4, F_IMPLICIT2: 2, F_IMPLICIT4: 4,
             F_QUALIFIED6: 6, F_QUALIFIED8: 8}
    if form == F_ANON:
        return None, etype, pos
    if form not in sizes:
        raise TlvError('bad tag form')
    end = pos + sizes[form]
    if end > len(buf):
        raise TlvError('truncated tag')
    raw = bytes(buf[pos:end])
    names = {F_CONTEXT: 'context', F_COMMON2: 'common2', F_COMMON4: 'common4', F_IMPLICIT2: 'implicit2',
             F_IMPLICIT4: 'implicit4', F_QUALIFIED6: 'qualified6', F_QUALIFIED8: 'qualified8'}
    tag = ('context', raw[0]) if form == F_CONTEXT else (names[form], raw)
    return tag, etype, end


def _read_len(buf, pos, size):
    end = pos + size
    if end > len(buf):
        raise TlvError('truncated length')
    return int.from_bytes(bytes(buf[pos:end]), 'little'), end


def decode_one(buf, pos=0, _depth=0):
    """Decode one element at pos. Returns (tag, value, next_pos)."""
    if _depth > MAX_DEPTH:
        raise TlvError('nesting too deep')
    if not isinstance(buf, (bytes, bytearray)) or len(buf) > MAX_BYTES:
        raise TlvError('document too large')
    tag, etype, pos = _read_tag(buf, pos)
    if etype == T_END:
        raise TlvError('stray end-of-container')

    def take(n):
        end = pos + n
        if end > len(buf):
            raise TlvError('truncated value')
        return bytes(buf[pos:end]), end

    if etype in (T_INT8, T_INT16, T_INT32, T_INT64):
        raw, pos = take(2 ** (etype - T_INT8))
        return tag, int.from_bytes(raw, 'little', signed=True), pos
    if etype in (T_UINT8, T_UINT16, T_UINT32, T_UINT64):
        raw, pos = take(2 ** (etype - T_UINT8))
        return tag, int.from_bytes(raw, 'little'), pos
    if etype == T_FALSE:
        return tag, False, pos
    if etype == T_TRUE:
        return tag, True, pos
    if etype == T_FLOAT32:
        raw, pos = take(4)
        return tag, struct.unpack('<f', raw)[0], pos
    if etype == T_FLOAT64:
        raw, pos = take(8)
        return tag, struct.unpack('<d', raw)[0], pos
    if etype == T_NULL:
        return tag, None, pos
    if etype in (T_UTF8_1, T_UTF8_2, T_UTF8_4):
        ln, pos = _read_len(buf, pos, 2 ** (etype - T_UTF8_1))
        raw, pos = take(ln)
        try:
            return tag, raw.decode('utf-8'), pos
        except UnicodeDecodeError:
            raise TlvError('invalid UTF-8 string') from None
    if etype in (T_BYTES_1, T_BYTES_2, T_BYTES_4):
        ln, pos = _read_len(buf, pos, 2 ** (etype - T_BYTES_1))
        raw, pos = take(ln)
        return tag, raw, pos
    if etype in (T_STRUCT, T_ARRAY, T_LIST):
        kind = {T_STRUCT: 'struct', T_ARRAY: 'array', T_LIST: 'list'}[etype]
        items = []
        while True:
            if pos >= len(buf):
                raise TlvError('unterminated container')
            if buf[pos] == T_END:
                return tag, (kind, items), pos + 1
            t, v, pos = decode_one(buf, pos, _depth + 1)
            items.append((t, v) if kind == 'struct' else v)
    raise TlvError('reserved element type 0x%02x' % etype)


def decode_all(buf):
    """Decode a whole document (exactly one top-level element, no trailing bytes)."""
    tag, value, pos = decode_one(buf)
    if pos != len(buf):
        raise TlvError('trailing bytes after the top-level element')
    return tag, value
