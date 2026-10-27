# Capability Forge integration preview

Worktree branch: feat/capability-forge. Review: https://github.com/toskaman/openbridge/pull/1 (draft; no main merge).

Run `python -m src.forge.demo_host`, then open http://127.0.0.1:18766. The page is entirely SIMULATED and starts with no configured model. Explicitly select Rules for the demonstrated workflow. Refresh the simulated fixture if it expires, request a plan, approve publication, build, test, inspect the contract and remove the service.

Optional `--glimmer` uses the existing pinned local Meta service. Current Forge Glimmer attempts failed due resource/projector loading constraints; the default preview never falls back to cloud. The 64-case Llama run accepted no complete plans. See MODEL_ABLATION_RESULTS.md. Rules remain authoritative for this task. Local provider charges were $0.

Tests: `python -m unittest discover -s tests -q` (202 passing on the delivery check), then `python -m tests.e2e.forge_smoke` after installing the repository's pinned browser-test requirements and Chromium. No hardware or provider is needed for these tests. Optional jsonschema 4.26.0 enables full standalone schema validation and is installed by Forge CI.

Start with CAPABILITY_FORGE_ARCHITECTURE.md, CAPABILITY_FORGE_API.md and CAPABILITY_FORGE_SECURITY.md. INTEGRATION_HANDOFF.md identifies the v1 bridge and outstanding true per-fact timestamp/authenticated hardware gates. The source/compiler/client path works over real loopback HTTP with synthetic observations; actual remote TV/beacon publication is not yet proven.

DEMO_VIDEO.json describes the 170-second English-captioned fallback recording. It is a preview, not a final hackathon submission or proof of successful Glimmer planning.
