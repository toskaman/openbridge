# Device identity and deduplication

Strong identifiers (merge allowed when equal): `android_serial` (ro.serialno), `freebox_uid` (api_domain), `mac_global` (universally administered MAC only), `mdns_host` (unique on a link by RFC 6762 conflict resolution), `cast_id`, `hap_id`, `ble_address` (static-random only), `companion_key`. All are HMAC-pseudonymized with a per-install 32-byte salt (`%LOCALAPPDATA%/OpenBridge/fabric-salt.bin`); raw values never leave the adapter.

Weak signals (never merge): IP address, announced name, randomized MAC, private BLE address. Two devices sharing a weak signal are reported as `possibly_same_as`; the UI shows "possible duplicate" and the detail explains that no action can target both.

Conflicts: if an observation carries strong identifiers belonging to two different existing devices, it becomes a third device with conflict hints rather than collapsing them.

Facts keep one value per source; the displayed value prefers verified direct reads, then confidence, then recency. Missing facts are listed as unavailable, never guessed.

Tests: tests/fabric/test_identity.py (USB + Wi-Fi same phone, two IPs, IP reuse, same-model twins, random MAC, incomplete identity, conflict, source retention, no raw identifiers, category ranking).
Real observation: the LG TV is seen by mDNS and by the Freebox inventory and is shown as a possible duplicate; the Xiaomi phone seen over USB and in the Freebox inventory is not merged (no shared strong identifier).
