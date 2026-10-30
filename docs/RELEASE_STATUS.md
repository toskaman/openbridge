# Release status and remaining work

Authoritative checklist, reconciled against main `73cfef5` on 30 October 2026 (PR145-149 merged; suite 1145 green on Windows + Linux CI; registry 24 VERIFIED rows; live :18765 still on an older commit, reload owner-gated). [Documentation index](README.md) · [Evidence index](RELEASE_EVIDENCE.md) · [Archived checkpoints](archive/RELEASE_CHECKPOINTS.md). Earlier branch names, ports, test counts and pending flags in archived notes are historical.

## Integrated work

| Area | Delivered scope | Evidence and limits |
|---|---|---|
| Fabric and Forge | Typed discovery, trusted observation-bound publication, consent, first-read verification and removal | [Forge guide](forge/README.md), [TV journey](forge/TV_GLIMMER_JOURNEY.md), [selector lifecycle](forge/WORKSPACE_JOURNEY.md). Historical receipts do not prove current hardware readiness or remote erasure. |
| Routing and Companion controls | AUTO/PREFERRED/PINNED routes, leases, deduplication, Companion 0.11.0 on phone/TV/Watch7 (signed watch pair), point-of-dispatch full-control recheck and burst-lock fixes | [Complete contributor handover](release/COMPLETE_HANDOVER.md), [Watch acceptance](release/WATCH_CONTROL_ACCEPTANCE.md). Original 2→16 cause remains unproven; duplicate/expiry coverage is unit + integration (restart journal, HTTP scan), live-hardware retest pending. |
| Durable runtime state | Policy + unresolved-outcome persistence (PR59) plus pre-dispatch invocation journal with cross-process claim admission (PR128), extended to HTTP execute keys + direct intents (PR135) | [Persistence scope](runtime/PERSISTENCE.md). Crash recovery refuses re-execution (honest UNCERTAIN), never replays. No automatic replay. |
| P0 hardening (30 Oct) | Pairing confirm attempt limits (PR127), supervised STT worker subprocess (PR129), relay-scan HTTP verification (PR130), BridgeWindows plaintext/PSK warnings + sealed-transport design (BridgeWindows PR4), HTTP/direct idempotency journal claims (PR135) | [Known limitations](KNOWN_LIMITATIONS.md). Residuals documented per item (offline transcript brute force, no VRAM gate, VRAM/design follow-ups). |
| Device connect (30 Oct) | Hardware agent matrix + auto connection planner + per-device connect tutorials + guided agent pick (PR133) | Staged agent binaries served per hardware; unknown hardware asks the owner instead of guessing. |
| Multi-PC + legacy + ports | Bridge accepts up to 8 agents, PC2 verified; legacy C agent proven on XP SP3 + Win7 SP1 QEMU guests (VMs deleted, trace kept); ESP32 P1 firmware + host protocol proof | [Legacy evidence](evidence/vm-legacy-xp-win7-30oct.md), [device registry](DEVICE_EVIDENCE.json) (15 VERIFIED rows), [port catalog](KNOWN_LIMITATIONS.md). |
| Routing evaluation | Preregistered synthetic inputs/gold and full result archive; router and policy-aware heuristic both32/32 | [Results and actual Meta design review](evaluation/routing-v1/RESULTS.md). Eight correlated families; no unseen-protocol or model-superiority claim. |
| Command Center | PR60 and prompt correction PR63 merged; registered-skill parsing, bound preview, consent and receipts | [Current overview](../README.md), [command service](../src/runtime/command.py), [UI regression](../tests/e2e/command_center_smoke.py). Earlier PR60 findings describe its earlier head; merge alone is not new physical proof. |
| Explanation evaluation preparation | PR62 merged the draft prompt/sample/rubric/budget | [Freeze guide](evaluation/routing-v1/explain/FREEZE_GUIDE.md). Preparation is not an approved freeze, completed calls or measured explanation quality. |
| Capability explorer (30 Oct) | UI schemas matched to live capabilities + layouts + render API (PR140) | [Explorer tests](../tests/fabric/test_capability_explorer.py). Live discovery smoke (2 cards/118 widgets); TV/watch offline at proof time. |
| Hardware intelligence (30 Oct) | PC facts + task rankers + micro-benchmarks + API (PR141) | Live on PC1 + BV9300 (facts/rank/bench). Some collectors degrade per-metric; never invented. |
| Permissions center (30 Oct) | 13-entry catalog, measured states, grant flow + API (PR142) | Live re-verified on BV9300 (grants flip to granted). |
| Eval-kit baseline (30 Oct) | 1,000-turn replay harness, anti-leak oracles, rules baseline (PR143) | [Report](benchmark/EVAL_1000_RULES_BASELINE.md). Rules 1.4%; model tiers + judging pending (models down, no hosted authz). |
| Multi-device orchestration (30 Oct) | DAG workflows + 9 skills + stdlib montage + API + fixtures (PR144) | [Live USB proof](evidence/s7-live-usb-30oct.md) (registry row 17). Multi-target live runs pending TV/watch return. |
| Official emulator (30 Oct) | Pixel 6 AVD on WHPX driven via adb (PR144) | [AVD proof](evidence/avd-ob-pixel-30oct.md) (registry row 18, level 4, no companion). |
| Relay dashboards (30 Oct) | Generated/patched/saved/restored control UIs + reconnect repush (PR145) | Simulated relay proven; live watch run done 30 Oct ([proof](evidence/g04-watch-30oct.md), rows 22-23). |
| RetroArch + P2 gaps (30 Oct) | Loopback control + gap analysis (PR146) | [Loopback proof](evidence/retroarch-loopback-30oct.md) (registry row 19). VOLUME_UP sent-unverified (honest). |
| Stress hardening (30 Oct) | Workflow locks, store locks, byte cap, typed IO (PR147) | [Report](STRESS_14_REPORT.md). Crash drill 5/5. |
| Docs + gates (30 Oct) | Matrix sync, 180s storyboard, bonus, 10 audits, A-G verdicts, start-date audit (PR148) | D/G OPEN, B/F conditional; zero files predate the start ref. |
| CLI + jury release (30 Oct) | `openbridge` CLI + tiers + budget + doctor + parity + pack (PR149) | [Matrix](P30_MODEL_MATRIX.md), [gates](release/P30_GATES_AND_REPORT.md). 2 Glimmer candidates validated+revoked (row 20); phone+AVD orchestration sha-verified (row 21). Paid cloud BLOCKED (no key). |
| Watch native UI + TV shot (30 Oct) | G04 closed: QUICK CONTROLS on real Watch7 + long-press loop acked; TV 0.11.0 PAIRED shot | [Proof](evidence/g04-watch-30oct.md) (registry rows 22-23). Watch re-paired to evidence driver; live link restorable via standard flow. |
| Phone 0.11.0 shot (30 Oct) | PAIRED READY + relay probe on owner phone | [Proof](evidence/g04-watch-30oct.md) (registry row 24). Live link untouched. |

## Remaining gates

| Priority | Task | Owner / acceptance condition |
|---|---|---|
| P1 | Explanation-stage freeze and evaluation | Owner reviews the draft; Codex coordinates author/approver separation and exact freeze before scored calls. Follow the freeze guide and fresh promotional-credit guard. Do not retro-score hardware demonstrations. |
| P1 | Hardware cleanup confirmation | Runtime owner/Codex reconciles receipts with hardware state, including the earlier location-restoration request and relay/forward cleanup. Preserve uncertainty; do not guess a baseline. |
| P1 | Physical control edge cases | Targeted owner-attended duplicate/expiry acceptance. Retain original amplification as unresolved unless evidence establishes its cause. No broad replay or automatic control grants. |
| Release | Coordinated live reload | Check active operations and pending recovery, preserve open changes, coordinate with contributors, then verify the actual loaded revision. This page does not assert that the running service matches main. |
| Release | Participant review and submission | Select the final commit, verify portal fields, complete private declarations and retain a submission receipt. Indie Developer / Push the Frontier / solo toskaman are already confirmed. |

## Verification and ownership

Exact test counts, source revisions, receipts and CI belong to individual evidence records and PRs. Run `python -m unittest discover -s tests -q` and appropriate browser checks for new implementation. Software checks are distinct from physical acceptance and organizer approval.

Codex owns release/integration and has taken over persistence while Claude is unavailable. Spark's merged Command Center contributions retain their recorded scope. Coordinate overlapping paths on [issue36](https://github.com/toskaman/openbridge/issues/36); the shared local board records assignments, not extra proof of delivery.

## Standing constraints

- English interfaces and public documentation. Keep Claude's main theme and accurately scoped Meta attribution.
- No videos, recordings, edits or renders until a NEW explicit owner request. No native desktop keyboard/mouse automation.
- Meta-only runtime models. Hosted calls require eligible fresh promotional-credit observations through the existing guard; no paid fallback, stale-balance reuse or automatic retries.
- Multi-PC is delivered: the bridge accepts up to 8 agents and the second PC is verified (binary swap hash-matched). The earlier safety-blocked single-agent limit is superseded. Scheduling remains cancelled.
- Preserve evidence, failed attempts, licenses and frozen evaluation inputs. Follow [workspace maintenance](WORKSPACE.md) before deleting generated files.
