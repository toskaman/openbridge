# Evidence ledger — 26 October 2026

## Phase 1 local checks

- Python 3.14.4 on Windows: 12 unit/integration tests PASS. Covers fixture provenance, write refusal, unknown device, exact Host, Origin, CSRF, malformed input, oversized body and fixed asset routing.
- `python -m compileall -q src tests`: PASS.
- `node --check src/ui/app.js`: PASS with Node 24.14.1.
- Windows setup and verification scripts: PASS.
- Real Chromium browser: discover fixture → inspect evidence PASS at widths 390, 768, 1440 and 3440. No page exceptions; no horizontal overflow. Before/after screenshots saved locally under ignored artifacts/. Desktop screenshot visually inspected.
- Independent read-only code review: no important phase-one defects identified; required launch/browser checks subsequently completed.
- Running service: http://127.0.0.1:18765. Original proposed port 8765 was occupied by another local listener; it was left untouched.
- Physical devices, real inference, physical transactions and Undo: NOT TESTED / unavailable.
- Ollama service responds, but installed inventory contains no approved Meta model. No installed non-Meta model is invoked by this application.

The 47 preparation-kit tests were also run successfully in their separate private repository. They are not product tests and are not included in the 12 above.

## Reproduce

Run `powershell -ExecutionPolicy Bypass -File scripts/verify/verify.ps1`.
Optional browser check requires externally installed Playwright and Chromium: start the service, then `python tests/e2e/browser_smoke.py`. Browser binaries and optional test dependencies are not bundled.

No model gate, provider identity, hackathon eligibility or physical result is certified by these checks.
