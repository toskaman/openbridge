"""CPace password-authenticated key exchange on X25519 with SHA-512 (pure Python, standard library only).

Why: the original relay pairing derived the key as PBKDF2(6-digit code, nonces). Anyone who recorded the pairing
exchange could try the 1 000 000 codes offline. With CPace the on-screen code still decides who may pair, but
nothing on the wire lets an attacker test codes offline: each wrong guess needs a fresh, live pairing attempt,
and the Companion locks pairing after 5 failures.

Construction (follows draft-irtf-cfrg-cpace, "CPace255" with SHA-512):
  generator  g  = Elligator2( SHA-512( lv(DSI) || lv(PRS) || lv(zero pad) || lv(CI) || lv(sid) )[:32] )
  shares     Ya = X25519(ya, g),  Yb = X25519(yb, g)        (ya, yb: fresh random 32-byte scalars)
  secret     K  = X25519(ya, Yb) = X25519(yb, Ya)            (all-zero K is refused: low-order point)
  ISK           = SHA-512( lv("CPace255_ISK") || lv(sid) || lv(K) || lv(Ya) || lv(ADa) || lv(Yb) || lv(ADb) )
PRS is the code, CI the relay id, sid the two pairing nonces. The relay key is ISK[:32].

The Java twin is companion/android/src/fr/openbridge/companion/Cpace.java; tests/fabric/test_cpace.py checks
X25519 against RFC 7748 and both implementations against shared vectors. The draft's own test vectors run in
tests/fabric/test_cpace_vectors.py whenever tests/fabric/cpace_draft_vectors.json is present next to it
(git-ignored; see that file's docstring for the format); until then, interoperability between our two sides is
what the pairing needs, and is tested.
"""
import hashlib
import hmac
import secrets

P = 2 ** 255 - 19
A = 486662
A24 = 121665
DSI = b'CPace255'
DSI_ISK = b'CPace255_ISK'
S_IN_BYTES = 128   # SHA-512 block size


class CPaceError(ValueError):
    pass


def leb128(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def lv(data):
    return leb128(len(data)) + data


def decode_u(b):
    if len(b) != 32:
        raise CPaceError('a curve coordinate is 32 bytes')
    return int.from_bytes(b, 'little') & ((1 << 255) - 1)


def encode_u(u):
    return (u % P).to_bytes(32, 'little')


def _clamp(k):
    if len(k) != 32:
        raise CPaceError('a scalar is 32 bytes')
    b = bytearray(k)
    b[0] &= 248
    b[31] &= 127
    b[31] |= 64
    return int.from_bytes(bytes(b), 'little')


def x25519(k, u):
    """RFC 7748 X25519 (Montgomery ladder)."""
    k, x1 = _clamp(k), decode_u(u) % P
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = kt
        a, b = (x2 + z2) % P, (x2 - z2) % P
        aa, bb = a * a % P, b * b % P
        e = (aa - bb) % P
        c, d = (x3 + z3) % P, (x3 - z3) % P
        da, cb = d * a % P, c * b % P
        x3 = (da + cb) ** 2 % P
        z3 = x1 * (da - cb) ** 2 % P
        x2 = aa * bb % P
        z2 = e * (aa + A24 * e) % P
    if swap:
        x2, x3, z2, z3 = x3, x2, z3, z2
    return encode_u(x2 * pow(z2, P - 2, P))


def _is_square(x):
    return x % P == 0 or pow(x, (P - 1) // 2, P) == 1


def elligator2(r):
    """Map a field element to the u-coordinate of a point of Curve25519 (Z = 2)."""
    r %= P
    t = (1 + 2 * r * r) % P
    x1 = (-A) % P if t == 0 else (-A * pow(t, P - 2, P)) % P
    gx1 = (x1 * x1 * x1 + A * x1 * x1 + x1) % P
    return x1 if _is_square(gx1) else (-x1 - A) % P


def generator(prs, ci, sid):
    zpad = max(0, S_IN_BYTES - 1 - len(lv(prs)) - len(lv(DSI)))
    h = hashlib.sha512(lv(DSI) + lv(prs) + lv(b'\0' * zpad) + lv(ci) + lv(sid)).digest()
    return encode_u(elligator2(decode_u(h[:32])))


def share(g, scalar=None):
    """(secret scalar, public share) for generator g."""
    y = scalar if scalar is not None else secrets.token_bytes(32)
    return y, x25519(y, g)


def isk(y, y_other, sid, ya, yb, ad_a=b'', ad_b=b''):
    """Intermediate session key. ya/yb are the initiator's / responder's shares, in that order on both sides."""
    k = x25519(y, y_other)
    if hmac.compare_digest(k, b'\0' * 32):
        raise CPaceError('invalid peer share')
    return hashlib.sha512(lv(DSI_ISK) + lv(sid) + lv(k) + lv(ya) + lv(ad_a) + lv(yb) + lv(ad_b)).digest()
