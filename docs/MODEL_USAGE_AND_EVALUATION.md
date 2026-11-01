# Meta model usage and evaluation (runtime)

| Use | Models | Value measured | Result (honest) |
|---|---|---|---|
| Device fact review (grounded summary) | Llama 3.2 3B, Muse Glimmer | real ADB facts, exact values enforced | REAL_HARDWARE_VERIFIED |
| Agent planning (one reversible step) | Llama 3B, Glimmer vs rules | benchmark/STATUS.md | rules 90%, Glimmer 87%, Llama 53% correct; gate refused 100% unsafe proposals |
| Coverage advisor (next discovery step) | Llama 3B, Glimmer vs goal-priority rule | benchmark/advisor-benchmark-*.json | Glimmer 56/60 usable explanations (93.3%), Llama 0/60; goal-priority match: rules 100% by construction, Glimmer 53.3%, Llama 0% |
| Synthetic advisory (cloud) | Muse Spark 1.3 | recorded runtime-core call | runtime-meta-receipt.json |
Safety never depends on the model: gates, allowlists, consent and verification are deterministic. Models see no identifiers; the advisor sees only categories, counts and step ids. Development AI (Codex, Muse Spark design) is never called at runtime (src/ai/registry.py).

## Phase C closing sync (1 Nov 2026; append-only — table above unchanged)

Newer committed results since the 26 Oct rows above; details in
`docs/benchmark/STATUS.md` (Phase C closing sync section):

| Use | Models | Value measured | Result (honest) |
|---|---|---|---|
| Frozen 50-turn local eval (31 Oct) | rules, Llama 3.2 3B, Glimmer 30B | `docs/benchmark/EVAL_SUBSET_50_LOCAL.md` | rules 0/50, Llama 4/50 + 44 clarifications, Glimmer BLOCKED (host OOM, not scored); raw `.xbuild/eval_subset_50.json` stays uncommitted |
| §11 eval-kit rules baseline, 1,000 turns (30 Oct) | rules path only | `docs/benchmark/EVAL_1000_RULES_BASELINE.md` + `eval_1000_rules_baseline.json` | 14/1,000 resolved (1.4%, correctness UNGRADED); 0 crashes / 0 sends; model tiers PENDING |
| V4-04 re-ranking ablation (27 Oct) | rules, Llama 3.2 3B, Glimmer 30B | `docs/benchmark/v4/REGISTRATION.md` + `ablation-20261027T210021Z.json` | top-1: rules 0.833, Llama 0.833, Glimmer 0.722 (8 validator errors); Spark not run; no model arm beat the rules |

Missing / unpublished (explicit): `.xbuild/eval_subset_50.json` is absent by
design (local artifact, never committed); hosted-Spark eval arms not run (no
authorization / supervised budget too small); phone-side §11 acceptance sample
pending. No battery, speed or storage gains claimed.
