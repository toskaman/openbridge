"""aead1: confidentiality for the relay channel with the Python standard library only.

Encrypt-then-MAC: a keystream from HMAC-SHA256 in counter mode (HMAC as a PRF) XORed with the plaintext, then an
HMAC-SHA256 tag over (aad, nonce, ciphertext). Two subkeys are derived from the pairing key, so the existing message
MAC key is never reused for encryption. The associated data names the relay and the direction, so a captured
PC->relay envelope cannot be reflected back as a relay->PC reply. The inner payload is still the signed, nonce-bound,
expiring relay message: replay and freshness checks are unchanged. Mirrors RelayServer.java (Aead class).
"""
import base64
import hashlib
import hmac
import json
import secrets

VERSION = 'aead1'
NONCE_BYTES, TAG_HEX = 16, 64
MAX_PLAINTEXT = 1 << 20


class AeadError(ValueError):
    pass


def subkeys(key):
    return (hmac.new(key, b'obr-aead1|enc', hashlib.sha256).digest(),
            hmac.new(key, b'obr-aead1|mac', hashlib.sha256).digest())


def _xor_stream(kenc, nonce, data):
    if not data:
        return b''
    ks = b''.join(hmac.new(kenc, nonce + i.to_bytes(4, 'big'), hashlib.sha256).digest()
                  for i in range((len(data) + 31) // 32))[:len(data)]
    return (int.from_bytes(data, 'big') ^ int.from_bytes(ks, 'big')).to_bytes(len(data), 'big')


def _tag(kmac, aad, nonce, ct):
    a = aad.encode('utf-8')
    return hmac.new(kmac, len(a).to_bytes(4, 'big') + a + nonce + ct, hashlib.sha256).hexdigest()


def seal(key, aad, plaintext, nonce=None):
    if not isinstance(plaintext, (bytes, bytearray)) or len(plaintext) > MAX_PLAINTEXT:
        raise AeadError('plaintext must be bytes <= 1 MiB')
    kenc, kmac = subkeys(key)
    nonce = nonce or secrets.token_bytes(NONCE_BYTES)
    ct = _xor_stream(kenc, nonce, bytes(plaintext))
    return {'enc': VERSION, 'n': nonce.hex(), 'c': base64.b64encode(ct).decode('ascii'), 't': _tag(kmac, aad, nonce, ct)}


def open_(key, aad, env):
    if not isinstance(env, dict) or env.get('enc') != VERSION:
        raise AeadError('not an aead1 envelope')
    try:
        nonce, ct, tag = bytes.fromhex(env['n']), base64.b64decode(env['c'], validate=True), str(env['t'])
    except (KeyError, ValueError, TypeError):
        raise AeadError('malformed envelope') from None
    if len(nonce) != NONCE_BYTES or len(tag) != TAG_HEX or len(ct) > MAX_PLAINTEXT:
        raise AeadError('malformed envelope')
    kenc, kmac = subkeys(key)
    if not hmac.compare_digest(_tag(kmac, aad, nonce, ct), tag):
        raise AeadError('authentication failed')            # checked before any decryption
    return _xor_stream(kenc, nonce, ct)


def aad_for(relay_id, direction):
    return '%s|%s|%s' % (VERSION, relay_id, direction)


def wrap(key, relay_id, message):
    env = seal(key, aad_for(relay_id, 'pc>relay'), json.dumps(message, separators=(',', ':')).encode('utf-8'))
    return dict(env, relay_id=relay_id)


def unwrap_reply(key, relay_id, envelope):
    try:
        return json.loads(open_(key, aad_for(relay_id, 'relay>pc'), envelope).decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as e:
        if isinstance(e, AeadError):
            raise
        raise AeadError('reply is not JSON') from None


def encrypting_send(raw_send, relay_id):
    """Wrap a relay transport: every signed message goes out sealed, every reply must come back sealed."""
    def send(relay, message):
        from src.fabric.relay import RelayError          # callers already handle RelayError/OSError
        reply = raw_send(relay, wrap(relay['key'], relay_id, message))
        if not isinstance(reply, dict) or reply.get('enc') != VERSION:
            raise RelayError('relay answered in plaintext after aead1 was negotiated (refused)')
        try:
            return unwrap_reply(relay['key'], relay_id, reply)
        except AeadError as e:
            raise RelayError('encrypted reply rejected: %s' % e) from None
    send.aead = VERSION
    return send


def open_voice(key, relay_id, clip_id, blob):
    """Voice download body: nonce(16) | tag(32) | ciphertext. aad binds relay and clip."""
    if len(blob) < NONCE_BYTES + 32:
        raise AeadError('voice body too short')
    env = {'enc': VERSION, 'n': blob[:NONCE_BYTES].hex(), 't': blob[NONCE_BYTES:NONCE_BYTES + 32].hex(),
           'c': base64.b64encode(blob[NONCE_BYTES + 32:]).decode('ascii')}
    return open_(key, '%s|%s|voice|%s' % (VERSION, relay_id, clip_id), env)
