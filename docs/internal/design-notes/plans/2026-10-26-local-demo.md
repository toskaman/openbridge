# Local demo implementation plan

**Goal:** Start an honest, reproducible local simulation without device access.

**Architecture:** Python standard-library HTTP server, isolated simulated adapter and deterministic policy, static HTML/CSS/JavaScript UI.

**Tech stack:** Python 3.14.4; browser native JavaScript; unittest; optional Playwright for browser verification.

1. Create tests/unit/test_policy.py and tests/integration/test_http.py. Run `python -m unittest discover -s tests -v`; observe missing application failures.
2. Create src/adapters/simulated.py, src/core/policy.py and src/server.py. Return simulated facts; deny all writes. Enforce host/origin/token checks. Re-run the tests until green.
3. Create src/ui/index.html, style.css and app.js. Discover and inspect through the protected API. Show simulation and inference-unavailable labels persistently.
4. Create Windows run/setup/verify/build scripts, documentation, contribution ledger, license and CI. Compile and run all tests.
5. Launch service, inspect browser behavior at 390 and 1440 pixels, capture actual screenshots, verify a clean clone, commit and push the fresh public repository.

All source is authored fresh after participant-confirmed start. Preparation utilities stay outside this repository.
