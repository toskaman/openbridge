# Release evidence publication — 27 October 2026

Integration base: `437dfa3` (published main). This release contains documentation/evidence and preserves the existing diagnosis CSS in the maintained theme source. No protected runtime, adapter, Companion or permission implementation was edited.

Fresh local verification on this base plus the stated changes:

- `python -m unittest discover -s tests -q`: 441 tests passed in 35.322 seconds. One ResourceWarning reported an implicitly cleaned HTTPError; no test failed.
- `python -m compileall -q src dev tests`: passed.
- Initial `python -m dev.build_web_theme --check` failed because diagnosis CSS existed only in the generated asset. Moved the same rules into main-legacy.css, regenerated assets, and the check passed. Meta-authored modules were unchanged.
- `tests.e2e.forge_workspace_smoke`, `tests.e2e.forge_smoke`, `tests.e2e.fabric_smoke`, `tests.e2e.agent_portal_smoke`: passed at 390/768/1440/3440, using the existing Playwright cache on the participant PC. Controlled fixtures; no hardware/model calls.
- `python -m unittest tests.forge.test_benchmark_v2 -q`: 14 passed.
- Canonical Rules CLI: 80/80, zero inference. Published Llama/Glimmer receipts were collected earlier, not rerun; their recorded component hashes match the Rules run.
- All six published evaluation JSON receipts parsed; SHA256SUMS and frozen dataset/source hashes checked. Targeted credential/private-address pattern scan returned no matches. This is not a formal privacy certification.
- `git diff --check`: passed. Windows line-ending normalization warnings are not content failures.

Historical anonymous ec653af replay and physical workspace receipts are published separately with their original revisions. They do not establish the outcome of later runtime additions. CI on the PR remains separate evidence. No new hosted inference, hardware operations, videos or keyboard/mouse automation were performed in this publication milestone.

Remaining gates: Claude runtime review/acknowledgement, final participant eligibility/declaration review and authenticated submission receipt. Future V7 features require their own contracts, implementation and physical proof. No final contest submission or full accessibility certification is claimed.
