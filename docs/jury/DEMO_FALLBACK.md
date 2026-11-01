# Demo fallback — one-command scripted UI replay (Campaign Three §5.6, judge-C W3)

The centerpiece live demo is owner-gated (hardware + owner presence +
`DEMO_PHYSICAL_RUNBOOK.md`) and recording is owner-gated. This fallback is
the offline alternative: a scripted replay of the **recorded S5/S5b
receipts** inside the **real OpenBridge UI**, impressive without any owner
hardware — and honestly labeled at every step.

## One command

```powershell
python scripts/run/demo_fallback.py
```

Serves on an automatic free loopback port and opens
`http://127.0.0.1:<port>/#/replay/autoplay` in a browser: loopback only, no
hardware, no model, no pairing, no discovery probes (a fixed port can be
forced with `--port`). Stop with Ctrl+C. Variants:

- `python scripts/run/demo_fallback.py --no-browser` — serve only.
- `python scripts/run/demo_fallback.py --check` — headless verify
  (CI-friendly): asserts bundle identity, 2 scenarios × 9 stages,
  SIMULATED playback, and verbatim receipt ids, then exits.

## What the judge sees

Two recorded scenarios, each stepping through the §5.6 chain —
intent → model → proposal → validation → consent → publish → action →
verify → revoke — with Play/Pause/Prev/Next and per-step dots:

1. **S5 T1** — "Create a control panel on my TV so I can operate my robot
   vacuum": Glimmer 30B proposal (4 buttons incl. dock), VALID, install on
   TV relay `relay-dabd2a796665`, Dock press, `tx-ab731d7b885b5e1a`
   VERIFIED, revoke + deny.
2. **S5b** — T2 panel FIND press: `tx-4a96f8f626a1adc5`
   EXECUTED_UNVERIFIED, 15-poll oracle, revoke + deny.

Every stage shows its receipt values plus the tracked proof doc they come
from (`docs/benchmark/S5_UI_FREEZE.md`,
`docs/evidence/s5-tv-panel-31oct.md`,
`docs/evidence/s5b-safe-seek-31oct.md`).

## Honesty rules (enforced, not just documented)

- A **REPLAY · SIMULATED** banner is pinned at the top of the view, and
  every stage card carries its own **SIMULATED** chip.
- Receipt data is verbatim: `tests/unit/test_demo_replay.py` asserts each
  quoted value (tx ids, relay id, reply-sha prefixes, deny strings) also
  appears in the tracked proof doc, and that every stage cites its source.
- No fabricated footage: the replay renders text receipt data only — no
  video, no simulated effects presented as real.
- No live calls possible: `src/ui/replay.js` performs exactly one GET
  (`/api/demo-replay`); unit + browser tests assert it contains no POST
  path, and the browser smoke aborts any non-GET `/api/*` call.
- Honest limits travel with the replay (adb-injected press, no observed
  S5 motion, EXECUTED_UNVERIFIED S5b beep).

## Verification

- `python -m unittest tests.unit.test_demo_replay -v`
- `python -m tests.e2e.demo_replay_smoke` (needs Playwright browsers)
- Full suite: `python -m unittest discover -s tests -q`
