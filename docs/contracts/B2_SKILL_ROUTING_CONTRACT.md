# B2 — Typed skills, providers and route truth (contract, rev 2)

Owner: Claude (route truth). Consumers: Codex (Skill Graph UI, harness), Meta Spark (M2 explanation only).
Status: PROPOSAL rev 2 for review in issue #36. Nothing is wired into the server yet. Base: main 038f463 (merges cleanly with 0a7a8a6).

**Normative artifacts (rev 2):**
- `src/runtime/b2_skill_routes.schema.json` is the JSON Schema of the response and the invoke request.
- `src/runtime/route_contract.py` holds the dependency-free validator, the cross-field rules (`semantic_errors`), the stable IDs, the binding hash and the invocation ledger.
- `tests/contracts/b2/*.json` holds valid fixtures plus `invalid/` fixtures with a manifest of the expected failure. They are **shared**: backend tests and UI tests load the same files.
- `tests/contracts/test_b2_contract.py` runs the contract tests.

The prose below explains the artifacts. Where they disagree, the schema and the rules win.

## 0. Rev 2 changes (review → resolution)

| Review point | Resolution |
|---|---|
| Codex 1: dedup by identical params within 2 s loses deliberate repeats | §6: dedup only by an explicit `invocation_id` scoped to the actor. A retry reuses the ID (one dispatch, same receipt). A new intent gets a new ID, even with identical params. A reused ID with a different binding is rejected (`409 INVOCATION_ID_REUSED`). `InvocationLedger` and tests cover both cases. |
| Codex 2: versioning, revision, stable IDs, absolute time; lease binding | §3: `schema_version`, `graph_revision {epoch, seq}`, `server_time`, stable `route_id` / `provider_id` / `operation_id`, absolute `observed_at` / `expires_at`. §5: the lease and consent bind actor, physical target identity, exact params, graph revision, lease ID and `authority_rev`; a `route_id` alone never survives a change of authority. |
| Codex 3: `tv_volume_set` EXACT listed raw key presses | §2: an EXACT provider needs `exactness` (measured readable range, before snapshot, independent read-back, exact restore). Key presses are a separate IRREVERSIBLE skill, `tv_volume_step`. A rule forbids an EXACT route without `exactness`. |
| Codex 4: ACTIVE semantics inconsistent; STANDBY vs AUTO retry | §3–4: `route.state` is eligibility only (READY / STANDBY / UNAVAILABLE). Selection is the separate `selected_route_id`; the invocation (idle / armed / executing) and per-route `consent` are separate fields. M1's "ACTIVE" badge is *derived*: the route of an armed or executing invocation. Failover requires `policy.failover = idempotent_read_retry`, which is allowed only for idempotent read-only skills; STANDBY is manual-only. |
| Codex 5: ellipses; no valid JSON / schema | Schema, 5 valid fixtures and 15 invalid fixtures (unknown enums, bounds, missing fields, cross-field violations) with shared tests. |
| Meta Spark 1: consent field | `route.consent ∈ {none, required, armed}` |
| Meta Spark 2: name the missing grant | `reason_detail {missing_grant, hop_index, blocking_device_key}`, required for `grant_insufficient` |
| Meta Spark 3: countdown | `invocation.lease_expires_at` (absolute) + `lease_expires_in_s` (0–30) |
| Meta Spark 4: delivery of flips | §5.4: poll contract with `delivery.poll_after_s`, plus `route_changed` / `route_decision` events on `/api/v2/events`. The server re-checks the binding at dispatch, so UI latency can never execute a stale consent. |

## 1. Vocabulary
- **Skill**: an owner-meaningful outcome with typed input and output, e.g. `ble_scan_room`, `tv_volume_set`, `tv_volume_step`, `vacuum_dock`, `device_facts`.
  - It declares `reversibility`, `idempotent` and `consent`, and never names a transport.
- **Provider** (`provider_id`): one concrete way to perform a skill on one device, `(device_key, transport, primitive_id, operation)`.
  - Providers derive only from the current registry graph (devices, links, grants), the relay manager/ledger and the action catalog. The catalog alone never creates one.
- **Operation** (`operation_id`, e.g. `op:device_action:set_media_volume`): the exact primitive action. Two operations are never interchangeable unless the skill says so: BLE scan ≠ GATT ≠ audio ≠ file transfer.
- **Route** (`route_id`): a provider path evaluated now, with every hop (≤ 4). Example: PC → TV (WIFI) → TV Companion relay (RELAY).

## 2. Skills (typed, versioned)
| skill | reversibility | idempotent | consent | providers |
|---|---|---|---|---|
| `ble_scan_room` | SESSION_CLEANUP | yes | per_invocation | `relay_ble_scan` through a paired relay |
| `tv_volume_set` | **EXACT** | no | per_invocation | `device_action:set_media_volume` **only with `exactness`** |
| `tv_volume_step` | IRREVERSIBLE | no | per_invocation | `device_action:key_volume_up/down` (one press per invocation ID) |
| `device_facts` | NONE | yes | none | `read_facts` |

Skill input is validated with the strict primitive schema subset. A skill maps to exactly one primitive call per hop; sequences stay `device_macro`.

## 3. Route truth response (`GET /api/v2/skill_routes?skill=`, read-only)
The full shape is in the schema; example in `tests/contracts/b2/skill_routes_ble_relays.json`. The top level carries:
- `schema_version` (`b2.2`), `server_time`, and `graph_revision {epoch, seq}`. The epoch changes on server start; `seq` increases on every registry, grant, relay or route change. The UI drops any response older than the one it holds.
- `skill`, `policy {mode, failover, pinned_route_id, set_by}`, `selected_route_id`, `selection {rule, decided_at}`, `invocation {status, invocation_id, route_id, lease_id, lease_expires_at, lease_expires_in_s}`, `routes[]`, and `delivery`.

Each route has:
- **Identity**: `route_id`, `provider_id`, `operation_id`.
- **Eligibility**: `state` ∈ READY / STANDBY / UNAVAILABLE. UNAVAILABLE ⇔ exactly one `reason` from the M1 §7 enum; anything unclassifiable is `backend_unknown`.
- **Detail and consent**: `reason_detail` (for `grant_insufficient` / `dependency_unready`) and `consent` (none / required / armed).
- **Path and authority**: `hops[]` (each with `grant` and `required_grant`), and `authority {grants_checked, authority_rev}`.
- **Freshness**: `freshness {observed_at, expires_at, lease_s, source}`, in absolute UTC from the server clock. Ages are computed against `server_time`, never the browser clock.
- **Exactness and evidence**: `exactness` (EXACT skills only), `last_receipt`, and `evidence`. `evidence` comes from the last receipt; SIMULATED never renders as hardware.
- **Order**: the backend orders routes and the UI never re-sorts.

## 4. Selection and invocation
- **Selection**:
  - `selected_route_id` is the READY route the next invocation would use, or `null` with `rule = none_eligible`.
  - A STANDBY route is never selected: it becomes READY only through an explicit owner switch, which is a policy change.
- **Policies**: `PINNED` (only the pinned route; no fallback), `PREFERRED` (owner order), and `AUTO`. AUTO is a deterministic score with no model: eligible → freshest lease → fewest hops → last-10 success rate → `route_id` tie-break. Meta models may explain a decision (M2), never choose or authorize one.
- **Invocation**:
  - `idle` → `armed` (consent given, lease running) → `executing` → back to idle with a receipt.
  - The armed or executing invocation is always on the selected route; its route has `consent = armed` (at most one).
  - The UI's ACTIVE badge is exactly that route.
- **Failover**:
  - `policy.failover = none` by default.
  - `idempotent_read_retry` is allowed only for skills with `idempotent = true` and `reversibility = NONE`: one retry on the next READY route, recorded as a separate receipt with its own invocation ID linked to the first.
  - Changing or irreversible skills never fail over, and an UNKNOWN_TIMEOUT is never replayed.

## 5. Freshness, leases and binding
1. **Route leases** (maximum age before re-proof): ADB 60 s, relay 120 s, Tuya 60 s, Windows agent 60 s, router API 300 s. An expired lease gives `lease_stale`, and the only offered action is a read-only re-probe.
2. **Invocation lease**: 30 s, identified by `lease_id`, with consent armed inside it. Binding = `sha256(actor, skill_id, route_id, lease_id, graph_revision, target identity, authority_rev, canonical params)` (`route_contract.binding_hash`). The target identity is the strongest identifier anchor of the physical device (e.g. `android_serial:…`), not a display label.
3. **At dispatch** the server recomputes the binding. Any difference voids the consent (`409 CONSENT_VOID: route changed, review again`) and nothing is dispatched. The differences that count:
   - a newer graph revision touching a hop
   - an `authority_rev` change (grant added, removed or revoked)
   - a different target identity
   - an expired lease
   - edited params
4. **Delivery**:
   - `delivery.mode = poll`. The UI polls `skill_routes` every `poll_after_s`: 2 s while an invocation is armed, otherwise 8 s.
   - The UI also reads `/api/v2/events?since=` for `route_changed {skill_id, from, to, graph_revision}` and `route_decision` (M2 record).
   - Push transport is a non-goal for B2. Correctness never depends on delivery latency, because point 3 is enforced server-side.

## 6. Invocation request and dedup (`POST /api/v2/skill_invoke`, CSRF)
- **Request**: `{invocation_id, skill_id, route_id, lease_id, graph_revision, params, consent}`.
  - `invocation_id = "inv-" + 32 hex`, generated by the client once per owner intent.
  - Every press of a button is a new intent; a network retry of the same press reuses the ID.
- **Dedup**: the ledger is keyed by `(actor, invocation_id)` and kept 10 min (`InvocationLedger`).
  - Same ID + same binding: the original result is returned with **no second dispatch**, including while the first is still running and when the first raised (failures are outcomes).
  - Same ID + different binding: `409 INVOCATION_ID_REUSED`, nothing dispatched.
  - New ID: dispatched, even with identical params (two deliberate volume-up presses = two presses).
  - Full ledger: refused, never evicting a live ID.
- **Concurrency**: per-device concurrency stays `single-per-device` as today. One physical device reached by two transports gives two providers but one `device_key`.

## 7. Uncertain outcomes
A hop timeout produces receipt `UNKNOWN_TIMEOUT`. The route becomes `UNAVAILABLE / backend_unknown` until a read-back resolves it, and recovery keeps it (B1, PR #44: bounded by admission, owner acknowledge). There is no automatic retry and no failover for non-idempotent skills.

## 8. M2 grid R1 answers
- **Decision record**: `{skill_id, graph_revision, policy, selected_route_id, candidates[{route_id, state, reason}], grants_checked, freshness_at, decided_at, decision_ms}`, emitted as `route_decision` and stored with the receipt.
- **Scoring**: the decision is scored on the record and the outcome on the receipt, separately. `none_eligible` with reasons is a valid abstention and is scored as such.
- **Counting**: one invocation ID = one decision, however many retries.
- **Consent**: a route with `consent = required` is selectable; arming consent is part of the correct path, not a failure.

## 9. Implementation plan (after acceptance; Claude files only)
- `src/runtime/skills.py` (skill table + provider derivation), `src/runtime/routing.py` (eligibility, policies, leases, selection), and `/api/v2/skill_routes`, `/api/v2/skill_policy`, `/api/v2/skill_invoke` in api_v2. The server output is validated against the schema in tests.
- Tests:
  - zero devices
  - link kill flips the reason
  - lease expiry
  - PINNED with no fallback
  - a PREFERRED switch voids consent
  - AUTO determinism
  - ID dedup
  - binding void on a grant change
  - timeout → `backend_unknown`, no failover
  - SIMULATED never REAL
- Hardware receipts (B3): phone vs TV relay for `ble_scan_room` (manual switch). Watch → TV comes only once a Watch-side command path exists.

## 10. Non-goals
- No new device write capability or grant elevation.
- No cloud routing and no model-chosen routes.
- No push transport.
- No multi-PC routing in this contract version (multi-PC v4 is implemented and reviewed separately).

## 11. Runtime implementation (rev 2, Claude, 28 Oct 2026)
Implemented in `src/runtime/routing.py`, wired in `src/runtime/api_v2.py`. Every response is checked against the schema and rules in `tests/runtime/test_routing.py`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v2/skills` | GET | skill table: id, plain text, targeted, reversibility, consent, input schema, current policy |
| `/api/v2/skill_routes?skill=<id>[&target=<device key>]` | GET | route truth (§3); targeted skills require `target` |
| `/api/v2/skill_policy` | POST (CSRF) | `{skill_id, mode, failover?, route_id? (PINNED), preferred? []}`; voids armed consent |
| `/api/v2/skill_arm` | POST (CSRF) | `{skill_id, target?, route_id, params, consent: true}` → `{invocation_id, lease_id, route_id, graph_revision, lease_expires_at, lease_expires_in_s}`; only the selected READY route; 30 s lease |
| `/api/v2/skill_invoke` | POST (CSRF) | §6 request (+ `target` for targeted skills); dispatched once through the Executor with consent |

`skill_arm` is the one addition to the rev 2 text: it is where the server issues the invocation ID and lease that §4 and §5 describe.

**Skills live today:**
- `ble_scan_room`: paired relays; ledger freshness; permission and owner gates.
- `device_facts`: link and read grant.
- `tv_volume_set`: ADB control. It is EXACT only after a read-only `device_capabilities` probe measured the media-volume range; otherwise it is `dependency_unready`, naming the device.
- `tv_volume_step`: ADB control.

**Events on `/api/v2/events`:** `route_decision` (every `skill_routes` read), `route_changed`, `skill_policy`.

**Limits:**
- Policies and invocations are in memory; a server restart returns to AUTO with no armed invocation.
- The only actor is the local owner UI; Companion/Watch actors are B3.
- Evidence is REAL_HARDWARE for receipts from live devices and SIMULATED for synthetic (`sim-`) devices.
- Multi-PC scope is outside this contract version (it is implemented separately in BridgeWindows v4).
