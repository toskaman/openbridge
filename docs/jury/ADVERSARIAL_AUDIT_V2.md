# Final Adversarial Audit (§26) — DRAFT

Ten independent reviewers, evidence-backed findings only. Each finding carries
severity, location, evidence, reproduction, fix, acceptance test and residual risk.
Speculative findings are rejected. Status: draft until the last runs land.

## 1. Hackathon Judge — breakthrough clarity

**Finding (info):** the demo story is real but multi-threaded (phone relay +
TV→vacuum + clean-room + emulators). A jury remembers ONE thing. The report
picks the TV→vacuum chain as the spine and demotes the rest to montage.
No code change. Residual: storyboard discipline during video assembly.

## 2. Meta Researcher — genuine inference value

**Finding (low):** overnight Glimmer reruns OOM on the host, so the only Glimmer
planning evidence is the 31 Oct AM session (T1 PASS, T2 exact, frozen).
Evidence: `docs/benchmark/EVAL_SUBSET_50_LOCAL.md`, S5 ledger.
Reproduction: `python -m dev.s5_t3_offline --model glimmer` on a ≤6 GB host.
Fix: hosted GPU rerun (Kaggle/Colab, owner account) or accept AM evidence.
Acceptance: rerun receipt or explicit BLOCKED label. Residual: accepted BLOCKED;
AM evidence stands, no fresh overnight Glimmer tokens. Llama arms ran overnight
(4/50 + T3 pathology), so "genuine Meta inference" holds on Llama + AM Glimmer.

## 3. Cloud Engineer — reproducibility without the owner's PC

**Finding (low):** clean-room installs rebuild the ZIP in-run from the branch
checkout rather than downloading a published release asset.
Evidence: `cleanroom.yml` build-pack job. This still proves a fresh install
(no developer paths, no credentials, fresh runner), but a judge cannot fetch the
identical bytes without checking out the SHA. Fix: attach the ZIP as a release
asset at publication (PH10). Acceptance: release asset SHA matches the run log.
Residual: none after PH10.

## 4. Windows Engineer — claim accuracy

**Finding (low):** `windows-2025`/`windows-11-arm` runners are Server SKUs, not
consumer Windows 11 desktops.
Evidence: `env.json` (`system`/`release` per job). The report and README label
this explicitly (G09 PARTIAL). No fix possible on free cloud. Residual: accepted;
local `OB-JUDGE-WIN11-CLEAN` VM remains the documented fallback, not built.

## 5. Linux Engineer — headless + shutdown

**Finding (low):** `clean-shutdown` PASSes with `exit=1` on all 7 targets.
Evidence: `install.log` (`clean-shutdown — exit=1`, `8/8 passed`).
Root cause: the server stops via the exception path (nonzero exit) while
releasing everything (no orphan). Reproduction: any clean-room run.
Fix (post-submission): exit 0 on intentional shutdown; keep the no-orphan check.
Acceptance: `exit=0` in a future run. Residual: disclosed, cosmetic.

## 6. macOS Engineer — Intel vs Silicon + GPU claims

**Finding (info):** both architectures install and serve 8/8; no GPU inference
is claimed on runners (Glimmer never attempted there — 18 GB model vs runner RAM).
Evidence: per-OS `env.json` (arch x86_64/arm64) + `install.log`.
No Bluetooth/USB hardware claim is made from runners. Residual: none.

## 7. Android Engineer — companion on suitable targets

**Finding (medium):** the phone emulator capture hung 3× at `screencap` (~30 s,
exit 255) across API 34/33, exec-out/shell+pull, with/without screenrecord.
Evidence: runs 41211778338, 41212561298, 41212969695 (timelines in §H).
Install + launch succeed every time; TV (x86/API 33) and Wear are green, and the
same APK is proven on a real phone (pairing, BLE, background, toggle 8/8).
Reproduction: `android.yml` phone job. Fix attempted: `--no-incremental`
(run 41213691030, pending at draft). Acceptance: phone green, or G11 PARTIAL
with the hardware-phone coverage cited. Residual: if still red, the emulator gap
is documented and the behavior stays proven on hardware + two emulator shapes.
**Finding (low):** first-launch captures showed the permission dialog, not the UI.
Fixed with `pm grant` pre-grants (committed, next runs show the UI).
**Finding (fixed during the run, was high):** `RelayServer.get(ctx, null)`
unconditionally replaced the live screen sink with NOOP; the auto-started
foreground service detached the UI whenever its start landed after `onResume`,
silently dropping pairing codes (cloud e2e read dumpsys noise and failed
pair-confirm 409). Fixed: a null lookup never replaces a live Ui, the activity
releases its sink in `onDestroy`. Proven by physical e2e 9/9 (paired 1st try)
plus three further on-device pairings. Residual: none observed.

## 8. Security Engineer — consent, replay, revocation, keys

**Finding (medium):** the `full_control` standing-consent flag survives
re-pairing without a fresh consent tap (observed: phone re-pair kept
`full_control: true`).
Evidence: `relay-pair-confirm` declared payload (row 29 session).
Root cause: the flag is a device pref independent of the pairing key.
Reproduction: pair → allow full control → re-pair with a new code → flag kept.
Fix (post-submission recommended): clear `full_control` on every fresh pairing,
require one tap to re-allow. Acceptance: re-pair → flag false until tapped.
Residual until fixed: pairing still requires the on-screen code (possession),
so no remote attacker benefits; disclosed here and in row 29 limitations.
**Finding (low):** stale pairing codes stay on screen past the 120 s TTL and are
then refused ("not paired"); the vehicle hit this (S5b attempt 1).
Evidence: TV screenshots + relay `confirmPairing` (`pendingCode` expiry without
`ui.code(null)`). Fix (post-submission): clear the code card on expiry.
Acceptance: expired code disappears. Residual: cosmetic, vehicle works around it.
**Finding (info):** 6-digit code offline brute-force note stands (PAKE follow-up,
pre-existing limitation). Pairing attempt limits (5) + lockout hold.
No secrets in repo, logs, captures or artifacts (scanned at release).

## 9. QA Engineer — crashes, leaks, races

**Finding (low):** no reproducible crash, leak or race found in the overnight
scope. Suites: 1245 unit OK, A–N idempotency, crash/uncertain, lifecycle
(`test_endurance`, `test_apk_portal_lifecycle`), browser smokes incl. WebKit,
clean-install 8/8 × 7, on-device toggle 8/8. Flakes seen: none overnight
(previous WinError 10053 under load + WebKit timing flake remain documented).
Residual: perf measurements (§14 measures) not collected — functional only.

## 10. Demo Director — client action + verified consequence

**Finding (low):** CLIP-11 (TV→vacuum) is partial: pressed + captures + receipt +
polls exist, but the beep is not machine-audible and the press is adb-injected.
Evidence: `E:/shots/s5b/`, transcript `C:/tmp/on_s5b2.log`.
Fix: owner manual press when convenient (30 s) + room microphone for the beep.
Acceptance: one clip with visible press and audible/confirmed effect.
Residual: the labeled adb-injected chain already proves the full path; the manual
last mile is owner-optional, not a technical gap.

## Verdict

No P0 defect. Two mediums (phone-emulator capture stability; full_control
surviving re-pair) with mitigations and honest labels. Ship the report, the
release and the PR; fix the mediums post-submission or with owner time.
