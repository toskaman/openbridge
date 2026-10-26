# Sources and model endpoints

GET /api/devices defaults to the synthetic fixture. Explicit source=android reads ADB inventory; source=freebox identifies the local Freebox through its documented public discovery endpoint. Neither source is scanned automatically.

POST /api/inspect accepts source (demo, android or freebox) and device_id. The existing Host, Origin, CSRF, input-size and JSON checks apply. Physical-source failure never returns a simulated success. Android handles are process-local opaque values; Freebox responses exclude its unique ID, private domain and custom name.

GET /api/model-status reports whether a supervised session was configured. Automatic cloud calls stay disabled. A configured session can still be refused by expiry or budget checks at request time.

POST /api/recommend accepts only source=demo and device_id=demo-android. The server supplies the fixture facts itself; callers cannot supply arbitrary prompts, identifiers or physical data. The Meta broker pins muse-spark-1.3 and validates returned identity, schema and evidence references. Missing or expired free-credit verification returns 409 without a model call. Physical sources return 400.

GET /api/model-proof reads the fixed public sanitized runtime receipt. evidence_kind=RECORDED_RUNTIME_CORE_CALL and live_request=false distinguish historical evidence from a new model response. Viewing this proof makes no provider request and consumes no credits.

The one-shot Windows verifier requires PowerShell 7 (`pwsh`). After directly confirming current promotional credits, an operator can invoke `pwsh -File scripts/verify/meta_runtime_smoke.ps1 -ObservedAt <UTC-ISO-TIMESTAMP> -FreeCredits <BALANCE> -ObservationId <UNIQUE-ID>`. It requires the participant's separately stored Windows-user-encrypted credential. Never commit that file or place the key on the command line. The timestamp must describe the real observation, not be refreshed to bypass expiry. No automatic retry is performed.

## Android connection events

GET /api/device-events?source=android is an explicitly selected local event stream. It emits JSON inventory events in text/event-stream format; payloads contain the adapter's redacted devices, never raw tracking output. Duplicate frames are suppressed. A safe unavailable event tells the browser to stop live tracking and retain manual listing as a fallback. Normal Host validation applies; no cross-origin access is granted.

One owned tracking subprocess is shared among subscribers and closed during final subscription/server cleanup. Heartbeats detect closed browser connections without polling devices. No endpoint parameter can choose a command, external host or model.
