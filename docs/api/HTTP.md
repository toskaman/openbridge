# HTTP contract

- GET /api/session: per-process CSRF token. Not a user authentication token.
- GET /api/devices: synthetic device inventory, sources and timestamps.
- POST /api/inspect: JSON object with string device_id; exact Origin, Host and X-CSRF-Token required. Maximum 8192 bytes. Returns deterministic fixture evidence.
- No write endpoint exists. Unknown routes return 404; invalid host/origin/token returns 403; malformed input returns 400; excessive input returns 413.

Only 127.0.0.1 with the configured port is an accepted Host. Static assets are limited to /, /style.css and /app.js.
