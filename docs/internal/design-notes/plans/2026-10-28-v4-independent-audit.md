# V4 independent audit plan

**Goal:** Audit current implementation and preserve independent causality/security evidence without changing the platform, generator, protected documents or frozen experiments.
**Architecture:** Read-only source/registry inventory plus temporary, deny-network adversarial probes. New audit reports stay separate from production claims. Public development fixtures are not held-out hardware gold.
**Stack:** Python stdlib, existing contracts/compiler, unittest, Git/CI read-only metadata.

- [x] Read V4 roles, official owner guide, requirements and current main/CI.
- [x] Trace prebuilt registry, Forge output space and generated status formatter.
- [ ] Add independent audit tool and development-only tests; reproduce dispatch race with real Executor/fake runners and credit-policy behavior with temporary SQLite only.
- [ ] Record source/registry digests and hashes, full probe observations, exact commands/results, kit-spec counts vs executed tests.
- [ ] Write causality and G0–G9 gates, narrow remediation handoffs and no-Meta baseline protocol.
- [ ] Preserve genuine held-out case selection as BLOCKED until independently observed owned target, frozen primitive contract and private oracle exist. Do not publish or invent held-out gold.
- [ ] Independently review reports/tool; run existing/focused tests without hardware/model calls.
- [ ] Publish reviewable audit artifacts on an audit branch; no final release, protected-document edits, deployments or source-core patches.
