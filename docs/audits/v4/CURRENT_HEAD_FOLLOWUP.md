# Current-head follow-up: agent scaffold and proposed substrate

This extends, rather than rewrites, the [baseline audit](REPORT.md). Inspected merged agent head: `c426496a1305584ccf73b023ce9227099a73b55d` (PR71). Inspected **unmerged** substrate PR72: `8a73b8f395ecf13a979f88fd93649cd3975b3f23`. [Machine observations](current-head-receipt.json); executable source: `dev/audit_v4_followup.py`, committed `2787d4e`. No provider, credentials, physical device, install, capture or actual spend was used.

**Verdict remains BLOCKED.** The agent scaffold now exists; it is incorrect to describe all V4 agent implementation as absent on this newer revision. However, a connected, trusted, physically verified novel-capability pipeline is still not established.

## What changed since the baseline

PR71 adds eight source modules and24 pure fixture tests for evidence, gap detection, synthesis, UI, workflow, Meta transport and provenance. Imports/call-site inspection found these modules referenced within the new layer and its tests, not wired into the current runtime API/Command Center path. No new actual inference, signed staged deployment, before/after unknown-target registry delta or V4 physical acceptance is claimed by the audit.

PR72 proposes the missing native contract/kernel, registry and UI bridge. It has not been merged into the audited agent head and was inspected from immutable Git objects. Its canonical schema is `obv4.1` with `steps`, nested target/fingerprint, signed facts and model_run, while the agent emits its own version1 candidate using primitive_chain, target_opaque_id and model_run_id. Primitive IDs and UI shapes also differ. A reviewed interface adapter/contract handshake is required before generation calls; avoid competing kernels or pretending the schemas already interoperate.

## New substrate findings â€” PR72 HOLD

### V4-S4 / P1: concurrent operation replay consumes the grant twice

`src/substrate/kernel.py299â€“311` checks operation_id under one lock, releases it for compile, then consumes a grant and records the operation under another lock without rechecking replay. Two identical concurrent requests with a legitimate multi-use grant both proceed.

The upgraded retained reproduction uses **actual PR72 InvokeRequest/Grant schema validation**, actual invoke/_check_grant/HMAC and fixture-derived valid records. Compilation, device lookup and execution are explicitly mocked to isolate the admission race; this is not a complete real compile/physical pipeline claim. Result:2 fake effects,2 grant uses, no errors for one operation ID. The peer's earlier source-extraction proof had stubbed schema validation; the retained upgraded proof does not.

**Claude fix:** atomically recheck/claim operation identity in the same admission section as grant consumption. Preserve contract-defined replay refusal or prior-receipt behavior and uncertain-outcome semantics. **Test:** simultaneous same ID with max_uses>1 results in one effect/use; distinct IDs remain executable within their grant.

### V4-S5 / P2: signed facts survive verification/source downgrade

`src/substrate/kernel.py110â€“122` checks signature, target, age and current value, but ignores verified and current source/trust state. The actual Fact schema permits verified:false. Current facts() can sign unverified observations; signing authenticates origin, not truth or permission to rely on it for execution.

Actual schema/signature/fact-checker probes accept (a) an earlier verified fact after same-value current evidence becomes verified:false/source UNKNOWN, and (b) a legitimately signed unverified fact. Identity lookup/current-fact production are mocked and disclosed; the downgraded current fact is signed with the fake test key. No real device observation is asserted.

**Claude fix:** restrict execution evidence to trustworthy verified facts and recheck current provenance/verification/freshness, not only value. Preserve unverified observations for explicitly labeled inspection/proposals where appropriate. **Test:** same-value downgrade and signed-unverified input both refuse execution evidence.

## Merged agent findings and interface actions

### V4-M1 / P2: grounding inputs and candidate checks are incomplete

`v4_synthesize.build_prompt` sends only a bundle digest, primitive names, category and intent. It does not send actual evidence references or target IDs; `v4_evidence.resolve` also drops raw fact values. A digest cannot give the model the IDs it is required to cite, and no retrieval-tool loop is implemented here. Hardcoded mock candidate IDs in unit tests do not prove a real model can ground this prompt.

The existing synthesize path accepts a mock candidate with a foreign target, invented evidence reference, extra untyped input and expanded grant declaration if its primitive ID is listed. This is a **proposal-integrity gap**, not proof of privileged kernel escape or actual hardware execution. Muse should provide an approved bounded evidence projection, use canonical schema/identity references and require the independent native compiler before staging; do not duplicate trusted authorization logic inside the model layer.

### V4-M2 / P2: the new transport factory does not enforce Meta identity

`v4_metaclient.ollama_transport` accepts an arbitrary configured model/endpoint and drops the returned model identity; MetaClient accepts its text/usage. A fake opener returning a non-Meta envelope is accepted by this code. No actual non-Meta inference or network request was made. This unwired factory must reuse the existing pinned Meta-only registry/digest/endpoint/response checks before becoming a runtime provider. Unknown tier refusal alone is not a model identity check.

### V4-M3 / P2: registry digest misses mapping/version changes

`v4_evidence.registry_digest` hashes skill IDs and primitive names only. Changing an existing skill's action mapping and version leaves the digest unchanged, as reproduced. resolve() currently returns an empty registry_digest field as well. Before/after causal attribution requires canonical versioned descriptors, parameters, permissions and mappingsâ€”not just name membership. The audit's full baseline registry digest remains a separate, stronger recorded snapshot.

### Baseline fairness

The new RulesPlanner always abstains and does not consult prebuilt skill mappings. It is a transparent placeholder, not yet a complete fair control for tasks achievable by the existing deterministic library. Freeze a competent no-Meta baseline with identical evidence, registry, executor and intervention limits. An always-abstain control must not manufacture a novelty advantage.

## Current validation and limits

The retained current-head receipt reports zero actual provider/hardware calls and zero spend. It preserves both isolated kernel findings and source-only agent observations. Source hashes/heads identify what was inspected. Existing command-cache and explanation freshness/accounting findings remain applicable because those files are unchanged between baseline dcf8527 and merged c426496.

The current full suite passes630 methods (exit0,42.306s), including24 added scaffold tests and7 audit methods total. [Redacted output](CURRENT_TEST_OUTPUT.txt), [current-head CI records](CURRENT_CI.json) and [source/command provenance](CURRENT_PROVENANCE.json) are retained. The complete PR72 suite was NOT_RUN here; its admission/trust methods were isolated against actual schema validation. Green tests show that the collectors and covered behavior run, not that the security findings are fixed. The CLI returns2 for blocked findings.

G1 is now **proposed contract under review**, not a frozen compatible interface. G2 remains NOT_FROZEN; G3â€“G8 novelty/physical claims remain unestablished or not run. Do not publish private held-out gold to either generator; do not select already-tuned physical tasks and call them unseen. Owner-approved physical scope and fresh model/disclosure/budget evidence remain later gates. No protected master documents or frozen experiment bytes were changed.

## Handoff

- Claude: V4-S1 from the baseline plus V4-S4/S5; preserve exact owner identity/consent and address operation ownership/trust before live manifests.
- Muse Code: agree obv4.1 interface, address M1â€“M3 with evidence-grounded prompts and pinned providers, connect proposal to native compile without auto-approval, and replace the placeholder ablation with a fair control.
- Evaluation-tool author: S2/S3 in a new runner revision; original approved eight-call negative result remains unchanged. PR73 still retains those runner properties at ea22de2.
- Sol: review revised immutable heads, run independent negatives and only freeze genuine held-out facts/oracle after the shared interface and supported target exist. No current release clearance is granted.

## Reproduce without effects

Fetch the exact audited Git objects first (`git fetch origin` and, for a fresh clone, `git fetch origin refs/pull/72/head`). Verify the audited commit8a73b8f is available; do not substitute a changed PR head. On the audit branch, run `python -B -m dev.audit_v4_followup --output artifacts/new-v4-audit.json`. It refuses an existing output path and returns2 for the retained blocked observations. Do not run provider or physical actions to reproduce these source-level findings.

## Source-guard follow-up

The guarded auditor atd945edb verifies all eight agent source files and the PR72 schema helper before probing, and extracts kernel/contract/fixtures from the immutable PR object. A failed-first source-mismatch regression passes. [Guarded receipt](current-head-receipt-guarded.json), [latest631-method output](GUARDED_TEST_OUTPUT.txt) and [guarded provenance](GUARDED_PROVENANCE.json) retain the new run. Earlier630-method output and receipt remain unchanged. The blocked observations reproduce with zero provider/hardware calls. See [additional upstream context](UPSTREAM_CONTEXT.md) for explanation-v2 preparation.
