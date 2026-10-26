# OpenBridge

A local device workspace for inspecting facts, understanding permissions and making evidence-backed decisions.

## Current release: phase 1

Working local browser demo with one explicitly **SIMULATED** Android fixture, deterministic inspection and evidence provenance. No real devices are accessed or changed. No model is called. Actual Meta inference, Android access and physical Undo are **NOT TESTED** and are not shipped capabilities yet. The hackathon's real-model gate is therefore incomplete.

## Run on Windows

Install Python 3.14.4 from python.org and Git. No third-party runtime packages are required.

```powershell
git clone https://github.com/toskaman/openbridge.git
cd openbridge
powershell -ExecutionPolicy Bypass -File scripts/setup/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/run/run.ps1
```

Open **http://127.0.0.1:18765**. Select **Discover demo device**, then **Inspect device evidence**. Ctrl+C stops the server. Use the numeric loopback address; alternate Host values are deliberately rejected.

Cross-platform commands: `python -m unittest discover -s tests -v`, then `python -m src.server`. Optional port: `python -m src.server --port 8766`.

## Boundaries

The server binds exclusively to loopback. Exact Host/Origin validation, a per-process CSRF token, bounded JSON input, fixed static routes and a restrictive browser content policy protect the inspection endpoint. This development server is intended for one trusted local user; it is not an Internet deployment. All device write routes are absent.

## Project records

See CONTRIBUTIONS.md for origin, DEVICE_SCOPE.md for supported capabilities, EVIDENCE_LEDGER.md for checks, RISK_REGISTER.md for limitations, and docs/safety/BOUNDARIES.md for the runtime model policy. Preparation documents and utilities are maintained separately and are not included as event-built product work.

MIT licensed. Python's standard library and browser-native APIs are the only runtime dependencies.
