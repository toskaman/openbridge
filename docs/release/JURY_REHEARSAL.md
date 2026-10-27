# Internal jury rehearsal

27 October 2026. This is one evidence-based internal self-review using the preparation kit's `JURY_RELEASE_GATES.md` and `ELIGIBILITY_AND_SCORECARD.md`. It is not an official score, actual judge assessment, independent human panel, or simulated claim that twelve experts reviewed the product. The four equal 0–10 ratings below are subjective, provisional practice ratings; the anchors are the preparation kit's internal anchors, not organizer scoring thresholds.

**No release-ready claim.** Final video remains on owner hold and no final video has been produced for this preparation. Portal fields, participant/team eligibility, applicable declarations and organizer acceptance have not been reviewed or completed. Engineering evidence cannot compensate for an unmet submission gate.

## Gate review before scoring

| Gate | Evidence available | Current bounded assessment |
|---|---|---|
| Problem/theme fit | README and capability/service workflow describe consented device interoperability | Plausible fit; exact final chosen official statement/track and 12-second formulation need participant review. |
| Actual Meta inference in product | `docs/glimmer-smoke-receipt.json`, `docs/forge/tv-glimmer-live-receipt.json`, `docs/runtime-meta-receipt.json`; pinned identities in `config/runtime_models.json` | Recorded product inference exists, distinct from build-time theme generation. No fresh inference performed for rehearsal. |
| Meta-only runtime | Registry/config, broker boundary tests and `tests/unit/test_meta_only_network_trace.py` | Tested paths support declared policy. Socket interception does not establish complete OS/process/runtime egress coverage; see `THREAT_REVIEW.md`. |
| Provenance, rights and public source | `CONTRIBUTIONS.md`, `THIRD_PARTY.md`; anonymous public baseline clone in `OFFLINE_REPLAY.md` | Evidence exists; final public revision, exact artifact/service terms and participant declarations still require review. |
| Accessible final <=180-second demo | Historical stills and journey receipts exist | NOT ASSESSED: final video on owner hold. No video generated. |
| Portal/team/submission | `SUBMISSION_EVIDENCE.md` records unknown fields | NOT ASSESSED; no submission or acceptance claimed. |

## Four-category provisional practice ratings

| Category | Internal rating | Verified basis | Why the ceiling remains lower |
|---|---:|---|---|
| Impact | **5/10** | Real TV BLE observation to narrow published/read/revoked service journey is documented in `docs/forge/TV_GLIMMER_JOURNEY.md` and its raw live receipt. The workflow addresses a concrete interoperability/consent problem. | Real-user demand, beneficiary counts, time saved, battery/performance gain and measured before/after value are not proven. Correct safe operation is not a quantified impact study. |
| Meta AI Tooling | **7/10** | Product has actual local Glimmer/Llama and recorded hosted synthetic advisory evidence; model identity/digest, token/latency fields and effect on a gated proposal are recorded. Synthetic ablations and unfavorable findings are retained in `docs/benchmark/STATUS.md`. | Existing historical benchmarks have limited synthetic scope; new model benchmark results are still running and are not scored here. No invented model advantage, general reasoning superiority or measured unique capability is assumed. Rules remain material baselines and authorization stays deterministic. |
| Technical Depth & Execution | **7/10** | Trusted source binding, permission/provenance checks, read-time revalidation, bounded service lifecycle and controlled failure tests exist. Fresh anonymous baseline clone plus isolated venv passed 70 Forge tests with two skips (`OFFLINE_REPLAY.md`). Independent concurrency review found lifecycle flaws and root reports failed-first regressions then eight focused passes. | Final integrated commit replay is pending. Same-PC clone is not a separate machine. Browser/native egress, broad load testing, full accessibility audit and cross-platform independent installation are not proven; new workspace flow has no new full physical proof. |
| Demo | **4/10** | Historical end-to-end receipts and still screenshots support a working prototype story, with unsuccessful attempts disclosed. The real journey records 82.4-second model proposal latency, which must be explained honestly. | Rating covers current demonstration material only. Final <=180-second accessible video, unaided jury replay, final narration/story and portal demo compliance remain NOT ASSESSED. Owner hold prevents any readiness conclusion. |

Provisional arithmetic: **23/40**. This is a practice snapshot, not predicted ranking, acceptance probability, official grade or a target already achieved. Unknown mandatory gates remain unknown independently of this number. Final-video quality itself has no rating yet.

## Evidence a skeptical reviewer should inspect

- Trace actual proposal input/output and deterministic decision effect in the Glimmer receipt; distinguish synthetic observations, actual device observations and development-only Meta theme contributions.
- Replay baseline software commands, then inspect root's final integrated replay when available. Preserve skipped tests, failed-first regression evidence and resource/security limitations.
- Read historical benchmark failures and baseline definitions before repeating a percentage. Pending benchmark outputs must be reviewed before this document's model assessment changes.
- Confirm current permissions, publication/read denial and removal semantics from controlled tests; historical physical journey does not prove every new workspace boundary.
- Complete a real impact study before claiming optimization: comparable repeated baseline/change/revert measurements, context, spread, redacted identity and negative/neutral outcomes.
- Participant completes portal, team/track, rights and final-video decisions. No action in this rehearsal submits the project or authorizes new device/model calls.
