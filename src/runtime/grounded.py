"""Grounded identity kernel: bind a device key to a short-lived handle through a physical challenge.

Vision proposes candidates; this kernel disposes. A challenge carries a fresh nonce bound to one
device key; only a proof matching that nonce mints a handle, and handles are HMAC-signed with the
install salt, single-scope and expiring. Replay, expiry, lockout and forgery fail closed.

The physical ends (showing the nonce on the device, reading it back from the world) are injected
adapters with two methods: present(device_key, nonce) and observe(device_key, timeout_s) -> str|None.
Liveness against photos/recordings is the adapter's contract; the kernel enforces nonce freshness,
single use and device binding at this seam. No physical adapter ships yet (needs a camera plus a
Companion display channel); tests use loopback/adversarial doubles only.
"""
import hashlib
import hmac
import json
import secrets
import threading
import time

CHALLENGE_TTL = 30   # mirrors the relay command window
HANDLE_TTL = 120     # mirrors the pairing code window
MAX_ATTEMPTS = 5     # mirrors the Companion pairing lockout
METHODS = ('led_blink', 'display_nonce', 'audio_chirp')


class GroundedError(RuntimeError):
    pass


def _canonical(fields):
    return json.dumps(fields, sort_keys=True, separators=(',', ':')).encode()


def sign_handle(salt, handle):
    body = {k: handle[k] for k in ('handle_id', 'device_key', 'method', 'issued_at', 'expires_at', 'evidence_sha256')}
    return hmac.new(salt, _canonical(body), hashlib.sha256).hexdigest()


def _require_salt(salt):
    if not isinstance(salt, bytes) or not salt:
        raise GroundedError('Install salt required')


class ChallengeStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.challenges = {}   # challenge_id -> {nonce, device_key, method, issued_at, attempts}

    def _prune_locked(self, now):
        for cid in [c for c, ch in self.challenges.items() if now - ch['issued_at'] > CHALLENGE_TTL]:
            del self.challenges[cid]

    def issue(self, device_key, method='led_blink', now=None):
        if not isinstance(device_key, str) or not device_key or len(device_key) > 256:
            raise GroundedError('Unknown device key')
        if method not in METHODS:
            raise GroundedError('Unknown challenge method')
        now = time.time() if now is None else now
        cid = 'ch-' + secrets.token_hex(8)
        with self._lock:
            self._prune_locked(now)
            self.challenges[cid] = {'nonce': secrets.token_hex(16), 'device_key': device_key, 'method': method,
                                    'issued_at': now, 'attempts': 0}
            return dict(challenge_id=cid, **self.challenges[cid])

    def confirm(self, salt, challenge_id, proof, evidence=None, now=None):
        _require_salt(salt)
        now = time.time() if now is None else now
        with self._lock:
            self._prune_locked(now)
            ch = self.challenges.get(challenge_id)
            if ch is None:
                raise GroundedError('Unknown or expired challenge')
            ch['attempts'] += 1
            if ch['attempts'] > MAX_ATTEMPTS:
                del self.challenges[challenge_id]
                raise GroundedError('Too many attempts; issue a new challenge')
            if not isinstance(proof, str) or len(proof) != 32 or any(c not in '0123456789abcdef' for c in proof):
                raise GroundedError('Proof does not match this challenge')
            if not hmac.compare_digest(proof, ch['nonce']):
                raise GroundedError('Proof does not match this challenge')
            del self.challenges[challenge_id]
        digest = hashlib.sha256(evidence).hexdigest() if isinstance(evidence, bytes) else None
        handle = {'handle_id': 'h-' + secrets.token_hex(8), 'device_key': ch['device_key'], 'method': ch['method'],
                  'issued_at': now, 'expires_at': now + HANDLE_TTL, 'evidence_sha256': digest}
        return {**handle, 'mac': sign_handle(salt, handle)}


def verify_handle(salt, handle, now=None):
    _require_salt(salt)
    now = time.time() if now is None else now
    try:
        mac = handle['mac']
        body = {k: handle[k] for k in ('handle_id', 'device_key', 'method', 'issued_at', 'expires_at', 'evidence_sha256')}
    except (TypeError, KeyError):
        raise GroundedError('Malformed handle') from None
    if not isinstance(body['issued_at'], (int, float)) or not isinstance(body['expires_at'], (int, float)):
        raise GroundedError('Malformed handle')
    if not isinstance(mac, str) or len(mac) != 64 or any(c not in '0123456789abcdef' for c in mac):
        raise GroundedError('Forged handle')
    if not hmac.compare_digest(sign_handle(salt, body), mac):
        raise GroundedError('Forged handle')
    if not body['issued_at'] <= now <= body['expires_at']:
        raise GroundedError('Expired handle')
    return body


def bind(store, salt, device_key, adapter, method='led_blink', evidence=None, now=None):
    """One-shot physical binding: present the nonce on the device, read it back, mint a handle."""
    ch = store.issue(device_key, method, now=now)
    adapter.present(device_key, ch['nonce'])
    proof = adapter.observe(device_key, CHALLENGE_TTL)
    if proof is None:
        raise GroundedError('No proof observed; retry within the challenge window')
    return store.confirm(salt, ch['challenge_id'], proof, evidence=evidence, now=now)
