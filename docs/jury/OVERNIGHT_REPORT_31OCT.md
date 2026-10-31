# Overnight execution report — 31 Oct 2026 (OvernightRun M1–M6 extract)

## A. Repository state

- Inspected HEAD at start: `cb471de` (`origin/main`, PR157 merged, CI 10/10).
- Code freeze this run: `a713e70` on `feat/p30-jury-release`.
- PR: [Draft #158](https://github.com/toskaman/openbridge/pull/158) (base `main`).
- Branch delta vs `origin/main`: 19 files, +884/−16 (see `git diff origin/main...HEAD --stat`).
- Integrated: M1 matrix tests, M2 Undo/doc sync, background relay sources,
  M3 refusal channel, M4 runbook+preflight, M5 eval harness+scorecard+QUICKSTART+
  clean-install, M6 storyboard+checklist+pack manifest. Pending: S5/S6 owner
  runs, Glimmer eval rerun (RAM), on-device background proof, final video,
  submission (all owner-gated).

## B. Completed tasks

| Task | Change | Why | Tests | Result | Evidence | Limitation |
|---|---|---|---|---|---|---|
| M1 matrix A–N | Burst fix (live presses only) + atomic invoke claim + C/M tests | Duplicate/replay safety | 1223 unit + stress 6/6 | PASS | `tests/runtime/test_overnight_*.py` | WinError 10053 flake under load (monitored) |
| M2 Undo sync | Per-change RESTORED/FAILED/MANUAL wording in README + limitations | "Exact Undo" was overstated | Link/doc review | DONE | README, `KNOWN_LIMITATIONS.md` | Physical acts non-undoable (disclosed) |
| Background relay | `RelayService.java` foreground service + manifest + toggle + reattach | Companions must serve with screen off | javac android-34 | exit 0 | `companion/android/…` | No APK build / on-device run yet; BLE scans stay foreground-only |
| M3 §9 refusal channel | `reason` in history + route + Activity timeline | Refusals were invisible | 3 new (RED→GREEN) + shot | 29/29 | `E:/shots/refusal_channel.png` | — |
| M4 runbook+preflight | S5/S6 runbooks + read-only preflight gate | Owner runs need a script | Preflight live | PARTIAL (tv+vacuum GO, watch asleep) | `docs/jury/DEMO_PHYSICAL_RUNBOOK.md` | Execution owner-gated |
| M5 eval subset | `dev/eval_local_subset.py` + 50-turn run + scorecard | §10 bounded $0 comparison | 150 turns, 0 crashes, 0 sends | rules 0/50, llama 4/50, glimmer BLOCKED (host OOM) | `docs/benchmark/EVAL_SUBSET_50_LOCAL.md` | Prefix-only; no Spark arm (unauthorized) |
| §7 clean install | `docs/QUICKSTART.md` + isolated-venv check | Judges must reproduce | 8/8 | PASS | `scripts/verify/clean_install_check.py` | Windows only; Linux/macOS open (no VM, no WSL python) |
| M6 storyboard | One-story 180 s redesign + manifest + checklist | Old board was a feature tour | — | DONE, video BLOCKED | `docs/jury/DEMO_STORYBOARD_FINAL.md` | Beats S5/S6 need owner footage |
| M6 compliance | Source-backed checklist | §15 independent check | Official pages fetched | deadline/tracks CONFIRMED, 5 OPEN | `docs/jury/COMPLIANCE_CHECKLIST.md` | Full rules text not public-fetchable |
| §14 pack | QUICKSTART added to manifest; pack built+verified | Release readiness | `verify_jury_pack.py` | VERIFY OK | `E:/OpenBridge-Jury-ON-31oct-v2.zip`, sha256 `07bcc80e…2294` | Local artifact; publication owner-gated |

## C. Test results (this run, Windows 10, PC1)

- Unit: **1223 passed** (`pytest tests --ignore=tests/e2e`, 93 s), 0 failures.
- Browser: offline_smoke (390/768/1440/3440), command_center_smoke,
  fabric_smoke — all PASS, zero page errors.
- Clean-install: 8/8 PASS in an isolated third-party-free venv.
- CI (PR158): windows/ubuntu/macos unit + browser PASS; browser-macos pending
  at report time — see PR checks before merge.
- No historical counts reused; totals above are from this session.

## D. Physical results

- REAL_HARDWARE (this run): TV + vacuum live in discovery (fresh `observed_at`);
  preflight PARTIAL. No commands sent (owner-gated).
- Emulator: Pixel 6 AVD still BLOCKED (dies ~3 min); ESP32/RetroArch/Playdate
  prior proofs stand, not re-run tonight.
- Synthetic: FakeCompanion refusal loop (unit), seeded-UI refusal shot (payload
  from a real `process()` refusal, served by a demo server — labeled as such).
- Unverified implementation: background relay on-device behavior; Glimmer
  arm quality; S5 motion; S6 watch chain.

## E. Meta AI results

- Models: llama3.2:3b-instruct-q4_K_M (digest `a80c4f17…b8b72`, :11437),
  muse-glimmer:30b-q4_K_M (digest `de878ce3…4464c`, :11438). Identity verified
  via `/api/tags` at run time.
- Real inference calls: 50 llama turns (33,264 prompt / 3,445 eval tokens),
  50 glimmer attempts (0 tokens — all HTTP 500 `llama-server … out-of-memory`).
- Task outcome: llama 4 resolved + 44 clarifications; rules 0; glimmer no data.
- Failed attempts: glimmer arm (host ~6 GB free vs 18 GB model) — environmental.
- Cost: $0 (local only; cloud untouched, budget intact).
- Benchmark conclusion: on this prefix, the small local model beats rules on
  coverage without guessing; the 30B comparison is still open. Resolution
  coverage ≠ semantic correctness.

## F. Release readiness

| Gate | Status |
|---|---|
| Source freeze commit | `a713e70` |
| Full suite + smokes | GREEN (local) |
| Evidence registry valid | yes (28 rows, unchanged schema) |
| Pack built + verified | `E:/OpenBridge-Jury-ON-31oct-v2.zip` (21 files, sha256 `07bcc80e233f…2294`), VERIFY OK |
| QUICKSTART in pack | yes |
| Secrets scan | pack builder scan passed |
| Clean install | 8/8 (Windows) |
| CI full green | PENDING (browser-macos) — re-check before merge |
| Publication | OWNER-GATED (not done) |

## G. Jury package

- Demo sequence: `DEMO_STORYBOARD_FINAL.md` (problem → fabric → S5 panel →
  watch chain → safety/refusals → differentiators → close).
- README: hero + Meta paragraph + 3 scenarios + evidence links verified current;
  Undo wording corrected.
- One-liner: "Local Meta AI that understands the devices around you, reaches
  the ones your PC can't, and only changes what it can prove it can undo."
- Strongest verified capabilities: (1) evidence-backed cross-transport device
  graph with read-only default; (2) Meta-composed, strictly-validated controls
  with consent + receipts + revocation; (3) crash-safe duplicate-proof execution
  with structured refusal surfacing.
- Disclosures: S5 motion + manual press pending; watch chain pending; Glimmer
  eval pending; background relay unrun on hardware; Linux/macOS clean-install
  open; video/compliance opens listed in their files.
- Submission readiness: materials ready; submission itself is the owner's action.

## H. Remaining tasks (ranked by competition impact)

1. S5 owner run (TV panel → manual press → observed vacuum motion). Next: owner
   wakes hardware, runs preflight, follows `DEMO_PHYSICAL_RUNBOOK.md` §2.
2. S6 owner run (watch → second device). Next: same, §3.
3. Glimmer eval rerun (50-turn arm). Next: free host RAM (close heavy apps),
   re-run `dev/eval_local_subset.py --limit 50 --arms glimmer`.
4. Background relay on-device proof. Next: build APK (SDK now on E:), install
   on phone, screen-off poll test.
5. browser-macos CI → merge PR158. Next: re-check PR158 checks, merge when green.
6. Final video (owner-authorized). Next: storyboard capture manifest, recording
   day protocol.
7. Submission. Next: owner fills compliance OPENs, submits from their account.
