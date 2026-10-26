# OpenBridge

A local device workspace for inspecting facts, understanding permissions and making evidence-backed decisions.

## Current release: read-only device workshop

Working English browser workspace with an explicitly **SIMULATED** fixture and separate, opt-in **Android USB** and **Freebox gateway** sources. One authorized physical Android phone has been inspected using fixed read-only ADB commands. No physical device changes or physical Undo are available. A separate **SIMULATED change & Undo** sandbox demonstrates durable snapshots and exact restoration without accessing hardware. Meta Muse Spark 1.3 contributed the visual design; this development use is recorded separately from an actual supervised runtime-core inference on synthetic facts. Default startup keeps cloud requests disabled. Physical actions and Undo remain unavailable.

## Run on Windows

Install Python 3.14.4 from python.org and Git. No third-party runtime packages are required.

```powershell
git clone https://github.com/toskaman/openbridge.git
cd openbridge
powershell -ExecutionPolicy Bypass -File scripts/setup/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify/verify.ps1
powershell -ExecutionPolicy Bypass -File scripts/run/run.ps1
```

Open **http://127.0.0.1:18765**. Select **Refresh demo**, then **Inspect evidence**. For a real phone, select **Android USB**, authorize USB debugging on the phone, then select **List USB devices**. Install Android Platform Tools from the official Android developer site if ADB is missing. **Freebox gateway** reads public identity only; it does not pair or access router settings. **View recorded Meta proof** displays the previous verified runtime-core call without making another request. Ctrl+C stops the server. Use the numeric loopback address; alternate Host values are deliberately rejected.

Cross-platform commands: `python -m unittest discover -s tests -v`, then `python -m src.server`. Optional port: `python -m src.server --port 8766`.

## Boundaries

The server binds exclusively to loopback. Exact Host/Origin validation, a per-process CSRF token, bounded JSON input, fixed static routes and a restrictive browser content policy protect the inspection endpoint. This development server is intended for one trusted local user; it is not an Internet deployment. All device write routes are absent. Android discovery is opt-in; serial numbers stay inside the adapter. Offline and unauthorized devices cannot be inspected.

## Project records

Visual design attribution: **Meta Muse Spark 1.3**, actual request on 26 October 2026. See [design receipt](docs/meta-design-receipt.json) and [English design proposal](docs/visual-meta-proposal.md). Estimated token cost: **$0.01219975**, using promotional credits verified in the Meta dashboard before the supervised call. This is an estimate, not a provider invoice. A separate [runtime receipt](docs/runtime-meta-receipt.json) records a real Muse Spark 1.3 advisory call through the application broker, estimated at **$0.00335475**. The interface can display this explicitly recorded proof without spending credits. Live requests require a fresh supervised free-credit observation and conservative durable reservations; see [free-credit operation](docs/safety/FREE_CREDITS.md). A live browser-to-provider session is not claimed.

The simulated recovery sandbox records its snapshot before mutation, verifies read-back, and restores the exact original value. It survives page reloads and refuses external conflicts. See [simulation receipt](docs/simulated-transaction-receipt.json). This is not physical-device rollback evidence. Reproduce the core simulation with `python -m dev.transaction_smoke`; the private journal stays outside Git.

See CONTRIBUTIONS.md for origin, DEVICE_SCOPE.md for supported capabilities, EVIDENCE_LEDGER.md for checks, RISK_REGISTER.md for limitations, and docs/safety/BOUNDARIES.md for the runtime model policy. Preparation documents and utilities are maintained separately and are not included as event-built product work.

MIT licensed. Python's standard library and browser-native APIs are the only runtime dependencies.

## Controlled physical-write status

An isolated, explicitly opted-in verifier exists for one authorized USB phone's screen timeout. The tested phone **rejected the write**. The exact original value was independently read back and preserved; no successful physical change or physical Undo is claimed. See [recorded blocked attempt](docs/physical-transaction-attempt.json).

The web interface remains physically read-only, even if a physical engine is accidentally supplied to its simulated sandbox route. Do not retry the physical verifier without reviewing the existing evidence and the device's normal authorization. It never roots a phone or bypasses protected consent. Recovery-only mode can inspect/restore an interrupted journal without initiating a new change: `python -m dev.physical_transaction_smoke --confirm-owned-device --recover-only`.

## Live Android connection updates

Selecting **Android USB** starts a local ADB event stream. Plugging in, unplugging or authorizing a device refreshes the redacted inventory without periodic device polling. Switching sources closes the stream; manual listing remains available if tracking fails. Connection changes invalidate pending inspection results so stale device evidence is not displayed as current.

Tracking uses an owned `adb track-devices` subprocess, starts only with an opted-in subscriber, and shuts down when subscriptions end. It sends no device data to a model and triggers no writes. An offline emulator may appear separately from USB phones; its transport label identifies it explicitly.

## Optional browser verification

Runtime needs no third-party Python packages. For the pinned browser-test environment, run `python -m pip install -r requirements-dev.txt`, then `python -m playwright install chromium` and `python -m tests.e2e.offline_smoke`.

This isolated check starts its own temporary server and synthetic journal. It verifies the English interface, recorded model proof, simulated change/reload/Undo and missing-device guidance at four widths. Hardware responses are controlled and no provider calls are made. The same check runs in the Linux CI browser job; unit/integration tests run on Windows and Linux.

## Evidence walkthrough preview

A captioned English preview is available with the [alpha.2 release](https://github.com/toskaman/openbridge/releases/tag/v0.1.0-alpha.2). It is 177 seconds, 1080p/30fps, intentionally silent, and records actual application interactions. Its [public manifest](docs/jury/DEMO_PREVIEW.json) pins the captured source revision and states which evidence is recorded or simulated. This is a preview, not a final contest submission.

## Optional local Meta reasoning — Built with Llama

`python -m dev.start_local_meta --pull-model` starts a separate CPU-only Ollama service on 127.0.0.1:11437 with a private model directory and pulls Meta **Llama 3.2 3B Instruct** (`llama3.2:3b-instruct-q4_K_M`, manifest digest `a80c4f17…b8b72`, ~2 GB). Then run `python -m src.server --local-meta` (or `run.ps1 -LocalMeta`). Your existing Ollama service is left untouched.

The digest is verified before every call; unknown or retagged models fail closed, and there is no cloud fallback. After inspecting an authorized Android phone, **Request Meta advice** sends only allowlisted numeric facts (battery, free storage, screen timeout), re-read by the server, to the local model. Output is schema-checked English advice with `inspect_only` action; it cannot change the device. A recorded CPU call on synthetic facts is in [docs/local-meta-smoke-receipt.json](docs/local-meta-smoke-receipt.json) (8.4 s, 211 tokens, $0). A local call on real ADB facts is **NOT TESTED** yet.

Llama 3.2 is licensed under the Llama 3.2 Community License, Copyright © Meta Platforms, Inc. Model weights are not included in this repository.
