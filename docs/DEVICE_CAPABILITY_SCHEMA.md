# Device capability schema (schema_version 1)

Snapshot (`GET /api/fabric`): `devices[]` {key, category, label, identifier_kinds[], facts{name: {value, sources[], verified}}, capabilities[] {name, level: observe|read|write|restore, status: REAL_HARDWARE_VERIFIED|INTEGRATION_VERIFIED|SIMULATED_VERIFIED|IMPLEMENTED_UNVERIFIED|NOT_SUPPORTED|BLOCKED, via, evidence}, possibly_same_as[], handles{transport: opaque}, last_seen}; `links[]` {parent, child, transport: USB|WIFI|EMULATOR|LAN|INVENTORY|BLE, grants: subset of observe/read/control, source, observed_at}; `possible_duplicates[]`; `providers{}` statuses.
Contracts: src/fabric/contracts.py (DeviceObservation, Identifier, Capability, Link, ProposedAction). Relay commands: RELAY_SECURITY.md.
