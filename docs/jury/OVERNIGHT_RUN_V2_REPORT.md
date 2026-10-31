# Overnight Run V2 — Final Report (§25)

Cloud-first execution of `OvernightRun.MD` (2074 lines, 31 Oct 2026): clean-room
OS matrix, Android emulator lab, genuine Meta inference, cloud end-to-end,
technical hardening, owner-gated hardware, evidence, release.

Status of this document: DRAFT until the last cloud runs land; facts below are
observed values only, with run IDs and SHAs.

## A. Repository state

- `main` HEAD: `e1ac13929fd50aa9c3bd82d19199d4ab45f5d013` (PR #159 merged, CI 11/11).
- Release branch: `feat/p30-jury-release`, HEAD `4c82e9e` at draft time.
- Open PRs at draft time: none (PR for this branch to be opened at the end).
- Branch delta vs `main`: 15 commits, 11 files, +903/−45.
- Local suite: 1245/1245 OK (`python -m unittest discover -s tests`, 99 s).
- Evidence registry: 30 VERIFIED rows (`docs/DEVICE_EVIDENCE.json`).

## B. Cloud infrastructure

All runs on GitHub-hosted runners (public repository, $0 spent, $0 billed).

| Run | Workflow | Result at draft |
|---|---|---|
| 41210900996 | cleanroom.yml | 8/8 jobs success |
| 41211778338 | android.yml | build-apk+wear success; phone+tv failed (diagnosed, fixed) |
| 41212561298 | android.yml | build-apk+wear success; phone+tv failed (diagnosed, fixed) |
| 41212969695 | android.yml | build-apk+wear+tv success; phone failed (diagnosed, fixed) |
| 41213691030 | android.yml | in progress (phone no-incremental verdict pending) |
| 41212947403 | android.yml | cancelled (stale code, superseded) |
| 41210547807/41210549911 | cleanroom/android | failed (workflow authoring bugs, fixed and re-run) |
| 41213691030 | android.yml | cancelled at 15 min (phone hung again, same screencap symptom) |
| 41214555252 | android.yml | build-apk+wear+tv success; e2e failed (pair-confirm on OCR false positive, fixed); phone failed (same hang, contingency C) |
| 41215098799 | android.yml | build-apk+phone(C)+tv+wear success; e2e failed (code unreadable, setup overlay suspected, fixed) |
| 41215688399 | android.yml | in progress (e2e v2: front-raise + diag) |

No paid runners, no secrets, no persistent public servers. Firebase Test Lab,
Kaggle and Colab were assessed and marked NEEDS-ACCOUNT (owner-gated, §K).

## C. Clean-room OS matrix (run 41210900996, 8/8)

Application distribution `OpenBridge-App.zip` (built in-run from the branch,
`VERIFY OK`) installed from scratch on every target: `clean-install: 8/8 passed`
(venv-create, venv-python, venv-isolated, cli-doctor, cli-smoke, offline-demo,
server-start-ui, clean-shutdown) plus browser captures (home/activity/diagnostics
PNG + `tour.webm`) except the Debian container (no browser).

| Target | Arch | Python | Result |
|---|---|---|---|
| windows-2025 (Server, labeled, not consumer Win11) | AMD64 | 3.14.4 | 8/8 + captures |
| windows-11-arm | ARM64 | 3.14.4 | 8/8 + captures |
| ubuntu-24.04 | x86_64 | 3.14.4 | 8/8 + captures |
| ubuntu-24.04-arm | aarch64 | 3.14.4 | 8/8 + captures |
| macos-15-intel | x86_64 | 3.14.4 | 8/8 + captures |
| macos-26 | arm64 | 3.14.4 | 8/8 + captures |
| debian:12 container (labeled, not a full VM) | x86_64 | 3.11.2 | 8/8, logs only |

Evidence pack: per-OS `env.json` + `install.log` + captures, downloaded to
`E:/cleanroom-evidence/r2/` with per-OS SHA tracking in the media manifest.

Known wrinkle: `clean-shutdown` reports `exit=1` and still PASSes (server stops
via exception path; no orphan process — flagged in §26 for the jury, not hidden).

## D. Android emulator results

Real Companion APK built from source with SDK tools only (no Gradle):
`openbridge-companion.apk`, 123283 bytes, `apksigner verify` OK, cross-platform
build script (Windows + Linux).

| Guest | API | Result at draft |
|---|---|---|
| phone (pixel_6, x86_64, google_apis) | 33 | PASS via contingency C (pid 3416, fullscreen foreground, 0.12.0, logcat; run 41215098799): screencap hung 4× on this emulator image (root cause not isolated, emulator-side); visuals covered by real-phone hardware |
| TV (tv_1080p, x86, android-tv) | 33 | PASS: install, launch, D-pad, 2 captures, logcat (run 41212969695) |
| Wear (wearos_large_round, x86_64) | 33 | PASS: install, launch, capture, logcat (runs 41211778338+) |

First-launch captures show the Android runtime permission dialog (honestly labeled);
`pm grant` pre-granting landed after the green runs, so the next captures show the
real UI. Emulator results are labeled emulated, never hardware.

## E. Meta AI results

Production runtime is Meta-only (`src/ai/registry.py` enforced). All spend $0.

- Frozen 50-turn subset (prompts + oracles frozen): rules 0/50, Llama 3.2 3B
  (local CPU) 4/50 + 44 clarifications, Glimmer arm OOM-BLOCKED on the host
  (4.4 GB free vs 18 GB model + 4 GB CUDA alloc; environmental, not scored).
- S5-T3 (unsupported shell panel): Llama FAIL ×2 under the v2 prompt (misleading
  substitute, no bypass — pathology preserved as evidence); Glimmer BLOCKED ×2 (OOM).
- S5-T1/T2 (31 Oct AM, Glimmer 30B medium tier, temp 0): T1 PASS (4-button vacuum
  panel incl. dock), T2 bindings exact (TV volume + find-me). 4.4 GB host RAM made
  later Glimmer reruns OOM; no Glimmer rerun was possible overnight.
- §12 structured refusal (proposal/refusal/needs_clarification/unsupported) shipped
  with 81/81 mechanism tests; a refused request no longer yields an installable panel.
- Model-level refusal + consent/revoke + duplicate/replay (A–N) + crash/uncertain
  suites green locally and in CI.

No mocked model output is presented as genuine inference anywhere in this report.

## F. Cross-device evidence

Real hardware (owner-authorized phone + TV; watch asleep, S6 owner-gated):

- Phone (BV9300 Pro, Android 13, WLAN (redacted)): APK rebuilt from source and
  installed over adb; relay `relay-c388ba6dafcd` paired with the on-screen code
  (AEAD `aead1` negotiated); signed `get_status`; bounded 8 s BLE scans returning
  4–6 live advertisers ingested as `REAL_HARDWARE_VERIFIED ble_relay`; scan refused
  with the screen off (foreground-only consent holds); foreground-service
  notification shown; relay answers with the activity closed and with the screen
  off; owner toggle stops (TCP 47800 closed, `Relay unreachable`) and restarts the
  service; toggle regression `scripts/verify/companion_toggle_check.py` 8/8
  on-device. Registry row 29.
- TV (Android TV 11, ADB Wi-Fi <tv>:5555) + Tuya vacuum (S5b): relay
  `relay-dabd2a796665` paired first-try via OCR code; Meta-generated T2 panel
  installed (Find vacuum + Volume up/down); OCR-located hold-press on Find vacuum
  dispatched `vacuum_command seek` (receipt `tx-4a96f8f626a1adc5`,
  `EXECUTED_UNVERIFIED`); 15 × 2 s Tuya polls stable (`smart_clean`, fault 0 —
  the robot was already cleaning on its own); `set_controls([])` revoke (0 grants);
  post-revoke press denied; `relay_revoke` VERIFIED. Registry row 30,
  [proof](../evidence/s5b-safe-seek-31oct.md). Press is adb-injected (labeled),
  not a manual tap; beep not machine-proven.
- mDNS `_openbridge-relay._tcp` was unanswered (0 packets) from the phone; the
  adb-forward path was used instead (documented limitation, real finding).

Cloud end-to-end (`android.yml` `e2e` job + `scripts/verify/cloud_e2e.py`):
server → emulator pairing → signed scan → adb oracle → relay-side revoke.
Verdict pending at draft time.

## G. Video evidence inventory (draft)

| Clip | Source | Duration | SHA-256 (short) | Status |
|---|---|---|---|---|
| `E:/shots/phone-scan-live.mp4` | BV9300 screenrecord during a live BLE scan | 19.97 s, 1080×2388 h264 | (manifest at release) | REAL_HARDWARE, curated |
| `tour.webm` × 6 | clean-room browser captures (win/ubuntu/macos × arch) | short | per-OS | EMULATED-RUNNER, curated |
| `phone-demo.mp4` | emulator job | — | — | pending phone verdict |
| CLIP-11/12 (TV→vacuum, watch→device) | physical | — | — | CLIP-11 partial (S5b pressed+captures, beep unheard by machine); CLIP-12 owner-gated |

Every clip keeps its source commit, test ID and classification; no unrelated
events are combined; no private data (keys, LAN IPs, serials) is shown.

## H. Technical corrections

| # | Bug | Root cause | Fix | Proof |
|---|---|---|---|---|
| 1 | cleanroom dispatch 422 | `runner.temp` forbidden in top-level `env:` | per-step expressions | dispatch accepted |
| 2 | ubuntu/win verify fail | `/dist`+`/evidence` suffixes lost in the env patch (authoring error) | restored paths | 8/8 green |
| 3 | debian install fail | `set -o pipefail` under dash (no bash) | `shell: bash` + bash installed | debian 8/8 |
| 4 | build-apk fail | `setup-android@v3` installs obsolete `tools` pkg | preinstalled runner SDK | APK built |
| 5 | build-apk fail 2 | `d8.bat`/`.exe` names hardcoded (Windows-only) | cross-platform suffixes | APK on ubuntu |
| 6 | TV emulator fail | no `android-tv` x86_64 image for API 34/33 | API 33 + arch x86 (published builds) | TV green |
| 7 | phone screencap hang ×2 | unknown (not API, not exec-out, not record conflict) | API 33, shell+pull, `--no-incremental` | verdict pending |
| 8 | Background relay button | `refresh()` never styled it; no debounce | setToggle+content-desc, 1 s debounce, optimistic update | 8/8 on-device |
| 9 | S5b pairing fail | 120 s code TTL expired during slow OCR; stale code stays on screen | round-by-round confirm | paired 1st try |
| 10 | Emulator captures show permission dialog | first-launch setup requests runtime permission | `pm grant` pre-grant | next captures show UI |
| 11 | README Playdate claim | zero registry evidence | claim narrowed to verified ESP32 | registry-consistent |
| 12 | `clean-shutdown exit=1` | server stops via exception path | none (no orphan); disclosed | install.log |

## I. Release package

(Draft — rebuilt at the end from the final HEAD.)

- ARTIFACT A (application), ARTIFACT B (evidence), ARTIFACT C (media): rebuilt via
  `scripts/release_pack.py`, `VERIFY OK` each, SHA-256 manifest, no-secret scan.
- Previous set (`OpenBridge-App-8ab1e44.zip` + Evidence + Jury-ON-31oct-v2) is
  superseded by the new HEAD.

## J. Competition readiness (draft)

Strongest three actual achievements:

1. Real phone relay end-to-end on hardware: signed pairing, live BLE, background
   survival with the screen off, regression-tested toggle — all observed, not claimed.
2. Real TV → vacuum chain twice (S5 dock + S5b seek): Meta-generated panels,
   rendered controls, dispatched command, poll oracle, revoke + deny verified.
3. Clean-room install 8/8 on 7 hosted targets (Windows/Linux/macOS × x64/ARM64 +
   Debian) from the release ZIP, plus a real APK on three emulator form factors.

Remaining weaknesses: emulator-phone capture instability (hardware phone covers
the behavior); Glimmer overnight OOM (AM results stand); S6 watch owner-gated;
manual-press last mile owner-optional (adb-injected, labeled); Firebase/Kaggle
need accounts.

## K. Owner-only action list

- Re-pair the phone + TV companions with the live server if desired (test pairings
  used an isolated server; 30 s each, on-screen code).
- Optional S6: open the companion on the Watch7, connect it to the PC; manual
  press → second device, then revoke (runbook ready).
- Optional S5-manual: press the installed panel button by hand (adb-injected run
  already proven and labeled).
- Approve + publish: release artifacts, final 3-minute video, hackathon submission.
- Accounts (only if wanted): Firebase/GCP for Test Lab, Kaggle/Colab for hosted
  Glimmer reruns.
- Restore note: phone `stay_on_while_plugged_in` was set to 7 during testing and
  restored to 0 at the end of the run (verified below).

## Acceptance gates (§22)

| Gate | Verdict |
|---|---|
| G01 audit | PASS |
| G02 PR integrated | PASS (PR #159 merged; this branch PR pending) |
| G03–G08 clean-room | PASS (8/8, run 41210900996) |
| G09 consumer Win11 | PARTIAL (Server runner, explicitly labeled) |
| G10 APK | PASS (123283 bytes, apksigner OK) |
| G11 phone emulator | PASS (contingency C, run 41215098799) |
| G12 TV emulator | PASS |
| G13 Wear emulator | PASS |
| G14–G16 cloud e2e | PENDING (job committed, dispatch after phone verdict) |
| G17 Meta inference | PARTIAL (Llama 4/50 + S5 Glimmer T1/T2; overnight Glimmer OOM) |
| G18 secrets/cost | PASS ($0, guards intact) |
| G19 model refusal | PASS (mechanism 81/81; T3 pathology preserved) |
| G20 consent/revoke | PASS |
| G21/G22 dup/crash | PASS (A–N + lifecycle suites) |
| G23 lifecycle | PARTIAL (functional green; perf measurements not collected) |
| G24/G25/G26 evidence | PASS (captures + clips + provenance; manifest at release) |
| G27/G28/G29 packages | PENDING (rebuild at end) |
| G30/G31 README/matrix | PASS (30 rows, claims reconciled) |
| G32 S5 physical | PASS (S5 + S5b; manual-press optional) |
| G33 S6 watch | BLOCKED (watch asleep; runbook ready) |
| G34 background relay | PASS (hardware: closed-app + screen-off liveness, toggle 8/8) |
| G35 benchmark | PARTIAL (50-subset scored; Glimmer OOM honestly blocked) |
| G36 storyboard | PASS (exists) |
| G37 rules | PARTIAL (5 OPENs per checklist) |
| G38/G39 publish/submit | OWNER (not attempted) |
