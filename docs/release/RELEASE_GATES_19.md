# Release acceptance gates — verdicts (30 Oct 2026)

Revision under review: main `972b545` (§8 merged). Verdict scale:
PASS / CONDITIONAL / OPEN. An OPEN gate is stated, never hidden.

## Gate A — Source integrity: PASS
- Exact commit recorded (`972b545`); working tree controlled (docs PR
  pending review, nothing uncommitted on main).
- Historical evidence preserved (542 commits, no rewrites).
- LICENSE present; no BIOS/ROM/firmware in repo or archives; legacy
  agent.exe traces scrubbed.
- Contribution provenance audited: zero files predate 2026-10-26T16:24:00Z.

## Gate B — Automated verification: CONDITIONAL
- Suite green on merged heads (1064 on main; 1070–1087 on feature heads).
- New regression tests pass locally (RetroArch 5/5 ×5 stress).
- CI: main `1e8066a`/`070392a` success; `972b545` queued at review time
  (squash-identical to a 6/6-green PR tree); PR146 re-run in flight after
  the UDP race fix `7ad47ce`; PR147 queued.
- Zero skipped tests in `tests/` (no `skip`/`skipIf`/`skipUnless`).
- Closes when the queued runs report green.

## Gate C — Security: PASS
- No known unauthorized action path (§18 Auditor 3).
- Pairing + permission boundaries validated (§10, live re-verify).
- Duplicate physical execution controls validated (per-id locks,
  same-id repush, crash-drill 5/5 Undo).
- Secrets/personal data excluded from public outputs (capture manifest
  local-only, redaction discipline).

## Gate D — Meta novelty: OPEN
- No Meta-synthesized capability with independent verification exists yet.
- What exists: fair deterministic baselines (rules 1.4% on 1,000 turns),
  transparent honest-negatives (G3 0 grammar keys), install-local open
  models (Llama 3.2 3B, Glimmer 30B).
- Path: §11 model arms with recorded provenance (models-gated).
- Demo line until then: "measured, not claimed".

## Gate E — Real devices: PASS (with caps)
- Supported ops physically verified (registry 18 rows, levels labeled).
- Recovery + revocation tested (Undo, crash drill, reconnect).
- Simulated/emulated results labeled separately, never mixed.

## Gate F — User experience: CONDITIONAL
- Core workflow runs through the actual UI (Playwright smokes:
  2 cards / 118 widgets SMOKE_PASS).
- Real screenshots on file (E:/shots, manifest local-only).
- Errors + limitations understandable (KNOWN_LIMITATIONS.md).
- Device identity + permissions explicit (planner + tutorials).
- Closes after the storyboard rehearsal (owner-gated).

## Gate G — Demo and submission: OPEN (owner-gated)
- 180 s storyboard ready; video NOT recorded (needs new owner order).
- Public GitHub accessible; evidence links valid; install docs on file.
- Portal fields + submission receipt: participant-owned.

## Bottom line
Ship-blockers in our control: none. OPEN gates need gated resources:
models (D), rehearsal/recording (F/G), organizer portal (G).
