# Universal Device Fabric — architecture

Five separated concerns, each in its own module:

| Concern | Where | Rule |
|---|---|---|
| Discovery | src/fabric/mdns.py, ble_local.py, relay.py, src/adapters/android.py, freebox_auth.py, src/fabric/discovery.py | Bounded in time, packets, records; approved scope (private networks, link-local TTL 1); read-only |
| Identity | src/fabric/contracts.py, registry.py | Merge only on a shared strong identifier; weak signals become `possibly_same_as` hints |
| Transport | Link objects (USB, WIFI, LAN, INVENTORY, BLE, EMULATOR) | A link grants only what it states: observe, read or control |
| Capabilities | Capability objects with STATUS vocabulary | Every capability has a level, a route (`via`) and evidence |
| Actions | src/core/gate.py, agent.py, transactions.py | Deterministic gate + owner consent + snapshot + independent verify + exact Undo |

Data flow: providers -> Registry.upsert/observe/link/capability -> snapshot (pseudonymized) -> /api/fabric -> UI. The Meta agent only receives allowlisted numeric facts and candidate lists; it never receives identifiers and cannot reach an adapter except through the gate.

Graph semantics: `pc -> device` for direct transports, `freebox -> host` (INVENTORY, observe) for devices the box sees, `relay device -> BLE device` (BLE, observe) for relayed scans. Seeing a device never implies reachability or control from the PC.

Runtime AI: Meta only (Llama 3.2 3B local, Muse Glimmer local, Muse Spark 1.3 cloud), enforced by src/ai/registry.py. Development assistance: Codex and Meta Muse Spark earlier (see CONTRIBUTIONS.md).
