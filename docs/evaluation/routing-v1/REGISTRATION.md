# Routing snapshot evaluation v1 — preregistration

Status: frozen before the first scored run. Cases and gold are separate artifacts; hashes are in SHA256SUMS and the freeze commit identifies the registration. No physical or model result is claimed here.

## Question and scope

Does the current deterministic B2 router select the intended eligible relay, respect owner policy, and abstain when appropriate on newly composed synthetic snapshots? This tests existing documented behavior, not new protocols, unseen real networks, or Meta model advantage. The author knows the router and existing fixtures. Exact new case IDs/data are separate from existing fixture files; semantic overlap is deliberate, and model-training independence cannot be established.

32 cases comprise eight template families with four role/transport/age permutations each. The effective family count is eight; permutations are correlated, not 32 independent real environments. Every case has three synthetic nodes and two declared hops (PC transport then relay). Phone/TV/tablet labels are fictional capabilities, not hardware coverage. Synthetic proof ages and clocks are fixed in cases.json; this is not live lease proof.

## Frozen setup and labels

The case declares the final post-condition snapshot, not a physical failure schedule or live failover experiment. Conditions: freshness, offline link, missing control grant or scan permission, owner-disabled relay, stale proof, unavailable PINNED route, PREFERRED override, and all-unavailable abstention. No tie cases or dynamic invocation outcomes are evaluated. The 120-second relay lease comes from the existing B2 contract. Gold aliases and per-candidate unavailable reasons were authored from the case construction, not copied from router output. Gold is never passed to router or baselines.

One final decision is scored per case. An unscored setup snapshot may resolve opaque route IDs before installing PINNED/PREFERRED policy; setup records must be retained. No arming/invocation, device dispatch, scans or hosted/local model calls occur. Selection of an eligible scan route does not imply consent or execution. Full final route documents and events must be retained, including candidate set, reasons, rule, revision, grants and freshness. Invalid output and exceptions remain failures in the fixed denominator.

## Arms

- Router: production skill_routes using an isolated synthetic registry/relay ledger and temporary session storage. No runner/transport is allowed to execute.
- Catalog-first: first node in original case order, ignoring runtime state and policy.
- First-eligible: first eligible node in original case order; checks online, grants, permission, owner enablement and proof age, but ignores owner routing policy.
- Seeded-random eligible: uniform choice among eligible nodes with seed derived from the case ID; none when no eligible node exists.
- Historical-freshest: youngest proof, ignoring current eligibility and owner policy.
- Policy-aware heuristic: independently reads raw case conditions; applies eligibility, PINNED/PREFERRED policy and freshest-proof fallback. This stronger rules baseline is included even if it matches the production router.

Baselines receive original raw node order, never the router's selected-first sorted response. They do not receive gold. All baselines share the same available synthetic input. The router is deterministic policy logic; no result from these arms is evidence for Meta inference usefulness.

## Metrics and reporting

Primary: exact selected-alias accuracy, including correct null abstention, over all 32 cases. Router hits also require a contract-valid final document. Report numerator/denominator, errors and abstention precision/recall (undefined denominators shown as null). Per-candidate unavailable-reason accuracy is a separate deterministic check, never added to selection accuracy or model performance. Report full failures and per-family, selected-device-class and hop-count slices. All slices have n<30 and are indicative only.

Report descriptive 95% Wilson intervals per arm, explicitly noting correlated templates invalidate an independent-trial interpretation; also report eight family-level perfect/not-perfect counts. Do not claim statistical significance. Decision latency p50/p95 measures only the final router call with perf_counter; it includes local state reads and excludes setup. No device-task success rate is defined because no task is executed.

Run identity includes source HEAD, clean/tracked-worktree check, Python/platform, design/cases/gold/harness hashes, UTC time, fixed case ordering, no automatic retry and explicit zero actual hardware/model calls. Refuse execution on changed frozen inputs. Never overwrite a prior run; keep unsuccessful reports. Fixing production behavior after observing cases requires a new separately versioned evaluation; these results stay frozen.

## Meta explanation stage — not executed by this harness

Spark's review must inspect this frozen registration before the first scored run. A later explicit inference stage may explain recorded decisions using only archived fields; it cannot authorize execution. It must freeze its own exact prompt, sampled records, factual citation rubric and request budget before calls. Report unsupported claims and invalid outputs, exact model/version, token/cost receipts and failures separately. Existing promotional-credit guard requires a fresh eligible observation; do not reuse the old balance or substitute a paid provider. No explanation score or model benefit is claimed by the deterministic routing report.
