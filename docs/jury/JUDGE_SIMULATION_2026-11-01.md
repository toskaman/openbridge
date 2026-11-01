# JUDGE SIMULATION — 1 November 2026 (OPERATION FINAL FRONTIER §16)

Target: `main` @ `ae1194a` (PRs #164→#169 merged), release candidate v0.2.0.
Method: three adversarial passes against current files, CI state, and
evidence — scored against what a stranger can verify, not what the
changelog claims. Adverse findings preserved; fixes reference the commit
that actually landed them.

## Judge A — Technical execution

Scope: architecture, reliability, security, test quality,
interoperability, cross-platform operation, failure handling.

### A1. Findings

| # | Finding | Source | Severity | Disposition |
|---|---|---|---|---|
| A-1 | Android lab flaky on release SHA: 3 guest deaths across 2 runs (e2e NET-04 409 ×2, phone fail-fast ×1), `adb: device offline` / TCP-5554 refused | runs 41312111939, 41312550552 | HIGH | NOT A CODE BUG: zero Android-surface diff 19eaede→ae1194a; 5/5 green on 19eaede; run3 4/5 with e2e green on fresh hosts. Residual: emulator-host flake documented, fail-fast verdicts |
| A-10 | Run3 phone hung 26 min at stage=evidence (unbounded adb after guest death + pipeline masking by tee), job-cancelled with no verdict | run 41313438904 | HIGH | FIXED in this commit: all harness adb bounded by timeout(1) + pipefail; regression test red→green; full suite 2083 OK |
| A-2 | Mutating dispatch reachable without consent before §13 | `src/runtime/api_v2.py` (pre-#168) | HIGH | FIXED in #168: API 403 + CLI preview + tests |
| A-3 | Transplant store unbounded growth | `src/forge/transplant.py` (pre-#168) | MEDIUM | FIXED in #168: cap 128, oldest-evicted + tests |
| A-4 | Transplant CLI ran without explicit consent flag | `src/cli.py` (pre-#168) | MEDIUM | FIXED in #168: consent gate + tests |
| A-5 | Dashboard label charset unsanitized | `src/runtime/dashboards.py` (pre-#168) | LOW | FIXED in #168 |
| A-6 | Android companion `full_control` reset unvalidated (A1) | recon §13 | MEDIUM | OPEN: needs emulator-validated Java change; owner list |
| A-7 | Suite flaked once locally: 2 fails under 12 GB model load | local run 1 Nov | LOW | Not reproduced in 3 subsequent full greens (2082 OK) + all CI green; attributed to memory pressure, documented |
| A-8 | F90 modules (8) software-tested + API/CLI-wired but no hardware validation | FRONTIER90 report | MEDIUM | Documented as NOT hw-validated; README claims CLI+API only |
| A-9 | macOS graphical behavior untested (CI is unit-level) | verify workflow | LOW | STALE — corrected 01-Nov evening: headless Chromium+WebKit UI smokes (verify `browser-macos`, 8 smokes) + cleanroom install+capture on macos-15-intel AND macos-26 are green; residual is headed/human-driven browsers only |

### A verdict

Architecture is modular (runtime/forge/fabric/ai layers, typed actions,
deterministic gates, receipts). Reliability evidence is strong on
server-side (2082 tests, verify+clean-room green on the release SHA)
and honest-but-flaky on Android emulators (infra, proven by diff).
Security review was real: 4 findings fixed with tests, 2 dismissed with
grep evidence, 1 deferred. Weakest point: no hardware validation for F90
and no physical-motion footage — both disclosed, neither disguised.

## Judge B — Meta innovation

Scope: what Meta AI genuinely creates, rules-vs-model gap, synthesis
novelty, evaluation quality, safety boundaries, usefulness.

### B1. Findings

| # | Finding | Source | Severity | Disposition |
|---|---|---|---|---|
| B-1 | ModelStudy48: rules 36.1% beat Llama 22.2% — the headline benchmark favors the baseline | `docs/benchmark/modelstudy48/` | HIGH (optics) | PUBLISHED WITH THE WARTS (README + RESULTS.md); rules win on constrained phrasing, models add open-phrasing coverage; no superiority claim made |
| B-2 | 6 unsafe substitutions in eval (pre-gate) | rescore_gate eval | HIGH | FIXED: S8 deterministic gate blocks 6/6, 0 false positives on 72 Llama rows; new frozen 24-case set unsafe 2→0 |
| B-3 | S8 calibration set is small (24 frozen cases, one host) | intentffect/REGISTRATION.md | MEDIUM | Disclosed as indicative; frozen + registered so it cannot silently drift |
| B-4 | Glimmer 30B: 7 load attempts, 7 OOM | eval logs | MEDIUM | Environmental (12 GB host), not quality; disclosed; Glimmer UI-panel evidence stands on its verified run |
| B-5 | Same-class instance ambiguity passes the S8 gate by design | gate spec | LOW | By design; consent preview shows the target; documented |
| B-6 | FR `lance chkdsk`-style pc_run uncovered | gate coverage | LOW | Documented gap |

### B verdict

Meta's contribution is concrete and evidenced: Muse-generated TV
control panels (installed, dispatched, receipted, revoked — Oct 31),
Llama NL→plan routing, structured synthesis. The evaluation is the
most honest part of the submission: a losing benchmark published
anyway, unsafe-substitution failures fixed by a deterministic gate
rather than hidden. Weakest point: small calibration sets and no
Glimmer runtime numbers on this host — both stated plainly.

## Judge C — Demo and impact

Scope: first impression, README, video, install, clarity, polish,
reproducibility, real-world impact.

### C1. Findings

| # | Finding | Source | Severity | Disposition |
|---|---|---|---|---|
| C-1 | No physical vacuum-motion footage; Oct 31 press was ADB-injected, vacuum already docked | DEVICE_EVIDENCE + runbook | HIGH (demo) | Disclosed in README + audit; manual-press runs owner-gated; fallback video labeled honestly (78 s, no physical footage claimed) |
| C-2 | README was stale/copied (bonus section without proof) | pre-#167 README | MEDIUM | FIXED in #167: rewritten A–L, bonus section evidence-backed |
| C-3 | Broken-link / stale-total risk across ~large docs tree | docs/ | MEDIUM | FIXED: 44 links + 8 images validated; counts recomputed (2082, 35 VERIFIED) |
| C-4 | Video is a fallback cut, not a live demo | final-fallback-video | MEDIUM | Labeled as fallback; scene map + sources hashed; physical branch owner-gated |
| C-5 | Stranger reproducibility depends on clean install | QUICKSTART | LOW | VERIFIED: clean_install_check 8/8 + offline DEMO_COMPLETE on release tree |

### C verdict

A judge understands the project in seconds (hero + 30-second
explanation), can install it cleanly (8/8), can run the offline demo,
and can trace every showcased claim to evidence. The demo ceiling is
real: the strongest physical story (TV panel → vacuum) lacks motion
footage, and the video says so by omission rather than by fabrication.
Nothing in the presentation overclaims what the evidence shows.

## Residual weaknesses (carried into the release audit)

1. Android emulator-host flake (infra; run3 4/5, e2e green on
   fresh hosts; harness now verdicts every wedge via A-10 fix).
2. F90 hardware validation pending (all 8 modules).
3. No physical-motion footage; manual runs owner-gated.
4. Small S8 calibration set (24 frozen cases).
5. A1 Android companion fix open.
6. macOS graphical path untested — CORRECTED 01-Nov evening: headless browser UI smokes + cleanroom captures green on macos-latest, macos-15-intel, macos-26; only headed/human-driven browsers untested.
