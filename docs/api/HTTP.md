# HTTP contract

- GET /api/session: per-process CSRF token. Not a user authentication token.
- GET /api/devices?source=demo|android|freebox: inventory with provenance.
- GET /api/model-status: inference mode, model and agent_enabled.
- POST /api/inspect: JSON object with string device_id; exact Origin, Host and X-CSRF-Token required. Maximum 8192 bytes. Returns provenance-tagged evidence (fixture, ADB or Freebox).
- POST /api/recommend, /api/demo-transaction: see SOURCES_AND_MODELS.md.
- POST /api/agent-plan {source:'android', device_id, goal:'review'|'declutter'}; /api/agent-execute and /api/agent-undo {source:'android', device_id, plan_id, consent}. Available only when started with --local-meta --agent; otherwise 409. Execute requires gate decision REVIEW_REQUIRED and consent=true.
- No other write endpoint exists. Unknown routes return 404; invalid host/origin/token returns 403; malformed input returns 400; excessive input returns 413.

Only 127.0.0.1 with the configured port is an accepted Host. Static assets are limited to /, /style.css and /app.js.

## Device Fabric routes
- GET /api/fabric · POST /api/fabric-discover {device_id:'fabric', providers?} (single-flight)
- GET /api/freebox-authorization · POST /api/freebox-authorize {device_id:'freebox-local'}
- POST /api/tv-adb-connect {device_id:<device key>} (one connection to that TV's private IPv4:5555)
- POST /api/companion-install {device_id:<adb handle>} · GET /api/companion-install
- POST /api/relay-pair-start / relay-pair-confirm {code} / relay-scan {relay_id, seconds}
- POST /api/fabric-advise {device_id:'fabric', goal}
- GET /api/session-changes · POST /api/session-restore {device_id:'session', restore:[ids]}
All POST routes require exact Host, Origin and the per-process CSRF token.

## Runtime v2 (contract v1) — loopback only
GET (Host check): `/api/v2/contract`, `/api/v2/graph`, `/api/v2/capabilities[?device=]`, `/api/v2/facts?device=[&source=RELAY:<id>]`, `/api/v2/routes`, `/api/v2/relays`, `/api/v2/primitives`, `/api/v2/recovery`, `/api/v2/events?since=`, `/api/v2/diagnosis`, `/api/v2/watches`.
POST (Host + Origin + CSRF, JSON ≤ 8 KiB): `/api/v2/execute` `{primitive_id, device_key, params, consent}` → TransactionReceipt. Primitives: `read_facts`, `bounded_discovery`, `relay_ble_scan`, `relay_revoke`, `android_optional_app_state`, `undo_transaction`, `session_cleanup`, `diagnostic_report`, `watch_start`, `watch_stop`. Unknown primitive or extra field → 409 BLOCKED; no free-form commands.

## F90 wiring (loopback only)
- GET `/api/v2/route_intel?target=` — relay-route enumeration for one target, best first (pure advisory read).
- POST `/api/v2/route_intel/dispatch` `{target, op, params?, capability?, relay_id?, down?}` — at-most-once send over relay routes; POST `/api/v2/route_intel/failover` `{record, target?, capability?, down?}` — re-dispatches a NOT_SENT record only (uncertain outcomes → 409, nothing transmitted); POST `/api/v2/route_intel/simulate_loss` `{target, lost_relay}` — pure what-if.
- POST `/api/v2/diagnose` `{question, bundle, device?}` — owner why-questions over an observed-facts bundle (deterministic mode; explanation quotes observed values only). Deliberately distinct from `/api/v2/diagnosis`: that route serves runtime per-device findings, this one answers questions from a supplied bundle and never touches devices.
- POST `/api/v2/transplant/run|revoke|report|get` — simulated-only capability transplant lifecycle. `run` needs `consent: true` (409 otherwise) plus companions/links/bundle/manifest in the body; real hardware is refused, never transplanted.
- POST `/api/v2/command/parse` accepts an optional `prior` resolved intent: follow-up turns ("pause it") resolve deterministically against it; misses fall through to the normal router unchanged.

## Smartwatch pairing
POST `/api/watch-pair` `{device_id:"watch", address:"<private IPv4>:<port>", code:"<6 digits>"}` → `{state: AUTHORIZED|PAIR_FAILED|PAIRED_NOT_ADVERTISED|CONNECT_FAILED|NEED_INPUT, guide}`. Without address/code it returns the tutorial. Connections are recorded in the session journal.
