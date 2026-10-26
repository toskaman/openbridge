# Jury acceptance — Device Fabric

Reproduce without hardware: `python -m unittest discover -s tests`, `python -m tests.e2e.offline_smoke`, `python -m tests.e2e.guided_smoke`, `python -m tests.e2e.fabric_smoke` (all in CI).
With hardware: `python -m src.server --local-meta --agent` (add `--glimmer` for Muse Glimmer), open http://127.0.0.1:18765, "Discover my environment", inspect a device sheet, "Ask Meta what to do next", then the agent panel for a consent-gated reversible change and exact Undo.
Claims are limited to EVIDENCE_LEDGER.md and HARDWARE_TEST_MATRIX.md statuses.

Finish with **Finish session…** to see and restore every setting OpenBridge changed. Add `?redact` to the URL to hide household device names.
