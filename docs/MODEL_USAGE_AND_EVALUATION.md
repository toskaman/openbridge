# Meta model usage and evaluation (runtime)

| Use | Models | Value measured | Result (honest) |
|---|---|---|---|
| Device fact review (grounded summary) | Llama 3.2 3B, Muse Glimmer | real ADB facts, exact values enforced | REAL_HARDWARE_VERIFIED |
| Agent planning (one reversible step) | Llama 3B, Glimmer vs rules | benchmark/STATUS.md | rules 90%, Glimmer 87%, Llama 53% correct; gate refused 100% unsafe proposals |
| Coverage advisor (next discovery step) | Llama 3B, Glimmer vs goal-priority rule | benchmark/advisor-benchmark-*.json | Glimmer 56/60 usable explanations (93.3%), Llama 0/60; goal-priority match: rules 100% by construction, Glimmer 53.3%, Llama 0% |
| Synthetic advisory (cloud) | Muse Spark 1.3 | recorded runtime-core call | runtime-meta-receipt.json |
Safety never depends on the model: gates, allowlists, consent and verification are deterministic. Models see no identifiers; the advisor sees only categories, counts and step ids. Development AI (Codex, Muse Spark design) is never called at runtime (src/ai/registry.py).
