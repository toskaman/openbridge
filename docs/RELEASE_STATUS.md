Latest hardware/remaining-work update: [28 October follow-up](release/PHYSICAL_FAILOVER_FOLLOWUP.md) and [current backlog](REMAINING_WORK.md). The two-relay rerun is partial; B3 controls are unmerged pending the repeated-action investigation.

# Current release evidence update — 27 October 2026

Current prioritized work and ownership: [remaining work](REMAINING_WORK.md). Latest source audit: `038f463` (including Watch7/Blackview evidence); older checkpoint counts and revisions below remain historical.

This update supersedes conflicting historical checkpoints below. Integration base: `437dfa3`; newer runtime work is preserved, not re-authored here. Final verification of this base is being recorded separately.

- [Physical trusted selector journey](forge/WORKSPACE_JOURNEY.md): selected TV observation, Rules plan, consent, publish/read/docs 200; revoke read 409, remove 200 then 404, close 200; remote Companion UI changed to unpaired. Existing Android permissions and owner-authorized automation were used. This is one tested device, not universal remote erasure or fresh human permission-dialog proof.
- [Completed v2 evaluation](forge/evaluation-v2/RESULTS.md): Rules/Llama/Glimmer 80/80 overall; each model made 25 actual calls. Deterministic refusals and harness scope checks are separately counted. No general superiority is established.
- Spark synthetic diagnostic succeeded; earlier failure is retained. No new hosted requests or paid fallback for release publication.
- Anonymous exact-source ec653af replay: 349 tests and 12 browser modules passed on the same PC with a fresh clone/venv and existing browser cache. This is historical evidence, not verification of subsequent runtime changes.
- Owner confirmed Indie Developer / Push the Frontier / solo toskaman. Final owner attestations, portal fields and submission receipt remain external gates.
- Shared assignments: https://github.com/toskaman/openbridge/issues/36. Codex owns release/UI/evaluation; Claude owns backend/Companion/hardware; Spark supplies bounded design/review proposals. No video until a NEW explicit owner request.

---

# Current release status

Status reconciled 27 October 2026 against merged PR #20 (`715da9638ed6747ba202f2e5a41dfdb5be7eaeb7`) and retained implementation/receipts. The recorded redesign validation is **314 local tests and seven passing CI checks**, not a new run during this documentation reconciliation. Local release-readiness changes remain work in progress until separately verified.

## Proven scope

- Forge compiles one read-only observation primitive into deterministic OpenAPI, schemas and a fixed client; explicit consent, current-source authority, first-read verification, revocation and removal remain deterministic gates. The default standalone host is simulated. Trusted internal provider injection supports source-bound runtime capabilities and actual host ports; HTTP/model inputs cannot supply provider truth. See [API](forge/CAPABILITY_FORGE_API.md), [architecture](forge/CAPABILITY_FORGE_ARCHITECTURE.md) and [publication contract](forge/VERIFIED_PUBLICATION.md).
- The final [runtime contract](coordination/DEVICE_CAPABILITY_CONTRACT_V1.md), true per-fact observation times and source-filtered fact reads supersede the provisional timestamp gate. RuntimeV1Provider checks current graph/route/capability authority and refuses unavailable/expired source-specific facts without aggregate fallback.
- Physical phone and TV relay publication is recorded. The combined [TV â†’ local Glimmer â†’ Forge HTTP journey](forge/TV_GLIMMER_JOURNEY.md) records four advertisers, a validated local proposal (259/98 tokens, 82.406 s, $0 provider cost), publish/read/documents 200, local-authority removal denial 409, removal 200 and removed route 404. It used owner-authorized automated consent, existing Android permissions and an ADB-forwarded connection. It does not prove fresh human Android permission-dialog acceptance, independently verified remote Companion unpairing or direct beacon control. All incomplete attempts remain retained.
- [Runtime evidence](../EVIDENCE_LEDGER.md) records authenticated Freebox inventory, read-only SSDP/UPnP discovery physically observed on the LAN, Watch7 pairing/reads, Windows read-only inspection and bounded graph/endurance checks. Unsupported protocols and broader device coverage remain expansion work.
- One allowlisted optional-app change and exact Undo are physically verified on the owned phone. A USB cable pull occurred specifically during **revert**; quarantine and exact recovery after reconnect were verified. Five process-kill recovery points are separate evidence. This does not establish cable loss during every write phase or on every device; the earlier refused timeout write remains a retained failure.
- PR #20 merged the website redesign. Muse Wonder authored complete theme CSS fields; the final explanatory field was truncated and is disclosed. See [visual verification](forge/UI_BEFORE_AFTER.md) and [redesign attribution](forge/META_WEBSITE_REDESIGN_PLAN.md). Targeted keyboard/contrast checks are not a full accessibility certification.

## Remaining release gates

| Gate | Acceptance condition |
|---|---|
| Normal product workflow | From a discovered device, explicitly choose an eligible relay/target, open a trusted runtime-bound Forge session, plan, consent, publish/read, inspect contract, revoke and remove. Missing/stale authority fails closed. A separate Forge host bound through `api_v2.reader(server)` is valid; main-process mounting is optional. The separate selector and launcher are implemented with controlled HTTP/browser and closure-race tests. Final committed-source replay and physical selector evidence are tracked in `forge/WORK_STATUS.md`; historical TV proof is separate. |
| English-only Windows portal | Completed: English HTML/static/dynamic/copy states and hidden metrics fix; four-width controlled browser checks passed. |
| Anonymous replay and acceptance | Record a clean anonymous installation/replay; finish remaining accessibility and independent security cases with exact evidence. |
| Broader evaluation | 80-case v2 suite frozen before inference. Rules and Llama runs completed; CPU Glimmer is in progress. A newly supervised fixed synthetic Spark diagnostic succeeded ($0.013182 estimated promotional cost), separate from accuracy evaluation. |
| Model inventory | Completed bounded upstream/installed metadata inventory; no weights redistributed. Exact packaged artifact/notice obligations require review if redistribution changes. Catalog identity alone remains distinct from runtime inference proof. |
| Submission | Confirm accepted track/team, contributions/licenses, anonymous links, four-category rehearsal, final owner review and portal receipt. Internal tests do not establish organizer acceptance or bonus eligibility. |

## Evidence interpretation and operating constraints

[Model evaluation](MODEL_USAGE_AND_EVALUATION.md) distinguishes 56/60 (93.3%) usable explanation checks from Glimmer's 53.3% fixed-priority goal fit on 60 synthetic coverage-advisor cases; rules reach 100% goal fit by construction and emit no comparison prose. This is not complex-diagnosis accuracy. Narrow agent planning remains rules 90%, Glimmer 86.7%, Llama 53.3%. Retain original scores and failures.

Hosted requests require a fresh eligible promotional-credit observation, a $0.10 reservation per explicit request, $0.20 allowance per observation and $1 persistent local lifetime allowance, with retained reservations after ambiguous failures. These [local guards](safety/FREE_CREDITS.md) cannot enforce provider-wide billing or observe other applications' use. No paid fallback; runtime inference remains Meta-only.

**No videos, recordings, video edits or renders until a new explicit owner request, even after project completion.** Historical video receipts remain historical evidence and do not authorize production. No desktop keyboard/mouse automation. New public content and user interfaces must be English. Hardware/backend/Companion/permission/transaction/recovery implementation remains runtime-owner-owned under the mission split.

[Known limitations](KNOWN_LIMITATIONS.md), [risk register](../RISK_REGISTER.md) and [device scope](../DEVICE_SCOPE.md) preserve the limits of the demonstrated core. Older audit/spec/plan documents and the [README history](README_HISTORY.md) are historical context, not a live backlog. The original Markdown audit describes its audited revision and is not a freshly rerun acceptance report.
