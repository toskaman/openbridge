# Adversarial audit — 10 perspectives (30 Oct 2026)

Ten explicitly separated reviews against current main `972b545` (§8).
Speculative findings without evidence are rejected and listed as such.

## Auditor 1 — Hackathon judge
- Finding: the proven orchestration loop is single-device; "multi-target"
  cross-device execution is simulated, not live.
- Severity: Medium.
- Subsystem: `src/runtime/workflows.py`, `tests/unit/test_workflow_scenarios.py`.
- Evidence: registry row 17 (single-device live), matrix cap "partial".
- Repro: `python -m unittest tests.unit.test_workflow_scenarios` (uses
  FakeCompanion/EMULATOR transports).
- Corrective: live multi-target run (phone capture → TV-class route);
  hardware/owner-gated.
- Proof test: same invocation path with REAL_HARDWARE receipts on 2 targets.
- Residual: claim stays "partial" until that run exists.

## Auditor 2 — Rules and eligibility
- Finding: none blocking. Contribution/provenance clean.
- Severity: Low.
- Subsystem: `CONTRIBUTIONS.md`, `docs/jury/CONTRIBUTION_*.md`.
- Evidence: start-date audit (542 commits / 802 files, zero predate
  2026-10-26T16:24:00Z); agent.exe legacy traces scrubbed; no BIOS/ROM/
  firmware in repo or archives.
- Repro: `git log --name-status` audit one-liners (see CONTRIBUTIONS.md).
- Corrective: none; portal fields stay owner-owned.
- Residual: organizer attestation pending.

## Auditor 3 — Security
- Finding: no path found from untrusted device/model bytes to execution
  without consent + allowlist + typed capability.
- Severity: Low.
- Subsystem: `src/adapters/retroarch.py`, `src/runtime/primitives.py`,
  `src/runtime/remote_controls.py`.
- Evidence: `test_only_loopback`, `test_rejects_unknown_command_without_sending`,
  revocation disables, consent receipts.
- Repro: `python -m unittest tests.unit.test_retroarch tests.unit.test_primitives_media`.
- Corrective: none required; forbid non-loopback RetroArch stays.
- Residual: FakeCompanion is cooperative, not adversarial; no fuzzed-relay run.

## Auditor 4 — Distributed systems
- Finding: approval→execution failures are receipted; crash drill 5/5 Undo.
- Severity: Low.
- Subsystem: `src/runtime/capture_store.py`, workflow locks (§14).
- Evidence: `STRESS_14_REPORT.md`; per-id locks; repush same-id on reconnect.
- Repro: `python -m unittest tests.unit.test_stress_14 tests.unit.test_dashboards_reconnect`.
- Corrective: real relay-kill drill on hardware (gated).
- Residual: kill drill proven on store layer only, not on a live relay.

## Auditor 5 — Meta AI researcher
- Finding: today, rules select predefined ops; Meta models do not yet drive
  end-to-end runs. Honest-negative evals on file (G3 0 grammar keys, 1.4%
  rules baseline).
- Severity: Medium (positioning: do not overclaim "agentic").
- Subsystem: `dev/eval_1000.py`, `docs/EVAL_1000_RULES_BASELINE.md`.
- Evidence: 1000-turn baseline; Glimmer/Llama arms pending.
- Corrective: run §11 model arms; record provenance per run.
- Proof test: eval-kit tier columns filled with receipts.
- Residual: until then, "measured, not claimed" is the demo line.

## Auditor 6 — Hardware engineer
- Finding: feasibility labels are truthful; known-not-built items documented.
- Severity: Low.
- Subsystem: `docs/DEVICE_EVIDENCE.json`, `docs/KNOWN_LIMITATIONS.md`.
- Evidence: REAL/EMULATOR/SIM levels; wallpaper/WhatsApp/A2DP/TV-mic/WoL
  listed NOT built (policy/privacy).
- Repro: matrix vs registry diff (CI or `scripts/` check).
- Corrective: none.
- Residual: Watch7 offline; TV offline at last proof.

## Auditor 7 — QA engineer
- Finding: two timing races found and fixed (mtime ties → sequence index;
  UDP fire-and-forget → bounded wait). Remaining: ghost adb device
  (`emulator-5554` offline) handling relies on adb error surfacing.
- Severity: Low.
- Subsystem: `tests/unit/test_retroarch.py`, `src/adapters/android.py`.
- Evidence: CI fail → fix `7ad47ce` → re-run pending; android collectors
  degrade per-metric (`test_android_collect_degrades_on_failures`).
- Repro: 5× local unittest OK; CI re-run watches the flake.
- Corrective: if flake recurs, quarantine with retry-once + bug note.
- Residual: adb ghost behavior is environment-specific, asserted only loosely.

## Auditor 8 — UX and accessibility
- Finding: connection planner + per-device popup tutorials exist (PR133);
  request UI is English-only as required.
- Severity: Low.
- Evidence: planner + tutorial strings in tree; French war-room stays out
  of the product UI.
- Repro: manual connect flows (hardware-gated).
- Corrective: none code-side; rehearsal validates wording.
- Residual: tutorial accuracy for unseen devices is untested.

## Auditor 9 — Demo engineer
- Finding: 180 s storyboard is beat-proven on paper, but no rehearsal run
  has timed it.
- Severity: Medium.
- Subsystem: `docs/jury/DEMO_STORYBOARD_180S.md`.
- Evidence: per-beat proof column; cut-list discipline stated.
- Repro: rehearsal protocol in the storyboard (owner-gated recording).
- Corrective: two dry runs before any final take.
- Residual: live beats depend on devices being online that day.

## Auditor 10 — Product strategist
- Finding: post-hackathon value is concrete (receipted, undoable control);
  no retention/telemetry story by design (privacy-first, local-first).
- Severity: Low (out of hackathon scope).
- Evidence: receipts, Undo, KNOWN_LIMITATIONS honesty.
- Corrective: none before submission.
- Residual: growth/retention is future work, not a submission claim.

## Rejected for lack of evidence
- "Companion APK exfiltrates data" — no APK behavior analyzed; no such
  claim made anywhere. Rejected.
- "Model prompt-injection via device names" — device strings are data,
  never executed; no injection sink found. Rejected pending a sink.

## Deduplicated action list
1. Live multi-target run (A1) — hardware/owner-gated.
2. §11 model arms with provenance (A5) — models-gated.
3. Storyboard rehearsal ×2 (A9) — owner-gated.
4. Relay-kill drill on live hardware (A4) — hardware-gated.
5. Watch RetroArch CI re-run for the UDP flake (A7) — in progress.
6. No code-blocking finding: nothing above stops a submission commit.
