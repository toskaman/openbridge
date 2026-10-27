# Device capability schema (schema_version 1)

Snapshot (`GET /api/fabric`): `devices[]` {key, category, label, identifier_kinds[], facts{name: {value, sources[], verified}}, capabilities[] {name, level: observe|read|write|restore, status: REAL_HARDWARE_VERIFIED|INTEGRATION_VERIFIED|SIMULATED_VERIFIED|IMPLEMENTED_UNVERIFIED|NOT_SUPPORTED|BLOCKED, via, evidence}, possibly_same_as[], handles{transport: opaque}, last_seen}; `links[]` {parent, child, transport: USB|WIFI|EMULATOR|LAN|INVENTORY|BLE, grants: subset of observe/read/control, source, observed_at}; `possible_duplicates[]`; `providers{}` statuses.
Contracts: src/fabric/contracts.py (DeviceObservation, Identifier, Capability, Link, ProposedAction). Relay commands: RELAY_SECURITY.md.

## Status vocabulary mapping (V4 planning pack ↔ repository)
| V4 pack | Repository |
|---|---|
| IMPLEMENTED_HARDWARE_TESTED / VERIFIED | REAL_HARDWARE_VERIFIED |
| IMPLEMENTED_SIMULATED / SIMULATED | SIMULATED_VERIFIED |
| UNVERIFIED | IMPLEMENTED_UNVERIFIED |
| BLOCKED_BY_VENDOR | BLOCKED (with reason) |
| DOCUMENTED_NOT_IMPLEMENTED / PROPOSED | NOT_SUPPORTED (with "not implemented") |
