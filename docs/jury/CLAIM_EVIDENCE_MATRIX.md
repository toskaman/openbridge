# Claim / evidence matrix (V4-02)

Every public claim, its status and where to check it. A claim without evidence is listed as pending, never implied.

## Status vocabulary (repo ↔ V4 pack)
| Repo status | V4 pack equivalent | Meaning |
|---|---|---|
| REAL_HARDWARE_VERIFIED | IMPLEMENTED_HARDWARE_TESTED | ran on the author's real device(s); receipt with commit and date |
| INTEGRATION_VERIFIED | IMPLEMENTED_HARDWARE_TESTED (partial) | end-to-end through real services, not every device |
| SIMULATED_VERIFIED | IMPLEMENTED_SIMULATED | CI tests with fakes / synthetic data, labelled SIMULATED |
| IMPLEMENTED_UNVERIFIED | IMPLEMENTED_SIMULATED (no test of the external part) | code exists; the external service was not exercised |
| NOT_IMPLEMENTED | DOCUMENTED_NOT_IMPLEMENTED | design only |
| BLOCKED | — | refused by policy |

## Claims

Reconciled 31 Oct 2026: where this matrix previously said REAL/LIVE for a V4
row but the shipped V4 table said SIMULATED + pending, the conservative
SIMULATED status now governs until a re-verified run lands. Original wording
is preserved in git history, not deleted.

| Claim | Status | Evidence |
|---|---|---|
| Discovers mDNS, SSDP, ADB USB/Wi-Fi, Freebox OS (authorized), BLE via relays | REAL_HARDWARE_VERIFIED | EVIDENCE_LEDGER.md, README screenshot |
| One graph, strong-ID merge only, grants per link | REAL_HARDWARE_VERIFIED | TV mDNS+ADB merge in EVIDENCE_LEDGER.md |
| ISP Router API (e.g., Freebox OS / UPnP-IGD): Freebox inventory | REAL_HARDWARE_VERIFIED | docs/FREEBOX_INTEGRATION.md |
| ISP Router API: generic UPnP-IGD read-only | SIMULATED_VERIFIED (fake IGD) | tests/fabric/test_upnp_igd.py; real read: `python -m dev.igd_read` (pending) |
| BLE relay through phone and TV, signed protocol, revoke | REAL_HARDWARE_VERIFIED | docs/RELAY_SECURITY.md |
| Reversible write with exact Undo and read-back | REAL_HARDWARE_VERIFIED | docs/physical-package-receipt.json |
| Crash-recoverable physical workflows (not ACID): 5 kill points | REAL_HARDWARE_VERIFIED | crash drill 5/5, EVIDENCE_LEDGER.md |
| Cross-transport timeline + competing hypotheses + read-only probe | SIMULATED_VERIFIED (CI drills + independent labels) | tests/runtime/test_timeline.py; real TV+router capture pending (prior live-capture wording needs re-verification) |
| Privacy-preserving cloud escalation (never "zero-knowledge") | SIMULATED_VERIFIED (golden corpus + unit) | tests/runtime/test_redact.py, tests/runtime/test_cloud_escalation.py; no ACCEPTED live escalation receipt yet (the recorded Spark call is the 27-Oct synthetic advisory, not a V4-05 run) |
| Meta Model API live call (muse-spark-1.3) | REAL (synthetic facts) | docs/runtime-meta-receipt.json, EVIDENCE_LEDGER 27 Oct |
| Registered ablation, rules vs Llama vs Glimmer vs Spark | MEASURED: rules 0.833, Llama 0.833, Glimmer 0.722; Spark not run (budget) | docs/benchmark/v4/REGISTRATION.md |
| Visual read-back with local Glimmer | REAL_HARDWARE run, verdict INCONCLUSIVE — not a VERIFIED pass (Glimmer misread a screensaver) | tests/unit/test_visual_readback.py; `python -m dev.visual_readback_tv` re-run pending |
| BLE zone proximity (zones, not positions) | SIMULATED_VERIFIED | tests/runtime/test_ble_zones.py; `python -m dev.ble_zone_calibrate` (pending) |
| Voice command (local STT worker; cloud Muse Voice path kept, consent-gated) | REAL_HARDWARE_VERIFIED: frozen corpus 16/16 no wrong-skill, owner voice 2/2 | docs/evidence/v4/overnight/N2_N3_RESULTS.md; worker isolation unit-verified |
| Wear OS dynamic manifest | SIMULATED_VERIFIED | tests/fabric/test_wear_manifest.py; Watch7 run pending (prior REAL wording needs re-verification) |
| PC 2 as a client: owner jobs (`pc_job`) and Meta inference worker | jobs REAL_HARDWARE_VERIFIED (EVIDENCE_LEDGER); inference worker SIMULATED_VERIFIED | tests/runtime/test_windows_bridge.py, tests/unit/test_scheduler.py; real job + `python -m dev.benchmark_scheduler` (pending) |
| Tuya vacuum: reads, reversible suction/volume, full robot commands | REAL_HARDWARE_VERIFIED (reads, suction + exact Undo, seek, start/pause/dock; manual moves EXECUTED_UNVERIFIED) | tests/fabric/test_tuya_local.py; EVIDENCE_LEDGER.md (27-Oct movement run); docs/DEVICE_CAPABILITIES.md; live re-verify 30 Oct (facts + seek accepted, row 26) |
| Meta-only runtime | VERIFIED (static + network trace) | src/ai/registry.py, tests/unit/test_meta_only_network_trace.py |
| Capability explorer: UI schemas matched to live device capabilities | SIMULATED_VERIFIED + live discovery smoke (2 cards/118 widgets) | tests/fabric/test_capability_explorer.py, tests/runtime/test_explorer_api.py (§6 `5224d99`) |
| Hardware intelligence: PC facts + task rankers + micro-benchmarks | REAL_HARDWARE_VERIFIED (PC1 + BV9300 live) | tests/fabric/test_hardware_intel.py, tests/runtime/test_hardware_api.py (§9 `2ad4688`) |
| Permissions center: 13-entry catalog, measured states, grant flow | REAL_HARDWARE_VERIFIED (BV9300 live re-verify) | tests/fabric/test_permissions.py, tests/runtime/test_permissions_api.py (§10 `f1c460c`) |
| 1,000-turn eval kit: rules baseline, 200/200 convs, 0 crashes/sends | MEASURED (rules 1.4%; model tiers pending, oracles sealed) | docs/benchmark/EVAL_1000_RULES_BASELINE.md (§11 `070392a`) |
| Multi-device orchestration: DAG workflows, 9 scenarios, 9 new skills | SIMULATED_VERIFIED + live USB capture/send/montage | tests/runtime/test_workflows.py, docs/evidence/s7-live-usb-30oct.md (§7 `1e8066a`) |
| Official Android emulator driven via adb (level 4, no companion) | EMULATOR_VERIFIED (capture/probe/send + cleanup) | docs/evidence/avd-ob-pixel-30oct.md (registry row 18) |
| Relay dashboards: generated/patched/saved/restored UIs, reconnect repush | SIMULATED_VERIFIED + live watch run 30 Oct | tests/unit/test_dashboards*.py (§8 `972b545`); docs/evidence/g04-watch-30oct.md (registry row 22) |
| RetroArch loopback control (VERSION/GET_STATUS verified; VOLUME_UP sent-unverified) | REAL_HARDWARE_VERIFIED (host-PC software loopback only: 127.0.0.1 UDP to local RetroArch process, menu-state only; no external physical device) | docs/evidence/retroarch-loopback-30oct.md (registry row 19, §13 `db5dedf`) |
| Stress hardening: locks, byte cap, typed IO, crash drill | SIMULATED_VERIFIED + crash drill 5/5 | docs/STRESS_14_REPORT.md (§14 `ef58712`) |
| CLI + headless + GUI/CLI parity + jury pack | REAL_HARDWARE_VERIFIED (CLI live runs) + SIMULATED_VERIFIED (parity) | docs/CLI_REFERENCE.md, docs/P30_MODEL_MATRIX.md, docs/release/P30_GATES_AND_REPORT.md (§P30 `73cfef5`) |
| Glimmer-synthesized capabilities validated + published + revoked (2) | REAL_HARDWARE_VERIFIED (live phone bundle; pending-kernel staging) | docs/evidence/p30-glimmer-synthesis-30oct.md (registry row 20) |
| Phone+AVD orchestration via CLI, sha-verified montage | MIXED: REAL_HARDWARE_VERIFIED (BV9300 phone half) + EMULATOR_VERIFIED (Pixel 6 AVD half — emulator, not physical) | docs/evidence/p30-cli-orchestration-30oct.md (registry row 21) |
| Native controls on real Watch7 + long-press loop; TV 0.11.0 PAIRED | REAL_HARDWARE_VERIFIED (SM-L310 + Android TV) | docs/evidence/g04-watch-30oct.md (registry rows 22-23, G04 PASS) |
| Phone 0.11.0 PAIRED READY + relay probe | REAL_HARDWARE_VERIFIED (BV9300) | docs/evidence/g04-watch-30oct.md (registry row 24) |
| Companion found over Wi-Fi with no adb address (QU-bit browse + NSD) | REAL_HARDWARE_VERIFIED (SM-L310, adb disconnected) | docs/evidence/companion-lan-discovery-30oct.md (registry row 25) |
| Meta-planned quiet-mode pair: Llama 3.2 3B plan validated + consented, TV volume 22→21 adb read-back, vacuum dock dispatched + acked | REAL_HARDWARE_VERIFIED (vacuum EXECUTED with stable read-back, motion not observed) | docs/evidence/s4-quiet-mode-31oct.md (registry row 27) |
| Meta-generated vacuum panel on TV: Glimmer 30B proposal, 4/4 buttons bound + OCR-render-verified, hold-press executed from panel, revoke→deny | REAL_HARDWARE_VERIFIED (dock already charge_done 100pct so motion unobservable; tap adb-injected, pipeline identical) | docs/evidence/s5-tv-panel-31oct.md (registry row 28, S5 T1 FULL PASS) |
| Paid Meta cloud end-to-end | BLOCKED (no key, no spend order) | preflight + budget guard unit-tested; $0 spent |
| Companion background relay on a real phone (screen off, toggle 8/8) | REAL_HARDWARE_VERIFIED | docs/DEVICE_EVIDENCE.json (registry row 29 `companion-0.12.0-background-relay-hardware`) |
| S5b safe seek: T2 panel → hold-press FIND → tx-4a96f8f626a1adc5 → 15-poll oracle → revoke + deny | REAL_HARDWARE_VERIFIED (adb-injected press, labeled; beep not machine-proven) | docs/evidence/s5b-safe-seek-31oct.md (registry row 30) |
| Cloud end-to-end flow on physical phone: pair → signed BLE scan (3 advertisers) → service+forward oracle → relay revoke → 409 deny, 9/9 PASS | REAL_HARDWARE_VERIFIED (rugged phone, Android 13; isolated test server, live untouched) | scripts/verify/cloud_e2e.py (reproduces the run); verdict.json is an author-PC capture, not in repo (registry row 31 `cloud-e2e-flow-physical-phone`) |
| Companion voice loop on physical phone: on-device mic clips → signed fetch (sha256) → local Meta MMS STT → caption report + TTS | REAL_HARDWARE_VERIFIED (phone mic; low-tier parse, clarification-only in run; near-silence hallucination documented) | src/runtime/command_drain.py; drain fg.log is an author-PC capture, not in repo (registry row 32 `companion-voice-loop-transcribe-report-tts`) |
| Structured model refusal channel (proposal/refusal/needs_clarification/unsupported) | IMPLEMENTED + unit-verified (TDD 3/3); jury shot staged from live UI | docs/jury/OVERNIGHT_REPORT_31OCT.md §B |
| Wi-Fi-direct relay: pair + command drain + signed report over direct LAN with adb disconnected | REAL_HARDWARE_VERIFIED (TV 0.12.0, adb down throughout the drain, caption on screen) | docs/jury/screens/tv-wd7-direct-drain-caption.png (registry row 33 `wd7-direct-drain-tv-adb-down`) |
| S6 watch → TV volume over direct LAN: owner press → one EXECUTED → MUSIC +1 read back, revoke clears watch | REAL_HARDWARE_VERIFIED (no watch adb; rendering + revoke owner-confirmed; R1 physical repeat; R1 pair 9 min before R4; vehicle FAIL on re-press-denied, human-accepted) | docs/evidence/s6-watch-tv-volume-01nov.md (registry row 34 `s6-watch-tv-volume-01nov`) |
| Watch voice loop over direct LAN: 3 spoken orders fetched + locally transcribed + signed reports | REAL_HARDWARE_VERIFIED (clarifications only, no wrong-skill; STT imperfect; row-1 Heard cut at 60 chars; self-reported log; sleep timeouts at tail) | docs/evidence/voice-watch-direct-01nov.md (registry row 35 `watch-voice-direct-loop-01nov`) |
| S5c owner manual presses START + DOCK: tx-8abdd1eb + tx-63ee07451c4099ce VERIFIED, oracle standby→goto_charge, revoke→deny | REAL_HARDWARE_VERIFIED (motion oracle-proven, unfilmed; attempt-1 lease-stale adverse preserved; attempt-2 pairing operator-assisted, presses all owner) | docs/evidence/s5-tv-panel-01nov-manual.md (registry row 36 `s5-tv-manual-press-01nov`) |
| TV sleep/wake + Companion reveal skills from PC: wake + foreground EXECUTED verified, sleep effect owner-confirmed | REAL_HARDWARE_VERIFIED (sleep receipt UNVERIFIED — Wi-Fi ADB drops in sleep; wake needs the remote; no remote power-on claim) | docs/evidence/tv-sleep-02nov.md (registry row 37 `tv-power-reveal-02nov`) |
| S8 intent/effect gate over workflow proposals: eval2 unsafe 2→0, eval3 (48 replies) unsafe 4→0, zero fully-correct blocked | MEASURED (frozen held-out sets, rescore tooling; gate guards the model→spec bridge incl. CLI workflows-plan; Ask relies on fingerprinted preview + consent) | docs/benchmark/intenteffect/RESULTS.md, RESULTS3.md, REGISTRATION3.md; src/runtime/intent_effect.py |
| F90 endurance: 1128 ops simulated-wire rerun green, graceful shutdown | SIMULATED_VERIFIED (thresholds hold; hardware leg owner-gated, not run) | dev/f90_endurance.py; docs/jury/FRONTIER90_REPORT_2026-11-01.md |
| Capability Studio proposals (UI v2) | TEMPLATE-DRIVEN, not Meta-generated (deterministic client templates; rehearsal SIMULATED; same consent/revoke rails) | docs/ui/UI_V2_WORKSPACE.md; src/ui/views/studio_view.js |
| Jury video V2: 159.33 s cut with owner-recorded hardware footage, committed builder, shot-level honesty labels | VERIFIED ARTIFACT (sha256 3d3e228e…; V2 frozen; finale owner-filmed) | docs/jury/VIDEO_BUILD_V2.md, VIDEO_IRL_PLAN.md; scripts/video/build_jury_video.py |

## Never claimed
ACID transactions; zero-knowledge or anonymous cloud calls; 2D or person location from BLE RSSI; that BLE presence proves interference; fabricated scores; organizer acceptance or bonus eligibility.
