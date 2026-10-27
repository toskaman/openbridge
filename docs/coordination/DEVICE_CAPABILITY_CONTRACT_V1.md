# Device Capability Contract v1.0.0

Owner of this contract: Device Runtime (adapters, policy, journal, Companion, HTTP backend). Consumer: Capability Forge / Meta planner / UX (GPT-6.1).
Source of truth: `src/runtime/contract.py`. Machine-readable surface: `docs/coordination/contract_v1.schema.json`, checked by `tests/runtime/test_contract.py`.

## Compatibility rules
- Fields may be **added**; never removed or renamed. Enumerations may only grow. A removal requires CONTRACT_VERSION 2.x and a coordinated change.
- Unknown fields must be ignored by consumers. Absent, refused or unknown capabilities are **unavailable** (never assumed).
- Forge never sends ADB/shell/network commands. It reads `/api/v2/*` and requests actions only by `primitive_id` with schema-validated parameters; every action goes through the deterministic gate, owner consent and the transaction journal.

## Types
| Type | Purpose |
|---|---|
| DeviceIdentity | graph key, category, label, kinds of strong identifiers (values never exposed), possible duplicates |
| EvidenceFact | one fact with sources, time, `verified` (read from the device) and `inferred` (computed by OpenBridge) |
| DeviceObservation | who saw the device, over which transport, when, RSSI, staleness |
| TransportSession | transport and grants (observe/read/control), authentication, whether OpenBridge opened it |
| RelayRoute | relay that can reach a target, its radio, permission, owner enablement, health |
| CapabilityPermission | permission name, granted, how it was obtained |
| CapabilityDescriptor | **six independent flags**: discovered, observed, readable, controllable, reversible, verified(status) + permissions, parameters, operations, source, freshness, limitations, reversibility class |
| ActionDescriptor | a registered primitive: input schema, permissions, preconditions, effects, verification, inverse, reversibility, errors, timeout, concurrency, consent |
| TransactionReceipt | result of an executed primitive with before/after and verification |
| RecoveryState | pending transactions and open session changes; non-empty means new conflicting actions are blocked |

ReversibilityClass: NONE, EXACT, SESSION_CLEANUP, MANUAL, IRREVERSIBLE (always blocked).
Verification status: REAL_HARDWARE_VERIFIED, INTEGRATION_VERIFIED, SIMULATED_VERIFIED, IMPLEMENTED_UNVERIFIED, BLOCKED, UNSUPPORTED.

## Endpoints for Forge (local only, same Host/Origin/CSRF rules as the rest of the API)
| Method | Route | Returns |
|---|---|---|
| GET | /api/v2/contract | schema() |
| GET | /api/v2/graph | identities, observations, transport sessions |
| GET | /api/v2/capabilities | CapabilityDescriptor[] |
| GET | /api/v2/facts?device=<key> | EvidenceFact[] (+ diagnostics findings) |
| GET | /api/v2/routes | RelayRoute[] |
| GET | /api/v2/primitives | ActionDescriptor[] |
| GET | /api/v2/recovery | RecoveryState |
| GET | /api/v2/events?since=<seq> | ordered change events (bounded ring buffer) |
| POST | /api/v2/execute | {primitive_id, device_key, params, consent} → TransactionReceipt (gate + journal enforced) |

## Example CapabilityDescriptor
```json
{"capability_id":"dev-3f2a:ble_relay","device_key":"dev-3f2a","name":"ble_relay","transport":"WIFI",
 "discovered":true,"observed":true,"readable":true,"controllable":true,"reversible":true,"verified":"REAL_HARDWARE_VERIFIED",
 "permissions":[{"name":"android.permission.BLUETOOTH_SCAN","granted":true,"obtained_by":"android_dialog"},
                {"name":"pairing","granted":true,"obtained_by":"pairing_code"}],
 "parameters":{"seconds":{"type":"integer","minimum":1,"maximum":15}},"operations":["relay_ble_scan","relay_revoke"],
 "source":"RELAY:relay-b29262ca4f6a","freshness_s":12,"limitations":["Companion must be open on the device"],
 "reversibility":"SESSION_CLEANUP"}
```

## Implementation status (feat/device-runtime-v2)

All `/api/v2/*` routes above are implemented in `src/runtime/api_v2.py` (hook: two lines in `src/server.py`).
Loopback Host check on every route; `POST /api/v2/execute` also requires Origin + CSRF, JSON ≤ 8 KiB, and only the
fields `primitive_id`, `device_key`, `params`, `consent`. HTTP 409 = receipt with state `BLOCKED`.

| Primitive | Reversibility | Consent | Concurrency | Runs through |
|---|---|---|---|---|
| read_facts | NONE | no | per device | ADB read allowlist (`diagnostics.ANDROID_READS`) / Freebox read-only paths |
| bounded_discovery | NONE | no | global | `fabric.discovery.run` (existing lock) |
| relay_ble_scan | SESSION_CLEANUP | yes | per device | signed relay protocol (`relay_action`) |
| relay_revoke | IRREVERSIBLE | yes | per device | `RelayManager.revoke` |
| android_optional_app_state | EXACT | yes | per device | agent plan → deterministic gate → transaction engine → read-back |
| undo_transaction | EXACT | yes | per device | transaction engine revert + exact read-back |
| session_cleanup | SESSION_CLEANUP | yes | global | session journal restore |

Executor guarantees (tests: `tests/runtime/test_primitives.py`, SIMULATED_VERIFIED):
strict schema (no extra fields), consent, ADB identity re-check before every device action (device replaced on the same
link → `IDENTITY_CHANGED`), one action per device, timeout → `UNKNOWN_TIMEOUT` (never success; the lock stays held until
the worker really ends), adapter exception mid-write → `FAILED` + listed in `/api/v2/recovery`, event ring buffer.

Receipt states: `VERIFIED`, `REVERTED`, `PARTIAL`, `FAILED`, `BLOCKED`, `UNKNOWN_TIMEOUT`. `verified` is true only after
an independent read-back.
