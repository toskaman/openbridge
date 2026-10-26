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

## Read-only expansion and English interface

- 20 unit/integration tests PASS on Windows, including opt-in ADB inventory, no simulated fallback for failed physical inspection, unknown handles, unauthorized devices, timeouts and private identifier redaction.
- Actual Meta development request: muse-spark-1.3, returned identity matches; 267 input tokens and 2,792 output tokens, estimated cost $0.01219975 at the published standard rates. Free promotional credits were observed active immediately before this supervised call. See docs/meta-design-receipt.json.
- Entire interface and public project documentation are English. The original model proposal was translated editorially; no additional Meta call is claimed for that translation.
- Chromium tests PASS at 390/768/1440/3440 for demo inspection, explicit USB source, English language declaration, no overflow, and stale-card removal after discovery failure.
- One real authorized USB phone was inspected through the adapter. Facts came from fixed getprop, dumpsys battery and df commands. No writes occurred. Private serials and device measurements are not committed.
- Gateway identification returned Freebox Server API 16.1 through the documented local discovery endpoint. No credentials, authenticated router access, router writes or subnet scans were used.
- Windows and Linux CI passed for phase 1. The current expansion still requires a new CI run after push.
- Shipped HTTP runtime model calls remain disabled. Visual design assistance is not a substitute for an actual product inference trace.

## Guarded runtime core and Freebox public discovery

- 40 unit/integration tests PASS on Windows, including concurrent budget reservations, durable limits, model identity/schema checks, physical-data refusal and public Freebox discovery redaction.
- Actual supervised runtime-core call to Meta Muse Spark 1.3: 110 input tokens, 757 output tokens, estimated cost $0.00335475. Returned identity and evidence refs passed broker checks; action was inspect_only. See docs/runtime-meta-receipt.json. The participant confirmed active promotional credits before this request. No private physical facts were sent.
- The public Freebox identity endpoint responded with API 16.1 through the actual adapter. Its UID, local address, private API domain and custom name are excluded from returned evidence. No pairing, credentials, configuration or writes were used.
- Chromium source-selection and overflow checks PASS at 390/768/1440/3440. A separate mocked Meta UI test verifies one pending request, stale-result discard and credit-expiry feedback. Those mocked tests consume no provider credits.
- The browser defaults to blocked live inference. Recorded-proof display is explicitly historical and makes no model request. Live browser/provider execution remains NOT TESTED.
- Windows PowerShell 5.1 cannot run the isolated verifier; it explicitly requires PowerShell 7. Normal setup/run/verify scripts remain compatible with the documented startup.

## Simulated durable transaction milestone

- 56 unit/integration tests PASS on Windows. Fourteen transaction tests cover exact restore, consent, targets, durable snapshots, external conflicts, ambiguous operation failure, restart recovery, snapshot corruption, identity mismatch, idempotency and concurrent preparation.
- Independent review reproduced a crash gap between PREPARED and VERIFIED_BACKUP. New failing tests demonstrated it; recovery and cancellation were corrected. A never-executed transaction cannot overwrite an external value even if it coincides with the proposed target.
- The actual simulated core loop ran 30 -> 60 -> 30 seconds with journal events PREPARED, VERIFIED_BACKUP, EXECUTING, VERIFIED, REVERTING, REVERTED. docs/simulated-transaction-receipt.json is synthetic evidence only; physical_writes=0.
- Chromium browser checks PASS at 390/768/1440/3440: explicit synthetic consent, verified change, page reload, persisted active journal and exact Undo. Actual Android and Freebox read-only inspections also pass in the local browser suite when available.
- The transaction engine rejects physical adapters. The HTTP transaction route rejects physical sources. No physical action or physical rollback has been performed.

## Physical timeout permission-refusal evidence

- 63 unit/integration tests PASS on Windows after adding the narrowly scoped Android timeout adapter, explicit physical opt-in and HTTP refusal of misconfigured physical engines.
- Read-only code review found no material defect in the isolated single-phone verifier. Mocked tests cover fixed commands, authorization loss, build-identity changes, exact unit conversion and denied writes.
- One actual controlled screen-timeout attempt was blocked by the owned phone. Journal events were PREPARED -> VERIFIED_BACKUP -> EXECUTING -> QUARANTINED -> REVERTED. The proposed value was never verified. A separate read-only check confirmed the original setting remains intact.
- Android's WRITE_SETTINGS diagnostic recorded a rejection. No permission bypass or automatic write retry was attempted. docs/physical-transaction-attempt.json records the failure and original-state preservation without device identifiers.
- Physical change and physical Undo success remain UNPROVEN. This is evidence of safe refusal/recovery, not a successful optimization. The browser remains physically read-only.

## Event-driven Android connection handling

- 71 unit/integration tests PASS on Windows. Event coverage includes fixed tracking command, raw-identifier exclusion, duplicate-frame suppression, bounded queues, missing ADB, owned-process cleanup and two reconnect/termination handoff races.
- The installed ADB client was measured to emit four-hex-length-prefixed frames. The actual binary parser consumed a real tracking frame and published only the adapter's redacted inventory. The measured inventory included one authorized USB phone and an offline emulator; no claim of two physical phones is made.
- Controlled Chromium events verify unauthorized -> authorized -> offline handling, stale inspection rejection and stream closure on source change. These are controlled event tests, not physical unplug fault-injection evidence.
- Real browser source/inspection/recovery checks continue to pass at 390/768/1440/3440. Closing streams on Windows now releases subscriptions without a connection-abort traceback.
- Read-only review identified both stopped-worker and natural-exit handoff races. Failing regression tests reproduced them before lifecycle-lock fixes. All six monitor tests pass after review.
- No additional model calls, physical setting writes or permission changes were performed for this milestone.

## Hardware-free browser CI

- The isolated offline browser suite passed locally at 390/768/1440/3440 using Playwright 1.63.0. It verifies synthetic inspection, historical proof labels, durable simulated Undo after reload, missing ADB, unavailable gateway and English layout without overflow.
- Device responses are controlled; this suite performs zero physical-device or model-provider requests. A temporary server and journal are cleaned up after the test.
- Optional test dependencies are pinned separately from the dependency-free application runtime. A new Ubuntu 24.04 browser CI job installs these and runs the same isolated suite. Remote job results are tracked separately from local PASS results.

## Captioned evidence preview

- A direct headless browser recording captured actual Android read-only inspection, historical Meta proof, the simulated change/reload/Undo loop, actual Freebox public discovery and the recorded physical-write refusal.
- The capture used a separate temporary synthetic journal; no physical setting write or model request occurred during filming. Desktop input and desktop recording were not used.
- The encoded preview was verified as H.264, 1920x1080, 30fps, exactly 177 seconds and intentionally without an audio track. Representative Meta-proof and physical-refusal frames were visually checked for readable captions and truthful labels.
- docs/jury/DEMO_PREVIEW.json records the captured application revision, scene timing, SHA-256 and limitations. The preview does not assert successful physical Undo or a live browser/provider inference.

## Local Meta reasoning

- 81 unit/integration tests PASS (Python 3.10 in the Linux VM). New coverage: pinned digest, fixed loopback endpoint, numeric privacy allowlist, schema/identity rejection, invented-number rejection, ADB vs SIMULATED source routing, one in-flight request and no cloud fallback. HTTP tests confirm only server-reread allowlisted facts reach the local broker and that a cloud broker can never receive physical data.
- One actual CPU-only call of llama3.2:3b-instruct-q4_K_M (digest verified) on SIMULATED facts: 151 prompt + 60 completion tokens, 8403 ms, 0 bytes VRAM observed, $0 provider cost. See docs/local-meta-smoke-receipt.json.
- Local review of real ADB facts through the browser: NOT TESTED. Windows unit run and browser e2e for this milestone: NOT RE-RUN.
- No physical writes, no cloud model calls.

## Windows run_all (2026-10-26 19:03 UTC)

- verify.ps1 exit: 0. Offline browser e2e exit: 1.
- Local Meta review of real ADB facts: NOT_TESTED.
