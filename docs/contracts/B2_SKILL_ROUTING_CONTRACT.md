# B2 — Typed skills, providers and route truth (contract proposal, rev 1)

Owner: Claude (route truth). Consumers: Codex (Skill Graph UI, harness), Meta Spark (M2 explanation only).
Status: PROPOSAL for review in issue #36. Nothing here is implemented yet. Base: main 038f463.
Accepts M1 rev 1.2 asks (§9) and Codex review notes. Answers the M2 grid R1 questions (§8).

## 1. Vocabulary
- **Skill**: an owner-meaningful outcome with a typed input/output, e.g. `ble_scan_room`, `tv_volume_set`, `tv_power`, `vacuum_dock`, `device_facts`. A skill never names a transport.
- **Provider**: one concrete way to perform a skill = `(device_key, transport, primitive_id, params_template)`. Providers are derived from the existing registry (devices, links/grants, capabilities), relay manager/ledger and the action catalog (`/api/v2/catalog`). No provider is invented from the catalog alone: a provider exists only if its device is in the current graph with a link.
- **Route**: a provider evaluated *now*: state, reason, freshness, lease. A multi-hop route lists every hop (e.g. PC → TV Companion relay → BLE advertisers).

## 2. Skill contract (typed, versioned)
```json
{ "skill_id": "tv_volume_set", "version": 1,
  "input":  {"type":"object","properties":{"value":{"type":"integer","minimum":0}},"required":["value"],"additionalProperties":false},
  "output": {"type":"object","properties":{"before":{"type":"integer"},"after":{"type":"integer"}}},
  "reversibility": "EXACT", "consent": "per_invocation",
  "verification": "independent read-back equals target",
  "providers": ["android.device_action.set:media_volume", "android.device_action.key:volume_up|volume_down"] }
```
Skill input is validated with the same strict schema subset as primitives (src/runtime/primitives.validate). A skill maps to exactly one primitive call per hop; macros stay `device_macro` and are listed as such.

## 3. Route record (what `GET /api/v2/skill_routes?skill=` returns; read-only, additive)
```json
{ "skill_id": "ble_scan_room", "evaluated_at": "2026-10-28T09:00:00Z", "policy": "AUTO",
  "routes": [
    { "route_id": "r-…", "state": "ACTIVE", "reason": null,
      "hops": [{"device_key":"dev-tv","transport":"LAN","primitive_id":"relay_ble_scan","grant":"control"}],
      "grants_checked": ["control@dev-tv","BLUETOOTH_SCAN@relay-tv"],
      "freshness": {"last_seen_s": 12, "lease_expires_in_s": 48, "source": "relay ledger"},
      "receipt_ref": "tx-…", "evidence": "REAL_HARDWARE" },
    { "route_id": "r-…", "state": "STANDBY", "reason": null, "hops": [...] },
    { "route_id": "r-…", "state": "UNAVAILABLE", "reason": "link_down", "hops": [...] } ] }
```
- `state ∈ {ACTIVE, READY, STANDBY, UNAVAILABLE}`. **ACTIVE** = the route the backend selected for the next invocation (at most one per skill). **READY** = eligible now but not selected. **STANDBY** = eligible but only usable after an explicit owner switch (never auto-failover). **UNAVAILABLE** carries exactly one `reason` from the M1 §7 enum: `link_down, grant_insufficient, consent_missing, capability_absent, lease_stale, dependency_unready, policy_blocked, backend_unknown`. Anything the backend cannot classify is `backend_unknown` → treated as unavailable.
- `evidence ∈ {REAL_HARDWARE, SIMULATED, NONE}` comes from the last receipt of that provider; SIMULATED is never rendered as hardware.
- Routes are ordered by the backend; the UI renders the order and never re-sorts.

## 4. Selection policies
- **PINNED**: the owner fixed one provider. Only that route can be ACTIVE; if it is unavailable the skill is UNAVAILABLE (no fallback).
- **PREFERRED**: owner order; the first eligible route becomes ACTIVE; others READY/STANDBY. A switch away from the preferred route is reported (`route_changed` event) and voids any armed consent.
- **AUTO**: deterministic score, no model: eligible → freshest lease → fewest hops → highest last-receipt success over the last 10 invocations → stable tie-break on route_id. Meta models may *explain* a decision (M2) but never choose or authorize.
Policy is stored per skill in the session journal (owner-visible, reversible).

## 5. Freshness and leases
- Every provider has `last_seen` from the source that proves it is reachable (ADB discovery/`read_facts`, relay ledger `last_success_at`, Tuya status, Windows agent hello). Clock basis: server monotonic for ages, UTC ISO for display.
- A **lease** = maximum age before a route must be re-proved: ADB 60 s, relay 120 s (`ROUTE_STALE_S` today: 300 s → tightened for routing), Tuya 60 s, Windows agent 60 s, router API 300 s. Expired lease → `lease_stale`; the only offered action is a read-only re-probe.
- Selection (ACTIVE) holds a 30 s **invocation lease**: consent armed inside it is bound to `(skill, route_id, params hash)`. If the route changes or the lease expires before dispatch, consent is void ("route changed, review again").

## 6. Dedup
- Identical invocations `(skill, route_id, params hash)` within 2 s are coalesced into one primitive call; both callers get the same receipt (no double key presses, no double robot commands).
- One physical device reached by two transports (e.g. TV via ADB-Wi-Fi and via relay) yields two providers but one `device_key`; per-device concurrency stays `single-per-device` as today.

## 7. Uncertain outcomes
- A hop that times out → receipt `UNKNOWN_TIMEOUT` (existing), route state becomes `UNAVAILABLE/backend_unknown` until a read-back resolves it; recovery() keeps it (B1 fix, PR #44). No automatic retry, no failover to another route for a non-idempotent skill. Idempotent read skills may retry once on another READY route, recorded as a separate receipt.

## 8. Answers to M2 grid R1
- Decision record: `{skill, policy, chosen_route, candidates[{route_id,state,reason}], grants_checked, freshness_at, decided_at, decision_ms}` emitted as an event and stored with the receipt.
- Decision vs outcome: decision scored on the record above; outcome scored on the receipt (`VERIFIED/FAILED/UNKNOWN_TIMEOUT`) separately.
- Abstention: emitting UNAVAILABLE with a reason is a valid decision and must be scored, not punished.
- Dedup counting: coalesced invocations count once.
- Consent: a route needing consent is READY (not ACTIVE-dispatchable) until armed; scored as correct if chosen and consent requested.

## 9. Implementation plan (after acceptance; Claude files only)
- `src/runtime/skills.py` (skill registry + provider derivation), `src/runtime/routing.py` (state, policies, leases, dedup), `/api/v2/skill_routes` + `/api/v2/skill_policy` (read / owner-set) in src/runtime/api_v2.py, events `route_changed`, `route_decision`.
- Tests: zero devices; link kill flips reason; lease expiry; PINNED no fallback; PREFERRED switch voids consent; AUTO determinism; dedup 2 s; timeout → backend_unknown, no failover; SIMULATED never REAL.
- Hardware receipts (B3): phone vs TV relay failover for `ble_scan_room` (manual switch), Watch → TV control only once a Watch-side command path exists (separate receipt).

## 10. Non-goals
No new device write capability, no grant elevation, no cloud routing, no model-chosen routes, no multi-PC routing until the Windows adapter supports several sessions (Codex assessment, MULTI_PC_INTEGRATION_ASSESSMENT.md).
