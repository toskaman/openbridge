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
- `models list|status|test [--provider local|custom] [--deep]|benchmark`
- `ai list|add --name N --base-url URL --model M [--kind openai|ollama] [--api-key-env VAR|--store-key] [--timeout-s S] [--max-tokens T] [--json-mode] [--no-activate]|use NAME|test NAME [--consent ALLOW-REMOTE]|remove NAME` — connect your own AI/API by hand ([guide](AI_PROVIDERS.md)).
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
- `demo` — scripted read-only demonstration ending in an evidence export, no hardware needed (`judge demo` is the older name and still works).
- `serve [--port 18765] [--headless]` — foreground server, graceful SIGINT/SIGTERM.
- `agent start [--port 9876]` — Bridge agent listener, graceful shutdown.

## Client mode

`--server http://127.0.0.1:PORT` sends stateful calls to a running server
instead of a fresh in-process core. Use it when the GUI and the CLI must
share live state (pending approvals, running workflows).

## Connected AI (no paid model built in)

OpenBridge ships no paid model; the former hosted tier, `--spend` and the
credit/budget flags are gone. Model tiers are `AUTO`, `LOCAL-FAST`,
`LOCAL-QUALITY` and `CUSTOM` (the AI you connected with `ai add`; the old
`CLOUD-*` names map to `CUSTOM`). Keys go to the OS secret store
(`--store-key`, hidden prompt) or an environment variable (`--api-key-env`),
never a CLI argument. A provider that is not on this PC needs
`--consent ALLOW-REMOTE` (alias `ALLOW-CLOUD`). See [AI_PROVIDERS.md](AI_PROVIDERS.md).

## Home Assistant bridge

- `ha connect --url URL [--store-token | --token-env VAR]` — link a Home Assistant instance; the token goes to the OS vault or an environment variable, never to argv.
- `ha status` — check the link and count devices per domain.
- `ha devices` — list devices, their allowed actions and policy refusals.
- `ha do ENTITY ACTION [--value N] --consent ALLOW` — one action through the same gate as the app (consent, read-back, receipt).
- `ha disconnect` — forget the URL and the stored token.

See [Home Assistant bridge](HOME_ASSISTANT.md).

## Partner integration kit

- `partner new NAME [--category C] [--title T] [--from-openapi FILE] [--dry-run]` — scaffold an adapter, an emulator, a graph entry, passing tests and a checklist; never overwrites. With `--from-openapi`, settings, commands, refusals and tests come from the device's OpenAPI 3 description (same rules as the [Integrate page](https://toskaman.github.io/openbridge/integrate.html)).

See [Integrate your device](INTEGRATE_YOUR_DEVICE.md).

## Learning, new features and links

| Command | What it does |
|---|---|
| `openbridge ha say "TEXT" [--consent ALLOW] [--lang auto|en|fr] [--intent-model M] [--endpoint URL]` | Plain-language request (French, US or UK English) understood by OpenBridge's own model, checked by the gate, run on Home Assistant and read back; without `--consent ALLOW` it only shows the plan. Links are created unapproved |
| `openbridge ha soak --cycles N --consent ALLOW [--include-covers] [--seed S]` | Long real test of every allowed action; each change is undone |
| `openbridge learn report [--summary]` | What OpenBridge learned about each device |
| `openbridge learn reset --consent ALLOW` | Forget everything learned |
| `openbridge create suggest [--limit N]` | Cross-device features built from proven capabilities |
| `openbridge links add --when E --state S --then E --action A [--value V] [--title T] [--cooldown S]` | Propose a link (inactive until approved) |
| `openbridge links approve ID --consent ALLOW` | Let a link act |
| `openbridge links list` / `remove ID` | Manage links |
| `openbridge links watch [--seconds N] [--interval S]` | Run the link engine on live states |
| `openbridge skills list` / `show ID` / `remove ID` | Saved skills (features that run with no AI model) |
| `openbridge skills export [ID ...] --out FILE` / `import FILE` | Share skills as a signed file; imports arrive unapproved |
| `openbridge skills approve ID --consent ALLOW` | Let a skill act; any later change to it voids the approval |
| `openbridge skills run ID` | Run an approved skill now, through the normal gate and read-back |
| `openbridge skills packs [--lang en\|fr]` / `pack-show ID` | Ready-made cross-brand skill packs |
| `openbridge skills install-pack ID [--map ROLE=ENTITY ...] [--lang en\|fr]` | Install a pack on your devices; its skills arrive unapproved |
| `openbridge skills pack-check FILE` | Check a partner pack and print its SHA-256 for review |
| `openbridge quality status` / `enable --consent ALLOW` / `disable [--forget]` | Quality reports by device model and firmware: off by default, never sent |
| `openbridge quality report [--month YYYY-MM] [--markdown FILE]` | This month's success rates, p95 latencies and firmware regressions |
| `openbridge quality export [--month YYYY-MM] --out FILE` | A file you may choose to share (counts only, nothing identifying) |
| `openbridge quality merge FILE... [--markdown FILE]` | For a device maker: merge the files owners sent into a monthly report |

See [Devices that learn and talk to each other](DEVICE_LEARNING.md), [Skills](SKILLS.md) and [Skill packs](SKILL_PACKS.md).

## Glasses

| Command | What it does |
|---|---|
| `openbridge glasses run --link studio\|ble\|none [--glasses "ENGO 3"] [--seconds N] [--offline] [--takeover]` | Run the glasses hub: menus, messages from the phone, TV, vacuum, voice |
| `openbridge glasses run ... --sport run\|ride\|hike [--gpx FILE] [--workout 6x400@4:15] [--max-hr N] [--simulate M/S]` | Start a sport session: dashboard, navigation, intervals; `--simulate` moves a fake position along the GPX |
| `openbridge glasses grant --allow tv_remote,tv_apps,tv_power,vacuum --consent ALLOW` / `revoke` | What the glasses may run on a gesture or a voice command |
| `openbridge glasses set [--rotate on\|off] [--privacy full\|sender\|off] [--apps ...] [--lang auto\|fr\|en] [--hud-lang follow\|fr\|en] [--units metric\|imperial]` | Display orientation, message privacy, allowed apps, language, glasses language, units |
| `openbridge glasses preview [--out DIR] [--glasses MODEL]` | Every screen as PNG and a contact sheet |
| `openbridge glasses press EVENT` / `notify --app A --from F --text T` / `say TEXT` / `status` | Drive a running hub |

See [ENGO glasses](GLASSES.md).
