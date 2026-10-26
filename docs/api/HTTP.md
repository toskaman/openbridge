# HTTP contract

- GET /api/session: per-process CSRF token. Not a user authentication token.
- GET /api/devices?source=demo|android|freebox: inventory with provenance.
- GET /api/model-status: inference mode, model and agent_enabled.
- POST /api/inspect: JSON object with string device_id; exact Origin, Host and X-CSRF-Token required. Maximum 8192 bytes. Returns provenance-tagged evidence (fixture, ADB or Freebox).
- POST /api/recommend, /api/demo-transaction: see SOURCES_AND_MODELS.md.
- POST /api/agent-plan {source:'android', device_id, goal:'review'|'declutter'}; /api/agent-execute and /api/agent-undo {source:'android', device_id, plan_id, consent}. Available only when started with --local-meta --agent; otherwise 409. Execute requires gate decision REVIEW_REQUIRED and consent=true.
- No other write endpoint exists. Unknown routes return 404; invalid host/origin/token returns 403; malformed input returns 400; excessive input returns 413.

Only 127.0.0.1 with the configured port is an accepted Host. Static assets are limited to /, /style.css and /app.js.
