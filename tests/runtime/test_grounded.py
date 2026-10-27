"""Challenge/confirm/handle kernel: nonce freshness, single use, HMAC handles, spoof rig (no hardware)."""
import hashlib
import unittest

from src.runtime.grounded import (CHALLENGE_TTL, HANDLE_TTL, GroundedError, ChallengeStore, bind, verify_handle)

SALT = b'salt-16-bytes!!'


class Loopback:
    def __init__(self): self.shown = {}
    def present(self, device_key, nonce): self.shown[device_key] = nonce
    def observe(self, device_key, timeout_s): return self.shown.get(device_key)


class WrongProof:
    def present(self, device_key, nonce): pass
    def observe(self, device_key, timeout_s): return '00' * 16


class Silent:
    def present(self, device_key, nonce): pass
    def observe(self, device_key, timeout_s): return None


class PhotoReplay:
    """Replays a nonce captured from an EARLIER challenge (photo of a previous code)."""
    def __init__(self, stale_nonce): self.stale = stale_nonce
    def present(self, device_key, nonce): pass
    def observe(self, device_key, timeout_s): return self.stale


class GroundedTests(unittest.TestCase):
    def test_bind_mints_verifiable_handle_with_evidence(self):
        h = bind(ChallengeStore(), SALT, 'dev:pump1', Loopback(), evidence=b'photo-bytes', now=2000.0)
        body = verify_handle(SALT, h, now=2000.0)
        self.assertEqual((body['device_key'], body['method']), ('dev:pump1', 'led_blink'))
        self.assertEqual(body['evidence_sha256'], hashlib.sha256(b'photo-bytes').hexdigest())
        with self.assertRaises(GroundedError):
            verify_handle(b'other-salt-16byte', h, now=2000.0)

    def test_wrong_proof_fails_and_locks_out_after_five(self):
        store = ChallengeStore()
        ch = store.issue('dev:pump1', now=1000.0)
        for _ in range(5):
            with self.assertRaises(GroundedError):
                store.confirm(SALT, ch['challenge_id'], '00' * 16, now=1001.0)
        with self.assertRaisesRegex(GroundedError, 'Too many'):
            store.confirm(SALT, ch['challenge_id'], ch['nonce'], now=1001.0)
        self.assertEqual(store.challenges, {})

    def test_expired_challenge_rejected_and_cleared(self):
        store = ChallengeStore()
        ch = store.issue('dev:pump1', now=1000.0)
        with self.assertRaises(GroundedError):
            store.confirm(SALT, ch['challenge_id'], ch['nonce'], now=1000.0 + CHALLENGE_TTL + 1)
        self.assertEqual(store.challenges, {})

    def test_confirmed_challenge_is_single_use(self):
        store = ChallengeStore()
        ch = store.issue('dev:pump1', now=1000.0)
        store.confirm(SALT, ch['challenge_id'], ch['nonce'], now=1001.0)
        with self.assertRaises(GroundedError):
            store.confirm(SALT, ch['challenge_id'], ch['nonce'], now=1001.0)

    def test_handle_expires_and_forgery_rejected(self):
        h = bind(ChallengeStore(), SALT, 'dev:pump1', Loopback(), now=2000.0)
        verify_handle(SALT, h, now=2000.0 + HANDLE_TTL)
        with self.assertRaises(GroundedError):
            verify_handle(SALT, h, now=2000.0 + HANDLE_TTL + 1)
        forged = dict(h, device_key='dev:pump2')
        with self.assertRaises(GroundedError):
            verify_handle(SALT, forged, now=2000.0)
        for badmac in ('x' * 64, 'é' * 64, 12345, None):
            with self.assertRaises(GroundedError):
                verify_handle(SALT, dict(h, mac=badmac), now=2000.0)
        for bad in ({}, {'mac': 1}, {'mac': 'x'}, 'nope', None):
            with self.assertRaises(GroundedError):
                verify_handle(SALT, bad, now=2000.0)

    def test_photo_replay_of_another_challenge_fails(self):
        store = ChallengeStore()
        old = store.issue('dev:pump1', now=1000.0)
        store.confirm(SALT, old['challenge_id'], old['nonce'], now=1001.0)
        with self.assertRaises(GroundedError):
            bind(store, SALT, 'dev:pump1', PhotoReplay(old['nonce']), now=1002.0)

    def test_silent_adapter_keeps_challenge_for_retry(self):
        store = ChallengeStore()
        with self.assertRaisesRegex(GroundedError, 'No proof'):
            bind(store, SALT, 'dev:pump1', Silent(), now=1000.0)
        cid = next(iter(store.challenges))
        h = store.confirm(SALT, cid, store.challenges[cid]['nonce'], now=1001.0)
        self.assertEqual(verify_handle(SALT, h, now=1001.0)['device_key'], 'dev:pump1')

    def test_issue_rejects_bad_keys_methods_and_salts(self):
        store = ChallengeStore()
        for bad in ('', None, 123, 'k' * 257):
            with self.assertRaises(GroundedError):
                store.issue(bad, now=1000.0)
        with self.assertRaises(GroundedError):
            store.issue('dev:pump1', method='telepathy', now=1000.0)
        ch = store.issue('dev:pump1', now=1000.0)
        with self.assertRaises(GroundedError):
            store.confirm('', ch['challenge_id'], ch['nonce'], now=1001.0)
