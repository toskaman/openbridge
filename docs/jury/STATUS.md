# Demonstration status

**Verified on real hardware (one owned Android phone, Windows PC):**
- Read-only ADB inspection, live connection events, Freebox public identity (read-only second protocol).
- Real in-product Meta inference: pinned local Llama 3.2 3B (CPU, digest-verified) reviews real ADB facts; summaries must state exact values. Cloud Muse Spark 1.3 runtime-core call on synthetic facts (recorded).
- Physical reversible change with exact Undo: one allowlisted optional app disabled for user 0 and restored to its exact original Android enabled-state code, independently confirmed with dumpsys (docs/physical-package-receipt.json).
- Verifiable agent loop in the browser: observe -> Meta plan -> deterministic gate -> owner consent -> act -> independent read-back -> exact Undo (docs/agent-loop-receipt.json).
- Product-enforced Meta-only runtime registry.

**Simulated and labeled:** demo fixture and the persistent change/Undo sandbox.

**Not yet verified:** Muse Glimmer inference (download in progress; route fails closed until digest pinned), model benchmark results, multiple phones, physical unplug during a write, clean-machine reproduction, final video and submission. No bonus eligibility or organizer acceptance is claimed.

The earlier screen-timeout write was refused by Android; that refusal record stays published.
