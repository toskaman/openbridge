# Capability Forge

Forge turns approved relay observations into a consent-gated local read service. Planning proposes a path; deterministic provenance, freshness, permissions and schema checks decide whether it is usable. Publication verifies the first read. Removal remains available during pending planning or model-memory operations.

## Run locally

Run `python -m src.forge.demo_host`, then open http://127.0.0.1:18766. The default is an explicitly SIMULATED fixture with no configured model. Select Rules to exercise the offline workflow: refresh fixture, plan, approve publication, build, read, inspect the contract, then remove. Evidence expires after 120 seconds.

For the isolated CPU Muse Glimmer v2 service, use `python -m dev.forge_glimmer_cpu_service` and `python -m src.forge.demo_host --glimmer-cpu-v2`. Model preparation/release is under **Local planner memory**. No inference starts on page load, and there is no automatic model or cloud fallback.

## Evidence and limits

- [Physical TV journey](TV_GLIMMER_JOURNEY.md): actual local Muse Glimmer proposal, verified publication/read, revocation refusal and removal. Recorded hardware evidence does not imply current device availability.
- [Original model ablation](MODEL_ABLATION_RESULTS.md): retain narrow-task failures and rules baseline; do not present the development proofs as new benchmark scores.
- [Historical integration handoff](INTEGRATION_HANDOFF.md): provider interface evolution. Use [current release status](../RELEASE_STATUS.md) for delivered integration and open gates.
- [Meta website receipt](meta-web-design-receipt.json): Muse Wonder 1.0 authored the current theme foundation. Codex authored markup adaptation, integration and checks. The complete CSS fields were retained; the final explanatory note was truncated.

Forge foundation, verified publication and TV proof were merged through PRs #1, #10 and #14. The redesign is tracked in PR #20. Historical recordings remain historical artifacts; no further videos may be created without a new explicit owner request.

## Verify

`python -m unittest discover -s tests -q` passed 314 tests after syncing main on 27 October 2026. Browser checks require the pinned development requirements and Chromium. Run the `tests.e2e.forge_*` modules for lifecycle, failure recovery, expiry, injected-source labels, model memory and concurrent revocation. These controlled tests make no actual hardware or model requests.

Theme sources live in `src/ui/theme/`; run `python -m dev.build_web_theme` to compile both existing asset routes, and `python -m dev.build_web_theme --check` to detect drift. Main device discovery and Forge share the foundation without new backend asset routes or external fonts.
