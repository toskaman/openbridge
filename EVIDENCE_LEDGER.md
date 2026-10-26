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

## Windows run_all (2026-10-26 19:05 UTC)

- verify.ps1 exit: 0. Offline browser e2e exit: 0.
- Local Meta review of real ADB facts: PASS - see docs/local-meta-adb-receipt.json.

## Grounded local Meta summaries

- New rule: the local summary must state the exact value of every referenced fact; ungrounded text such as "No changes detected." is rejected. Two new unit tests (83 total).
- Real ADB review on Windows after the change: "Battery is 100% and 154.02 GB of storage is free." 175+76 tokens, 10.5 s CPU, digest verified, inspect_only. Receipt updated in docs/local-meta-adb-receipt.json.

## First physical change and verified Undo

- 90 unit/integration tests PASS (Linux VM; Windows re-run below). New package-state adapter tests: allowlist, fixed user-0 commands, inconsistent state blocks, unauthorized device blocks, denial preserves original, exact default-state restoration.
- Real run on the owned Xiaomi phone (Android 14) for org.nixgame.ruler: default -> disabled-user -> default. Journal PREPARED, VERIFIED_BACKUP, EXECUTING, VERIFIED, REVERTING, REVERTED in 3.2 s. Raw `dumpsys package` independently showed user-0 enabled=0 before and after. Receipt: docs/physical-package-receipt.json.
- Honest note: an earlier run of the first adapter version restored the app to "enabled" (code 1) rather than the original "default" (code 0). The app was functional throughout, but the restoration was not bit-exact. This was caught by an independent dumpsys check; the adapter was corrected to track exact codes, the original default state was restored with `pm default-state`, and the verified run above was recorded.
- The browser still exposes no physical write route.

## Verifiable agent loop (real phone)

- 102 unit/integration tests PASS on Windows, three consecutive runs. One earlier Windows run reported a single error that did not reproduce; recorded here rather than hidden.
- New tests: deterministic gate decisions, plan schema/privacy/grounding/eligibility rejection, fixed goal enum, consent and gate enforcement, refusal restores original, no double execution, undo-without-change blocked, HTTP opt-in/CSRF/source checks.
- Real HTTP run (goal=declutter): local Llama 3.2 3B proposed disabling org.nixgame.ruler (11.4 s CPU, 286+113 tokens, $0); gate REVIEW_REQUIRED; consented execute verified; Undo exact. Raw dumpsys user-0 `enabled=0 -> 3 -> 0`. Receipt: docs/agent-loop-receipt.json.
- Real browser run (Chromium, 390 and 1440 px, tests/e2e/agent_physical_smoke.py): plan for com.miui.compass, consent, execute, Undo; no page errors or horizontal overflow. Raw dumpsys afterwards: all three candidate apps enabled=0.
- With goal=review the model returned inspect_only (gate NO_ACTION). One plan was rejected by the grounding check before the prompt template was tightened; the system failed closed.
- Offline browser e2e still PASS at 390/768/1440/3440.

## Runtime Meta-only registry (product-enforced)

- New src/ai/registry.py: the shipped runtime manifest is loaded fail-closed; non-Meta or unknown model IDs and non-Meta endpoints are rejected (matrix R04/R05/R06). `--local-meta` startup refuses a model/endpoint pair absent from the manifest. A source scan test fails on any non-Meta inference client string in src/ (R12, static only).
- Every broker class (cloud Muse Spark, local Llama, local Muse Glimmer) is asserted to be declared in the manifest. 108 tests PASS (Linux VM).
- Muse Glimmer broker added but fails closed: its digest is PENDING until verified from the official registry pull.

## Guided UX and pinned Muse Glimmer

- Guided states (WAITING_FOR_DEVICE, REQUIRES_USER_ACTION, COMPLETE, BLOCKED) with a non-modal guidance dialog that closes by itself when the live re-check sees an authorized phone. tests/e2e/guided_smoke.py PASS at 390/768/1440/3440 on Windows (controlled responses, zero device/model calls); screenshots visually checked at 390 and 1440. Added to CI. Offline e2e still PASS.
- Muse Glimmer `muse-glimmer:30b-q4_K_M` pulled from the official Ollama registry into a private service on 127.0.0.1:11438 (27.9B, Q4_K_M, 18.2 GB). Local digest de878ce3...64c1 equals the SHA-256 of the official registry manifest; pinned in src/ai/glimmer.py and the runtime manifest. Inference not yet measured.

## Muse Glimmer inference and planning ablation

- First real Muse Glimmer call (digest-pinned, private service 127.0.0.1:11438): valid grounded plan in 18.1 s, 282+99 tokens, 13.5 of 17.4 GB in VRAM. Receipt: docs/glimmer-smoke-receipt.json. Ollama appended a literal `<|eot|>` after the JSON; only that exact suffix is now stripped (unit test covers exact/extra/other tokens).
- To fit the 18 GB model, the participant's own unrelated Ollama model (port 11434, infinite keep-alive) was temporarily unloaded, then reloaded with the same infinite keep-alive and verified. No model files were removed.
- Ablation, 30 synthetic cases × 3 repeats: rules 90.0% correct (9 unsafe proposals); Llama 3B 60.0% valid / 53.3% correct (6 unsafe); Muse Glimmer 90.0% valid / 86.7% correct (3 unsafe). Gate refused 100% of unsafe proposals for all routes. Details and honest interpretation: docs/benchmark/STATUS.md.
- Product option `--local-meta --glimmer` added; registry enforces the declared Glimmer endpoint.

## Muse Glimmer drives the real-phone agent loop (browser)

- Server `--local-meta --glimmer --agent`; Chromium at 390 and 1440 px (tests/e2e/agent_physical_smoke.py). Glimmer planned "temporarily disable com.miui.compass" with exact facts (100%, 154.13 GB); gate REVIEW_REQUIRED; consent; execute verified (Android state 0 -> 3); Undo exact (state 0). Plan latency 63.3 s (cold load) and 39.6 s (warm) on the shared desktop GPU.
- Raw dumpsys afterwards: compass, stopwatch and ruler all user-0 enabled=0. Participant's own Ollama model was unloaded for the run and reloaded with its original infinite keep-alive.
- Screens: docs/jury/screens/agent-glimmer-390-plan.png, docs/jury/screens/agent-glimmer-1440-undone.png (no identifiers visible).

## Restart-after-change recovery (real phone)

- Gap found in review: plans lived only in server memory, so a crash after a change would leave Undo unreachable from the browser. Added DeviceAgent.pending/recover, /api/agent-recover and a UI "Recover exact original state" action; planning is refused while a journaled change is pending. Three new unit tests + HTTP route test.
- Real fault injection: Llama-planned change to com.miui.compass verified (raw dumpsys enabled=0 -> 3); server process force-killed before Undo; after restart, planning was blocked; recovery restored the exact original (raw enabled=0). Receipt: docs/crash-recovery-receipt.json. Cable unplug mid-write remains NOT TESTED on hardware.
- Pre-event reuse audit (kit audit_submission.py) against the participant's pre-event v0.8 archive: 0 exact matches, 0 near matches, 0 secrets across 110 tracked files. The v0.9 archive was not found on this PC.
- Anonymous fresh clone of the public repository at 6a36803 on a clean Linux machine: all unit/integration tests, offline e2e and guided e2e PASS; no device serials or local usernames in the tree. GitHub CI green for every pushed commit through 29087f1.

## Device Fabric phase A — Android compatibility fixes

- Baseline audit recorded in docs/DEVICE_FABRIC_BASELINE.md (HEAD 78b6692, tests PASS, CI green).
- Wi-Fi ADB (`ip:port`, `adb-…._adb-tls-connect._tcp`) now listed as WIFI instead of skipped/mislabelled. OpenBridge never pairs or connects Wi-Fi ADB itself. Wi-Fi ADB hardware: NOT TESTED (needs owner pairing on the phone).
- Inspection is per-fact tolerant: a missing property, absent battery (TV boxes) or failed command marks only that fact `unavailable`. New read-only facts: CPU ABI, security patch, RAM, screen timeout, television (leanback) and Bluetooth LE features. The test now enforces an exact allowlist of read-only shell commands.
- Two real-hardware regressions caught during this change and fixed: on the Xiaomi, `df -k /data` reports /data under a bind-mount point, and `pm has-feature` exits 1 for "false". Now parsed from the single df row and from `pm list features`. Real phone: all 12 facts read, none unavailable.
- Package writes: allowed over USB, Wi-Fi ADB or emulator (ADB authorization remains the trust boundary); refused unless the active Android user is 0; the transaction engine refuses before any write when exact restoration is impossible (default state before Android 9). Real stopwatch loop re-verified with the user check (default -> disabled-user -> default).
- 119 unit/integration tests PASS (Linux VM).

## Device Fabric P0 — registry, mDNS, Freebox auth flow, BLE, topology UI

- Typed contracts (src/fabric/contracts.py) and a registry with conservative identity resolution: merge only on a shared strong identifier; weak signals (IP, name, private BLE/MAC addresses) produce `possibly_same_as` hints and never merge; conflicting strong IDs refuse merging; each fact keeps every source and prefers verified direct reads. Raw serials/MACs are pseudonymized with a per-install HMAC salt. 11 identity tests (two IPs, USB+Wi-Fi same phone, randomized MAC, IP reuse, same model twins, incomplete identity, conflict).
- Stdlib mDNS/DNS-SD browse (src/fabric/mdns.py): link-local TTL 1, explicit LAN interface, time/packet/record caps, compression-pointer and malformed-packet defenses, responders and addresses outside the private-network scope ignored. REAL_HARDWARE_VERIFIED on the participant's LAN: 7 services (Freebox API, SMB, HTTP, HomeKit, AirPlay, Android TV remote, Google Cast) in about 3 s. First attempt received 0 packets because multicast left through a virtual adapter; fixed by binding the default-route LAN interface.
- Freebox official app authorization (src/adapters/freebox_auth.py) with DPAPI-protected token (src/fabric/credential_vault.py), read-only GET allowlist, session renewal once, revoked-token cleanup; LAN hosts linked Freebox -> host as observe-only; Wi-Fi/DHCP/firewall/settings marked BLOCKED by policy. INTEGRATION_VERIFIED with a fake Freebox. Real request issued: shown on the box, ended TIMEOUT because nobody pressed the button; authenticated LAN inventory remains NOT TESTED on hardware.
- BLE (src/fabric/ble_local.py, optional bleak 3.0.2): passive, bounded, never connects; only static-random addresses are strong identity. This PC has no Bluetooth adapter -> BLE_UNAVAILABLE reported honestly; the phone's Bluetooth is off. BLE hardware: NOT TESTED.
- Device Fabric API (/api/fabric, /api/fabric-discover single-flight with provider allowlist, /api/freebox-authorize, /api/freebox-authorization) and UI section: provider status, topology tree with per-transport grants, duplicate hints, device sheet with sources and capability statuses, guided Freebox approval dialog.
- Real browser run on the participant's network (tests/e2e/fabric_real_smoke.py, not CI): 6 devices / 10 links at 390/768/1440/3440, no overflow or page errors; screenshots docs/jury/screens/fabric-real-*.png checked visually. Hermetic tests/e2e/fabric_smoke.py added to CI.

## Freebox authenticated LAN inventory (real)

- The participant approved "OpenBridge Device Fabric" on the Freebox Server front panel (second request; the first timed out). Token stored with Windows DPAPI. Granted permissions exclude `settings`; OpenBridge only calls allowlisted GET endpoints.
- Real read: 127 known LAN hosts, 12 active, 37 with randomized MACs (never used as strong identity). The graph shows the 12 active hosts as Freebox -> host INVENTORY links with observe-only grants (inactive hosts counted, not drawn): 18 devices / 22 links in 4.2 s. The LG TV seen by the Freebox and by mDNS is flagged as a possible duplicate rather than merged; the PC and the ADB phone also appear in the Freebox inventory and are not merged (no shared strong identifier). REAL_HARDWARE_VERIFIED.
- Screenshot of this run is kept private (household device names); public screenshots use the earlier run.

## Relay protocol v1 and Android Companion

- src/fabric/relay.py: pairing by on-screen 6-digit code (PBKDF2), HMAC-SHA256 signed commands from a closed set with nonce/expiry/replay protection, bounded BLE scans (≤15 s, ≤200 observations), untrusted-reply validation, capability- and permission-based relay selection (mains power preferred), offline after 3 failures, revocation, loopback/private-only HTTP transport. 10 relay tests including pairing with a reference relay.
- companion/android: native Java Android app (minSdk 26, targetSdk 34, TV leanback + D-pad UI, runtime BLE permission requests only, scans only while open and owner-enabled). Built and signed reproducibly with the official SDK tools (dev/build_companion.py; 33 KB APK). Android SDK licence accepted with the owner's explicit approval in chat.
- Installation on the Xiaomi: refused with INSTALL_FAILED_USER_RESTRICTED until MIUI "Install via USB" is enabled by the owner. Hardware relay scan: NOT TESTED yet.
- Device Fabric documentation added: UNIVERSAL_DEVICE_ARCHITECTURE, DISCOVERY_PROTOCOLS, DEVICE_IDENTITY_AND_DEDUPLICATION, FREEBOX_INTEGRATION, RELAY_SECURITY, ANDROID_COMPANION, KNOWN_LIMITATIONS.

## Vendor-aware guidance in the product

- src/fabric/guidance.py turns blocked steps into vendor- and version-specific guidance (goal, why, already tried, minimal action, waiting). Companion installation is now driven from OpenBridge (/api/companion-install) with bounded retries and adb error classification; relay failures return the matching guide; the UI shows them in the non-modal guided dialog. Tests: tests/fabric/test_guidance.py (vendor variants, TV/Android-version variants, install classification, server retry loop to success).

## Meta coverage advisor (real graph + ablation)

- src/fabric/advisor.py: deterministic candidate steps from the graph (authorize_freebox, install_companion, pair_wifi_adb, review_duplicate); the local Meta model sees categories, counts and step ids only and must pick a listed step with a real sentence; numbers must match the graph counts. Unusable output falls back to the rule with an explicit message.
- Real graph (participant LAN, phone unplugged so one candidate): Glimmer explained correctly with exact counts (15 devices, 12 indirect) and noted the step did not serve the Bluetooth goal; Llama 3B returned echoed ids/JSON fragments, which led to the new sentence-quality check.
- Ablation (docs/benchmark/STATUS.md): Llama 3B 0% usable; Glimmer 93.3% valid, 53.3% goal fit vs rule 100%; deterministic across repeats.

## Real Bluetooth relay through the phone (indirect discovery)

- Companion installed on the Xiaomi from OpenBridge after the owner enabled MIUI "Install via USB" (earlier attempts: INSTALL_FAILED_USER_RESTRICTED, now covered by the Xiaomi guide).
- Pairing over USB (adb forward, no Wi-Fi exposure): Java canonical JSON + PBKDF2 + HMAC-SHA256 interoperate with the Python side. The phone reported Bluetooth on and the "Nearby devices" permission granted (owner tapped Allow).
- Safety check on hardware: before the owner enabled scans in the app, a signed scan request was refused by the phone ("owner has not enabled scanning on this device").
- After the owner enabled scans: real 8 s relay scan found 9 BLE advertisers (4 with manufacturer IDs; 4 resolvable-private, 4 public/non-resolvable, 1 static-random addresses). The PC itself has no Bluetooth radio.
- Through the product UI (tests/e2e/relay_real_smoke.py, not CI): discover -> phone sheet -> pair with the on-screen code -> scan; 8–13 advertisers appeared under the phone as BLE/observe-only children, labelled by name or Bluetooth SIG company (e.g. Apple, Microsoft, a named pair of earbuds). The phone's ble_relay capability became REAL_HARDWARE_VERIFIED. Re-pairing an already paired phone failed at first (stored key took precedence); fixed in the Companion so a fresh on-screen code can replace the old key, never the reverse.
- Screenshots kept private (household device names). Hermetic relay UI flow (pair, scan, guided Bluetooth-off error) added to tests/e2e/fabric_smoke.py in CI.
- CI note: commit 7c81019 failed CI because a hermetic test fixture modified the wrong mock device; it was pushed because the commit script did not gate on that test's exit code. Fixed in 106241d (CI green). Commit scripts now commit only when the tests exit 0.
