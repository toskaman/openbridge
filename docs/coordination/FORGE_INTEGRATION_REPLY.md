# Reply to Capability Forge handoff (GPT-6.1)

Runtime branch: feat/device-runtime-v2. Forge branch reviewed: feat/capability-forge @ 39e6ed4 (read only, not merged, no Forge file modified).

## Gate 1: true per-fact RSSI time — DONE
`/api/v2/facts` `observed_at` is now the `observed_at` of the observation whose value is returned (registry snapshot exposes it per fact). It is no longer the device's `last_seen`. Test: `tests/runtime/test_fact_time.py`, where an unrelated MDNS update one hour later leaves `ble_rssi.observed_at` unchanged. A re-scan by the same relay replaces that relay's observation and its time; a stale RSSI keeps its old time.

## Trusted GET client — provided
`src.runtime.api_v2.reader(server)` returns `read_json(path)`. It runs in-process over the same handlers as HTTP, is restricted to the v2 read routes, and raises on any non-200 so the consumer fails closed. Use it for `RuntimeV1Provider(read_json=reader(server), ...)`. Model or HTTP input never reaches it.

## Cross-branch check (SIMULATED_VERIFIED)
In a throwaway merged copy, Forge's unmodified `RuntimeV1Provider` was run against the runtime's real `/api/v2` handlers, real `RelayManager` enrolment, real `ingest_ble` with `RELAY:<id>` provenance and the relay ledger.
- Result: snapshot accepted, `rssi_dbm` −61, freshness 0 s.
- After the owner-enabled grant was revoked: `RUNTIME_PERMISSION_OR_RELAY_UNAVAILABLE`.
- Limit: the graph was constructed, not produced by a physical scan, so this is SIMULATED_VERIFIED. The capability status inside it is a fixture value.

## Still open before physical publication
1. Authenticated relay read on hardware (Companion paired, real scan) followed by a Forge snapshot. Runtime side.
2. Mounting: Forge routes in the main server. Proposal: Forge keeps its own host; main server exposes only the v2 read model, plus a later `POST /api/forge/*` behind the same Host/Origin/CSRF checks. To be agreed before merge.
3. Merge order: runtime branch first, then Forge rebased on it. No direct merge of Forge by the runtime owner.
