# aead1 relay encryption on the owned Android TV — 29 Oct 2026 15:16 CET

Companion 0.9.0 and server built from `claude/relay-aead` (isolated :18780, stopped after). Presses adb-injected
(owner-authorized automation).

| check | result |
|---|---|
| Java `Aead` vs Python `src/fabric/aead.py` | shared vector `tests/fabric/fixtures/aead1_vector.json`: command **MATCH**, voice **MATCH** (`dev/aead_vector_check`, javac/java on the PC) |
| pairing → negotiated transport | `transport[relay-dabd2a796665] = aead1` |
| plaintext signed-format command to the Companion after negotiation | **403 `encryption required`** |
| full UI v2 flow over aead1 (install, ACK 7, confirmed press → muted true/0, second press → false/20, app restart → layout restored, revoke → BLOCKED, cleanup) | PASS, same outcomes as the plaintext run |

Not shown on hardware: the encrypted voice clip path (unit-tested with the shared vector and the Python fetch path).
Known limitation (unchanged): the pairing key is derived from a 6-digit on-screen code with PBKDF2; an attacker who
records the pairing exchange can brute-force it offline. A PAKE-style pairing is the follow-up.
