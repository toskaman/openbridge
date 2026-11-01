# OpenBridge CLI reference

Executable: `openbridge` (`openbridge.cmd` on Windows) or `python -m src.cli`
from the repository root. The CLI drives the same in-process core as the GUI
(`src/server.py` + `/api/v2` handlers + `Executor`), so behavior is identical
by construction. No GUI dependency is loaded.

## Global flags

`--json` `--quiet` `--verbose` `--no-color` `--timeout SECONDS` `--model TIER`
`--provider local|meta-cloud` `--session ID` `--evidence-dir DIR` `--dry-run`
`--yes` `--consent HASH` `--providers a,b,c` `--server URL`

JSON output is a stable versioned envelope:

```json
{"cli_version": 1, "command": "devices list", "ok": true, "data": {}, "error": null}
```

Diagnostics go to stderr; `--json` stdout is always pure JSON.

## Exit codes

0 success · 1 internal · 2 invalid arguments · 3 missing dependency ·
4 authentication failure · 5 permission denied · 6 device unavailable ·
7 timeout · 8 inference failure · 9 verification failed · 10 uncertain
physical outcome · 11 cancelled.

## Consent model

Privileged operations (`approvals approve`, `workflows run`,
`capabilities publish`, `sessions undo`) require preview-bound consent:
the preview step prints a `--consent HASH` that must be passed back.
`--yes` NEVER bypasses mandatory consent and is refused with exit 5.

## Commands

- `version` `doctor` `init`
- `models list|status|test [--provider local|meta-cloud] [--deep] [--spend]|benchmark`
- `devices discover [--providers mdns,ssdp,android,freebox,ble]|list|inspect ID|pair ID|status`
- `ask "TEXT" [--prior intent.json]` — resolves via the skill router; writes return an approval request. `--prior` resolves follow-ups ("pause it") against the prior turn.
- `routes list --target T|dispatch --target T [--op OP] [--params JSON] [--capability C] [--relay ID]|simulate-loss --target T --lost-relay R` — relay-route enumeration and at-most-once dispatch.
- `diagnose --question Q --bundle facts.json [--device ID]` — owner why-questions over observed facts (deterministic; questions listed in `src/fabric/diagnostics.py`).
- `transplant run --request plan.json --consent H` — simulated-only capability transplant (request carries `consent: true`); needs preview-bound owner consent; lifecycle queries via the `/api/v2/transplant/*` routes.
- `migrate propose --text T [--source S] [--target D] [--match M]|apply --proposal P.json --consent H|rollback --receipt R.json --consent H` — move skill-bound controls between paired Companion interfaces; apply/rollback need preview-bound consent (`--yes` never bypasses).
- `capabilities list|generate --intent T --target C [--model TIER] [--retries N]|inspect|publish|revoke ID`
- `dashboards propose|install|revoke|export|import` — model-generated panels incl. sealed portable bundles (export → integrity-check → remap → fresh consent; no inherited grants).
- `workflows list|plan [TEXT|--file]|run ID [--file]|status ID`
- `approvals list|approve ID --consent H|deny ID`
- `sessions list|inspect ID|undo ID --consent ID`
- `evidence list|verify ID|export ID`
- `test smoke|integrations|hardware|models|jury`
- `judge demo` — scripted read-only demonstration ending in an evidence export.
- `serve [--port 18765] [--headless]` — foreground server, graceful SIGINT/SIGTERM.
- `agent start [--port 9876]` — Bridge agent listener, graceful shutdown.

## Client mode

`--server http://127.0.0.1:PORT` sends stateful calls to a running server
instead of a fresh in-process core. Use it when the GUI and the CLI must
share live state (pending approvals, running workflows).

## Paid cloud

Without `OPENBRIDGE_META_KEY` (OS secret store or environment, never a CLI
argument), cloud commands report `CLOUD_API_KEY_MISSING`. Spend is disabled
unless `OPENBRIDGE_CLI_BUDGET_USD` is set, and every paid call needs
`--spend --consent SPEND-APPROVED` plus budget headroom. Estimates are
pre-authorized; actuals reconcile afterwards.
