# Release status and remaining work

Authoritative checklist, reconciled against main `dfaf972` on 28 October 2026. [Documentation index](README.md) · [Evidence index](RELEASE_EVIDENCE.md) · [Archived checkpoints](archive/RELEASE_CHECKPOINTS.md). Earlier branch names, ports, test counts and pending flags in archived notes are historical.

## Integrated work

| Area | Delivered scope | Evidence and limits |
|---|---|---|
| Fabric and Forge | Typed discovery, trusted observation-bound publication, consent, first-read verification and removal | [Forge guide](forge/README.md), [TV journey](forge/TV_GLIMMER_JOURNEY.md), [selector lifecycle](forge/WORKSPACE_JOURNEY.md). Historical receipts do not prove current hardware readiness or remote erasure. |
| Routing and Companion controls | AUTO/PREFERRED/PINNED routes, leases, deduplication, hold-only Watch controls and concurrency fixes | [Complete contributor handover](release/COMPLETE_HANDOVER.md), [Watch acceptance](release/WATCH_CONTROL_ACCEPTANCE.md). Original repeated-action cause remains unproven; duplicate/expiry coverage is unit-only. |
| Durable runtime state | Corrected policy and completed-unresolved-outcome persistence through PR59 | [Persistence scope](runtime/PERSISTENCE.md). No pre-dispatch crash journal, global multi-process admission or automatic replay. |
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
- Supported read-only multi-PC review is complete; OpenBridge remains single-PC. The earlier safety-blocked port is not retried automatically. Scheduling remains cancelled.
- Preserve evidence, failed attempts, licenses and frozen evaluation inputs. Follow [workspace maintenance](WORKSPACE.md) before deleting generated files.
