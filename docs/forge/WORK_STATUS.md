# Release-readiness checkpoint — 27 October 2026

Branch: `codex/release-readiness`, based on merged main `715da96`. Frozen v2 evaluation committed before inference: `cc6cca4`, then LF byte-hash normalization `fdf9922` (no case/gold changes). Dataset SHA: `693658da1da548ef39d3082db9e2447baa06be5885f30aadc5a239ec65c502b8`.

## Constraints

English throughout. No desktop keyboard/mouse automation. No videos, recording, edits or rendering until a new explicit owner request, even after completion. Meta-only runtime; no paid cloud fallback or automatic retry. New cloud calls require freshly eligible credit observations. Preserve protected main server, physical adapters, Companion, permissions, transaction and recovery source.

## Completed in this release branch

- Windows portal translated, including dynamic/copy/error states and document language; fixed hidden metrics display. Mocked four-width browser verification passed.
- Reconciled stale hardware/integration/status documents; 12 historical README links repaired. Model/third-party attribution and metadata review added, without redistributing weights or claiming legal clearance.
- Separate trusted runtime selector implemented in `src/forge/workspace.py`, launched by `python -m dev.start_workspace`. Main UI links to :18767; main remains :18765. It lists only current verified source-bound observations, requires an explicit short-lived candidate selection, and opens a bounded per-source Forge host. No automatic scan, model request, grant or publication. Default rejects simulated providers.
- Independent source review found selection-lock and late-publication races. Failed-first regressions now cover pending capacity, closure during source initialization, late publication, stalled reads and terminal per-service stop. Bound Stop is terminal: select a new workspace to publish again. In-flight trusted I/O cannot be forcibly cancelled, but its late result is denied and cannot republish. Existing simulated fixture lifecycle remains reusable.
- Seven diagnostic tests passed before one newly authorized Muse Spark call. Successful fixed synthetic diagnostic: 349 input / 2,999 completion tokens, 10,817 ms, estimated $0.013182 promotional cost; $0.10 retained reservation. `spark-diagnostic-success.json` records non-authorizing hypotheses/checks. Earlier blocked attempt retained; no automatic retry. Observation now must not be silently refreshed for further calls.
- Current 80-case evaluation froze 40 development/40 heldout cases across 16 categories. Rules: 80/80; Llama v2: 25/25 actual constrained proposals accepted. Other eligibility/scope outcomes are deterministic and not credited to model reasoning. CPU Glimmer comparison is in progress; no superiority claim or replacement of v1 scores.
- Anonymous public baseline clone and fresh same-PC venv replay: 70 Forge tests, two explicit skips, no forbidden I/O attempts. Final new-source replay remains to run after commit.
- Submission worksheet, provisional internal four-category rehearsal and bounded threat review prepared. Unknown human/portal fields remain unknown.

## Running services

`dev.start_workspace --glimmer-cpu-v2` serves main :18765 and selector :18767 from this worktree. It has no hosted broker; main agent remains disabled unless explicitly started with local Meta/agent flags. Existing :18766 remains the independent SIMULATED contract preview. CPU Glimmer :11439 is used by the explicit local evaluation. Do not stop unrelated model services. Only loads created by this evaluation may be released.

## Next

Finish Glimmer run and preserve raw outputs, execute optional authorized physical selector verification without another model call, run final guarded committed-source/browser/clean-environment replay and CI, publish/merge with exact evidence, and save a final checkpoint. Submission is not complete until required portal information and owner review exist; video remains on hold.

Historical physical TV/Glimmer proof remains [TV_GLIMMER_JOURNEY.md](TV_GLIMMER_JOURNEY.md). The older 64-case v1 ablation and failed attempts remain unchanged. See [release status](../RELEASE_STATUS.md) and [submission worksheet](../release/SUBMISSION_EVIDENCE.md).
