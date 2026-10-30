# Release status and remaining work

Authoritative checklist, reconciled against main `50406d3` on 30 October 2026 (PR130 merged, 0 open PRs, suite 864 green on Windows + Linux CI; live :18765 still on `ea2a102`, reload owner-gated). [Documentation index](README.md) · [Evidence index](RELEASE_EVIDENCE.md) · [Archived checkpoints](archive/RELEASE_CHECKPOINTS.md). Earlier branch names, ports, test counts and pending flags in archived notes are historical.

## Integrated work

| Area | Delivered scope | Evidence and limits |
|---|---|---|
| Fabric and Forge | Typed discovery, trusted observation-bound publication, consent, first-read verification and removal | [Forge guide](forge/README.md), [TV journey](forge/TV_GLIMMER_JOURNEY.md), [selector lifecycle](forge/WORKSPACE_JOURNEY.md). Historical receipts do not prove current hardware readiness or remote erasure. |
| Routing and Companion controls | AUTO/PREFERRED/PINNED routes, leases, deduplication, Companion 0.11.0 on phone/TV/Watch7 (signed watch pair), point-of-dispatch full-control recheck and burst-lock fixes | [Complete contributor handover](release/COMPLETE_HANDOVER.md), [Watch acceptance](release/WATCH_CONTROL_ACCEPTANCE.md). Original 2→16 cause remains unproven; duplicate/expiry coverage is unit + integration (restart journal, HTTP scan), live-hardware retest pending. |
| Durable runtime state | Policy + unresolved-outcome persistence (PR59) plus pre-dispatch invocation journal with cross-process claim admission (PR128) | [Persistence scope](runtime/PERSISTENCE.md). Crash recovery refuses re-execution (honest UNCERTAIN), never replays. No automatic replay. |
| P0 hardening (30 Oct) | Pairing confirm attempt limits (PR127), supervised STT worker subprocess (PR129), relay-scan HTTP verification (PR130), BridgeWindows plaintext/PSK warnings + sealed-transport design (BridgeWindows PR4) | [Known limitations](KNOWN_LIMITATIONS.md). Residuals documented per item (offline transcript brute force, no VRAM gate, VRAM/design follow-ups). |
| Multi-PC + legacy + ports | Bridge accepts up to 8 agents, PC2 verified; legacy C agent proven on XP SP3 + Win7 SP1 QEMU guests (VMs deleted, trace kept); ESP32 P1 firmware + host protocol proof | [Legacy evidence](evidence/vm-legacy-xp-win7-30oct.md), [device registry](DEVICE_EVIDENCE.json) (15 VERIFIED rows), [port catalog](KNOWN_LIMITATIONS.md). |
| Routing evaluation | Preregistered synthetic inputs/gold and full result archive; router and policy-aware heuristic both32/32 | [Results and actual Meta design review](evaluation/routing-v1/RESULTS.md). Eight correlated families; no unseen-protocol or model-superiority claim. |
| Command Center | PR60 and prompt correction PR63 merged; registered-skill parsing, bound preview, consent and receipts | [Current overview](../README.md), [command service](../src/runtime/command.py), [UI regression](../tests/e2e/command_center_smoke.py). Earlier PR60 findings describe its earlier head; merge alone is not new physical proof. |
| Explanation evaluation preparation | PR62 merged the draft prompt/sample/rubric/budget | [Freeze guide](evaluation/routing-v1/explain/FREEZE_GUIDE.md). Preparation is not an approved freeze, completed calls or measured explanation quality. |

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
