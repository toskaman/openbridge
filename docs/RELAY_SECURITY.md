# Relay security (protocol openbridge-relay/1)

- Enrollment: PC sends `pair_request` with a random nonce; the relay shows a 6-digit code on its own screen; key = PBKDF2-HMAC-SHA256(code, relay_nonce + pc_nonce, 200k). The first signed PC command proves the code; 5 failed attempts lock pairing until the app is reopened; the code expires after 2 minutes.
- Commands: closed set (discover_capabilities, start_discovery, stop_discovery, report_observations, get_status, get_permissions, revoke_access), HMAC-SHA256 over canonical JSON, nonce + 30 s expiry, replay cache.
- Bounds: BLE only, 1–15 s per scan, ≤200 observations, short names, numeric company IDs; replies are validated as untrusted data.
- Permissions: a relay is eligible only if it declares `ble_scan`, reports the Android scan permission as granted, and scans are not paused. Consent = the owner installs the app, pairs it with a code shown only on that device, and grants Android's own permission dialogs; scans are then enabled automatically (owner request to minimise steps) and can be paused in the app. A scan is refused unless the Companion is in the foreground, so nothing scans unseen.
- Routing: mains-powered relays preferred over battery relays, then fewer recent failures; three consecutive transport failures mark a relay offline.
- Transport: loopback (adb forward for USB phones) or private LAN IP only.
- Revocation: `revoke_access` or "Remove pairing" on the device; the PC forgets its key either way.
Tests: tests/fabric/test_relay.py (tamper, replay, expiry, unknown op, out-of-bounds scan, missing permission/owner consent, relay disappearing, malformed reply, busy relay, routing preference, revocation, transport scope, pairing).
