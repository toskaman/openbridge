# OpenBridge

A local device workspace for inspecting facts, understanding permissions and making evidence-backed decisions.

## Current release: read-only device workshop

Working English browser workspace with an explicitly **SIMULATED** fixture and a separate, opt-in **Android USB** inventory. One authorized physical Android phone has been inspected using fixed read-only ADB commands. No device changes or physical Undo are available. Meta Muse Spark 1.3 contributed the visual design; this development use is recorded separately from product runtime inference, which remains disabled. The hackathon's real runtime model-use gate is incomplete.

## Run on Windows

Install Python 3.14.4 from python.org and Git. No third-party runtime packages are required.

```powershell
git clone https://github.com/toskaman/openbridge.git
cd openbridge
powershell -ExecutionPolicy Bypass -File scripts/setup/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/run/run.ps1
```

Open **http://127.0.0.1:18765**. Select **Refresh demo**, then **Inspect evidence**. For a real phone, select **Android USB**, authorize USB debugging on the phone, then select **List USB devices**. Install Android Platform Tools from the official Android developer site if ADB is missing. Ctrl+C stops the server. Use the numeric loopback address; alternate Host values are deliberately rejected.

Cross-platform commands: `python -m unittest discover -s tests -v`, then `python -m src.server`. Optional port: `python -m src.server --port 8766`.

## Boundaries

The server binds exclusively to loopback. Exact Host/Origin validation, a per-process CSRF token, bounded JSON input, fixed static routes and a restrictive browser content policy protect the inspection endpoint. This development server is intended for one trusted local user; it is not an Internet deployment. All device write routes are absent. Android discovery is opt-in; serial numbers stay inside the adapter. Offline and unauthorized devices cannot be inspected.

## Project records

Visual design attribution: **Meta Muse Spark 1.3**, actual request on 26 October 2026. See [design receipt](docs/meta-design-receipt.json) and [English design proposal](docs/visual-meta-proposal.md). Estimated token cost: **$0.01219975**, using promotional credits verified in the Meta dashboard before the supervised call. This is an estimate, not a provider invoice. Runtime cloud inference remains blocked pending a reliable credit-verification path.

See CONTRIBUTIONS.md for origin, DEVICE_SCOPE.md for supported capabilities, EVIDENCE_LEDGER.md for checks, RISK_REGISTER.md for limitations, and docs/safety/BOUNDARIES.md for the runtime model policy. Preparation documents and utilities are maintained separately and are not included as event-built product work.

MIT licensed. Python's standard library and browser-native APIs are the only runtime dependencies.
