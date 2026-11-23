"""BridgeWindows v5 sealed transport core (standard library only, with an optional fast backend).

Implements `BridgeWindows-v4/docs/SEALED_TRANSPORT_DESIGN.md`: a PSK-confirmed ephemeral-X25519
handshake, HKDF-SHA256 session keys, and XChaCha20-Poly1305 records. Pure-Python primitives
(ChaCha20, Poly1305, HChaCha20, HKDF) are verified byte-for-byte against libsodium (PyNaCl),
`cryptography` and PyCryptodome in `tests/fabric/test_sealed_v5.py`; when `cryptography` is installed
the bulk AEAD step uses it automatically (same wire bytes, reported by `backend()`).

Wire layout (all fixed-size, all bounds-checked):
- handshake: A->B: na(16) || EA(32); B->A: nb(16) || EB(32) || mac_b(32); A->B: mac_a(32).
- transcript = na || nb || EA || EB (96 bytes, in that order on both sides).
- conf_key = HKDF(PSK, salt=b'', info=b'ob-v5-confirm-v1').
- mac_a = HMAC-SHA256(conf_key, b'A' + transcript); mac_b likewise with b'B'.
- shared = X25519(ea, EB); all-zero refused. thash = SHA256(transcript); session_id = thash[:16].
- key_AB = HKDF(shared, salt=thash, info=b'ob-v5-A-to-B-v1'); key_BA likewise. Rekey = re-handshake.
- record nonce (24 bytes) = dir_prefix(4) || zeros(12) || counter_be(8). NOTE: the design doc says
  "4-byte prefix + 8-byte counter" (12 bytes), which fits ChaCha20-Poly1305 but not XChaCha20; the
  zero middle keeps uniqueness (one key per direction, counter strictly increasing) while making a
  valid 24-byte nonce. Counter and direction are also bound in the AD.
- AD = len(agent_id)(1) || agent_id || session_id(16) || dir(1: b'A'/b'B') || counter_be(8).
- frame = counter_be(8) || ciphertext+tag. The receiver enforces the exact next counter, so a
  replay, duplicate, reorder or drop fails closed. Frames stop before 2**32 per direction.

What this module does NOT do: TCP framing, the v4 hello, negotiation/downgrade policy (the adapter
refuses plain when `--require-sealed`), rotation timers (see `Session.stats()`), key wiping beyond
dropping references. PSK enrollment/rotation stays out of scope per the design's threat model.
"""
import hashlib
import hmac
import secrets
import struct

INFO_CONFIRM = b'ob-v5-confirm-v1'
INFO_AB = b'ob-v5-A-to-B-v1'
INFO_BA = b'ob-v5-B-to-A-v1'
DIR_A = b'OB-A'
DIR_B = b'OB-B'
MAX_FRAMES = 2 ** 32
MAX_PLAINTEXT = 16 * 1024 * 1024


class SealedError(ValueError):
    pass


def backend():
    """'cryptography' when its C implementation accelerates the bulk AEAD step, else 'pure-python'."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305 as _C
        _C(b'\0' * 32)
        return 'cryptography'
    except Exception:
        return 'pure-python'


# ---------- ChaCha20 (RFC 8439 section 2) ----------

def _rotl(v, n):
    return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF


def _qr(x, a, b, c, d):
    x[a] = (x[a] + x[b]) & 0xFFFFFFFF
    x[d] ^= x[a]
    x[d] = _rotl(x[d], 16)
    x[c] = (x[c] + x[d]) & 0xFFFFFFFF
    x[b] ^= x[c]
    x[b] = _rotl(x[b], 12)
    x[a] = (x[a] + x[b]) & 0xFFFFFFFF
    x[d] ^= x[a]
    x[d] = _rotl(x[d], 8)
    x[c] = (x[c] + x[d]) & 0xFFFFFFFF
    x[b] ^= x[c]
    x[b] = _rotl(x[b], 7)


def _rounds(x):
    for _ in range(10):
        _qr(x, 0, 4, 8, 12)
        _qr(x, 1, 5, 9, 13)
        _qr(x, 2, 6, 10, 14)
        _qr(x, 3, 7, 11, 15)
        _qr(x, 0, 5, 10, 15)
        _qr(x, 1, 6, 11, 12)
        _qr(x, 2, 7, 8, 13)
        _qr(x, 3, 4, 9, 14)


_CST = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)


def chacha20_block(key, counter, nonce12):
    """One 64-byte ChaCha20 block (RFC 8439 section 2.3)."""
    if len(key) != 32 or len(nonce12) != 12 or not 0 <= counter < 2 ** 32:
        raise SealedError('bad chacha20 block inputs')
    x = list(_CST) + list(struct.unpack('<8I', key)) + [counter] + list(struct.unpack('<3I', nonce12))
    w = list(x)
    _rounds(x)
    return struct.pack('<16I', *[(a + b) & 0xFFFFFFFF for a, b in zip(x, w)])


def chacha20_stream(key, nonce12, length, counter=0):
    out = bytearray()
    while len(out) < length:
        out += chacha20_block(key, counter, nonce12)
        counter += 1
    return bytes(out[:length])


# ---------- Poly1305 (RFC 8439 section 2.5) ----------

_P = 2 ** 130 - 5


def poly1305_mac(key, msg):
    """16-byte Poly1305 tag."""
    if len(key) != 32:
        raise SealedError('bad poly1305 key')
    r = int.from_bytes(key[:16], 'little') & 0xFFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:], 'little')
    acc = 0
    for i in range(0, len(msg), 16):
        n = int.from_bytes(msg[i:i + 16] + b'\x01', 'little')
        acc = ((acc + n) * r) % _P
    return ((acc + s) % 2 ** 128).to_bytes(16, 'little')


# ---------- ChaCha20-Poly1305 AEAD (RFC 8439 section 2.8) ----------

def _aead_mac(key, nonce12, ad, ciphertext):
    poly_key = chacha20_block(key, 0, nonce12)[:32]

    def pad16(b):
        return b + b'\0' * (-len(b) % 16)

    mac_data = pad16(ad) + pad16(ciphertext) + struct.pack('<QQ', len(ad), len(ciphertext))
    return poly1305_mac(poly_key, mac_data)


def aead_seal(key, nonce12, plaintext, ad=b''):
    """ChaCha20-Poly1305 encrypt; returns ciphertext || tag."""
    if len(key) != 32 or len(nonce12) != 12:
        raise SealedError('bad aead inputs')
    stream = chacha20_stream(key, nonce12, len(plaintext), counter=1)
    ct = bytes(a ^ b for a, b in zip(plaintext, stream))
    return ct + _aead_mac(key, nonce12, ad, ct)


def aead_open(key, nonce12, sealed, ad=b''):
    """ChaCha20-Poly1305 decrypt; the tag is verified (constant time) before anything is returned."""
    if len(key) != 32 or len(nonce12) != 12 or len(sealed) < 16:
        raise SealedError('bad aead inputs')
    ct, tag = sealed[:-16], sealed[-16:]
    if not hmac.compare_digest(_aead_mac(key, nonce12, ad, ct), tag):
        raise SealedError('forgery or corruption: AEAD tag mismatch')
    stream = chacha20_stream(key, nonce12, len(ct), counter=1)
    return bytes(a ^ b for a, b in zip(ct, stream))


# ---------- HChaCha20 + XChaCha20 (draft-arciszewski-xchacha) ----------

def hchacha20(key, nonce16):
    """32-byte HChaCha20 output: ChaCha20 rounds, no feed-forward add, words 0-3 and 12-15."""
    if len(key) != 32 or len(nonce16) != 16:
        raise SealedError('bad hchacha20 inputs')
    x = list(_CST) + list(struct.unpack('<8I', key)) + list(struct.unpack('<4I', nonce16))
    _rounds(x)
    return struct.pack('<8I', x[0], x[1], x[2], x[3], x[12], x[13], x[14], x[15])


def _xsub(key, nonce24):
    if len(key) != 32 or len(nonce24) != 24:
        raise SealedError('bad xchacha20 inputs')
    return hchacha20(key, nonce24[:16]), b'\0' * 4 + nonce24[16:]


def xseal(key, nonce24, plaintext, ad=b''):
    """XChaCha20-Poly1305 encrypt; returns ciphertext || tag. Uses the C backend when available."""
    subkey, nonce12 = _xsub(key, nonce24)
    if backend() == 'cryptography':
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        return ChaCha20Poly1305(subkey).encrypt(nonce12, bytes(plaintext), bytes(ad))
    return aead_seal(subkey, nonce12, plaintext, ad)


def xopen(key, nonce24, sealed, ad=b''):
    """XChaCha20-Poly1305 decrypt; tag verified before anything is returned."""
    subkey, nonce12 = _xsub(key, nonce24)
    if len(sealed) < 16:
        raise SealedError('sealed box too short')
    if backend() == 'cryptography':
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
        try:
            return ChaCha20Poly1305(subkey).decrypt(nonce12, bytes(sealed), bytes(ad))
        except InvalidTag:
            raise SealedError('forgery or corruption: AEAD tag mismatch') from None
    return aead_open(subkey, nonce12, sealed, ad)


# ---------- HKDF-SHA256 (RFC 5869) ----------

def hkdf_sha256(ikm, salt, info, length):
    """HKDF-Expand(SHA-256). Raises on empty output or outputs over 255 digests."""
    if not 0 < length <= 255 * 32:
        raise SealedError('bad hkdf length')
    prk = hmac.new(salt or b'\0' * 32, bytes(ikm), hashlib.sha256).digest()
    out, prev, i = bytearray(), b'', 1
    while len(out) < length:
        prev = hmac.new(prk, prev + bytes(info) + bytes([i]), hashlib.sha256).digest()
        out += prev
        i += 1
    return bytes(out[:length])


# ---------- v5 handshake ----------

def _check_psk(psk):
    if not isinstance(psk, (bytes, bytearray)) or len(psk) != 32:
        raise SealedError('the v5 PSK is 32 bytes')
    return bytes(psk)


def hello_a(psk, noncea=None):
    """Initiator hello: returns (ea, na, EA, msg1). msg1 = na(16) || EA(32)."""
    from src.fabric.cpace import encode_u, x25519
    _check_psk(psk)
    na = noncea if noncea is not None else secrets.token_bytes(16)
    if len(na) != 16:
        raise SealedError('handshake nonce is 16 bytes')
    ea = secrets.token_bytes(32)
    EA = x25519(ea, encode_u(9))
    return {'ea': ea, 'na': bytes(na), 'EA': EA}, bytes(na) + EA


def answer_b(psk, agent_id, msg1, nonceb=None, eb=None):
    """Responder step: checks msg1, returns (state, msg2 = nb || EB || mac_b)."""
    from src.fabric.cpace import encode_u, x25519
    _check_psk(psk)
    _check_agent(agent_id)
    if len(msg1) != 48:
        raise SealedError('hello must be 48 bytes')
    na, EA = msg1[:16], msg1[16:]
    nb = nonceb if nonceb is not None else secrets.token_bytes(16)
    if len(nb) != 16:
        raise SealedError('handshake nonce is 16 bytes')
    eb = eb if eb is not None else secrets.token_bytes(32)
    if len(eb) != 32:
        raise SealedError('ephemeral scalar is 32 bytes')
    EB = x25519(eb, encode_u(9))
    transcript = bytes(na) + bytes(nb) + bytes(EA) + EB
    conf = hkdf_sha256(bytes(psk), b'', INFO_CONFIRM, 32)
    mac_b = hmac.new(conf, b'B' + transcript, hashlib.sha256).digest()
    return {'eb': eb, 'nb': bytes(nb), 'EA': bytes(EA), 'EB': EB, 'transcript': transcript}, \
        bytes(nb) + EB + mac_b


def finish_a(psk, agent_id, state_a, msg2):
    """Initiator finish: checks msg2 (96 bytes) and mac_b, returns (session, msg3 = mac_a)."""
    from src.fabric.cpace import x25519
    _check_psk(psk)
    _check_agent(agent_id)
    if len(msg2) != 80:
        raise SealedError('answer must be 80 bytes')
    nb, EB, mac_b = msg2[:16], msg2[16:48], msg2[48:]
    transcript = state_a['na'] + bytes(nb) + state_a['EA'] + bytes(EB)
    conf = hkdf_sha256(bytes(psk), b'', INFO_CONFIRM, 32)
    if not hmac.compare_digest(hmac.new(conf, b'B' + transcript, hashlib.sha256).digest(), mac_b):
        raise SealedError('peer confirmation failed (wrong PSK or active attacker)')
    shared = x25519(state_a['ea'], EB)
    if hmac.compare_digest(shared, b'\0' * 32):
        raise SealedError('invalid peer share')
    mac_a = hmac.new(conf, b'A' + transcript, hashlib.sha256).digest()
    return _session('A', agent_id, transcript, shared), mac_a


def finish_b(psk, agent_id, state_b, msg3):
    """Responder finish: checks mac_a (32 bytes), returns the session."""
    from src.fabric.cpace import x25519
    _check_psk(psk)
    _check_agent(agent_id)
    if len(msg3) != 32:
        raise SealedError('confirmation must be 32 bytes')
    conf = hkdf_sha256(bytes(psk), b'', INFO_CONFIRM, 32)
    if not hmac.compare_digest(hmac.new(conf, b'A' + state_b['transcript'], hashlib.sha256).digest(),
                               bytes(msg3)):
        raise SealedError('peer confirmation failed (wrong PSK or active attacker)')
    shared = x25519(state_b['eb'], state_b['EA'])
    if hmac.compare_digest(shared, b'\0' * 32):
        raise SealedError('invalid peer share')
    return _session('B', agent_id, state_b['transcript'], shared)


def _check_agent(agent_id):
    if not isinstance(agent_id, (bytes, bytearray)) or not 0 < len(agent_id) <= 64:
        raise SealedError('agent_id is 1..64 bytes')


def _session(role, agent_id, transcript, shared):
    thash = hashlib.sha256(transcript).digest()
    return Session(role, bytes(agent_id), thash[:16],
                   hkdf_sha256(shared, thash, INFO_AB, 32), hkdf_sha256(shared, thash, INFO_BA, 32))


# ---------- v5 record layer ----------

class Session:
    """One sealed direction pair. Counter 0 is the first frame; the peer must send exactly the
    next counter, so replays, duplicates, reorders and drops all fail closed. Rekey = re-handshake."""

    def __init__(self, role, agent_id, session_id, key_ab, key_ba):
        if role not in ('A', 'B'):
            raise SealedError('role is A or B')
        self.role, self.agent_id, self.session_id = role, agent_id, session_id
        self._send_key, self._recv_key = (key_ab, key_ba) if role == 'A' else (key_ba, key_ab)
        self._send_prefix, self._recv_prefix = (DIR_A, DIR_B) if role == 'A' else (DIR_B, DIR_A)
        self._send_dir, self._recv_dir = (b'A', b'B') if role == 'A' else (b'B', b'A')
        self._send_n = self._recv_n = 0
        self.bytes_sent = self.bytes_received = 0

    def _nonce(self, prefix, counter):
        return prefix + b'\0' * 12 + struct.pack('>Q', counter)

    def _ad(self, direction, counter):
        return bytes([len(self.agent_id)]) + self.agent_id + self.session_id + direction + struct.pack('>Q', counter)

    def seal(self, plaintext):
        """Seal one frame: counter_be(8) || box. Raises past MAX_FRAMES (re-handshake instead)."""
        if not isinstance(plaintext, (bytes, bytearray)) or len(plaintext) > MAX_PLAINTEXT:
            raise SealedError('one frame carries at most %d bytes' % MAX_PLAINTEXT)
        if self._send_n >= MAX_FRAMES:
            raise SealedError('frame budget spent: re-handshake')
        box = xseal(self._send_key, self._nonce(self._send_prefix, self._send_n), bytes(plaintext),
                    self._ad(self._send_dir, self._send_n))
        frame = struct.pack('>Q', self._send_n) + box
        self._send_n += 1
        self.bytes_sent += len(frame)
        return frame

    def open(self, frame):
        """Open one frame. The counter must be exactly the next expected one."""
        if not isinstance(frame, (bytes, bytearray)) or len(frame) < 8 + 16 or len(frame) > 8 + MAX_PLAINTEXT + 16:
            raise SealedError('bad frame shape')
        (counter,) = struct.unpack('>Q', bytes(frame[:8]))
        if counter != self._recv_n:
            raise SealedError('unexpected frame counter %d (want %d): replay, loss or reorder' % (counter, self._recv_n))
        pt = xopen(self._recv_key, self._nonce(self._recv_prefix, counter), bytes(frame[8:]),
                   self._ad(self._recv_dir, counter))
        self._recv_n += 1
        self.bytes_received += len(frame)
        return pt

    def stats(self):
        return {'role': self.role, 'session_id': self.session_id.hex(), 'sent': self._send_n,
                'received': self._recv_n, 'bytes_sent': self.bytes_sent, 'bytes_received': self.bytes_received,
                'backend': backend()}
