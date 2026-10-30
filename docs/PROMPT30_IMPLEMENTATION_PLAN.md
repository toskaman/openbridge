# Prompt30 implementation plan (30 Oct 2026)

Forensic baseline: main `e36c20e`. Server core exists (`src/server.py`,
loopback HTTP + `api_v2` + `Executor` + broker + registry + forge +
dashboards + orchestration). Missing: true CLI, model tier router,
budget guard, readiness doctor, headless story, parity tests, jury pack.

Live right now: phone BV9300 (USB), AVD emulator-5556 (booted),
CPU Glimmer :11439 UP; Llama :11437 DOWN; no cloud key in env;
TV/watch offline.

## Build order (one branch `feat/p30-cli-release`, one PR)
- P30-A CLI: `src/cli.py` (argparse, in-process core, no GUI deps) +
  `openbridge` shims (`.cmd`/shell) + `python -m src.cli`. Commands:
  version/doctor/models/devices/ask/capabilities/workflows/approvals/
  sessions/evidence/test/serve/agent. Flags: --json/--quiet/--verbose/
  --no-color/--timeout/--model/--provider/--session/--evidence-dir/
  --dry-run/--yes(low-risk only). Exit codes per §7.2. stdout JSON
  stable + versioned; diagnostics on stderr.
- P30-B Router: `src/ai/router.py` tiers LOCAL-FAST/LOCAL-QUALITY/
  CLOUD-HIGH/CLOUD-MAX/AUTO with auditable reason log; never silent
  local↔paid switch; consent gate for cloud escalation.
- P30-C Budget: `src/ai/cloud_budget.py` caps (per-request/session/day/
  total), allowed models, retries; error codes CLOUD_API_KEY_MISSING/
  CLOUD_AUTH_FAILED/CLOUD_QUOTA_EXCEEDED/CLOUD_BUDGET_BLOCKED/
  CLOUD_MODEL_UNAVAILABLE; secrets via OS store/env, never CLI args.
- P30-D Doctor: readiness module with REQUIRED statuses (READY/MISSING/
  INVALID/INCOMPATIBLE/BLOCKED/PERMISSION_REQUIRED/AUTH_REQUIRED/
  MODEL_NOT_FOUND/INSUFFICIENT_RESOURCES/API_UNAVAILABLE/NOT_TESTED),
  per-feature + per-mode; no global READY unless all usable.
- P30-E Headless: `serve --headless` (signals, health, journal flush,
  no orphan sockets); systemd unit + Windows scheduled-task doc.
- P30-F Parity tests: GUI≡CLI contracts/auth/state/audit/Undo +
  concurrent-clients no-double-execution.
- P30-G Live matrix: local arms real (phone + AVD = 2 distinct
  endpoints); cloud arms BLOCKED without a key (plumbing + diagnostics
  proven, spend needs explicit owner opt-in). Fault injection on a safe
  workflow. Evidence packs per §14 (local-only originals, redacted
  public exports).
- P30-H Jury pack: ZIP builder + verify script + G01–G22 verdicts +
  §21 final report + verdict (GO/CONDITIONAL/NO-GO).

## Honest BLOCKED (stated, never faked)
Paid cloud (no key, no current spend order), watch/TV/ESP32/Wii/vacuum
(offline/absent), macOS, independent-machine clean install, video
recording (owner-gated). Llama :11437: attempt local start; if it
fails, LOCAL-FAST = Glimmer-limited, documented.
