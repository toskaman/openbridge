# Evidence ledger — 26 October 2026

Current interpretation: this ledger is chronological. Counts, failures and statements such as NOT TESTED describe their recorded milestone; later sections may supersede them. See [release status](docs/RELEASE_STATUS.md) for the current backlog. Hosted-credit guards are $0.10 reserved per explicit request, $0.20 per fresh observation and $1 persistent local lifetime allowance; none is an account-wide provider billing cap.

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

## Android TV over ADB Wi-Fi and TV Bluetooth relay (real)

- The participant's Android TV (Android 11, ARMv7, 1.3 GB RAM) was found by mDNS (androidtvremote2 + Cast at the same address). One owner-triggered `adb connect <tv>:5555`: port open, TV showed "Allow debugging?", owner accepted with the remote. Inspection over Wi-Fi ADB read 11 facts; battery correctly unavailable (no battery). New product feature: "Connect over ADB Wi-Fi" in every TV sheet (single connection to that TV's private IPv4 only, no scanning) with brand-aware tutorials for enabling debugging and for accepting the prompt.
- Identity: the TV's Bluetooth address read with `settings get secure bluetooth_address` equals the `bt` value announced over mDNS, so the mDNS TV and the ADB TV now merge on a strong identifier (one node, LAN + WIFI links).
- Companion installed on the TV without a prompt and paired over the LAN (no USB). Real problems found and fixed: (1) the activity was destroyed by the low-RAM TV while system settings were open, stopping the relay (perceived as a crash) — relay now process-wide, scans still require the app in the foreground; (2) the Bluetooth enable dialog/settings intents did nothing on this Google TV — direct documented `BluetoothAdapter.enable()` on Android ≤12 when the owner taps, system dialog on 13+, resolved-intent fallbacks; (3) logcat showed the TV's system Bluetooth app (`com.android.bluetooth`) was disabled (enabled=3), so no radio could start — re-enabled at the owner's request (original state recorded) and now diagnosed by the Companion with a guide; (4) Windows default encoding broke UI symbols — build now compiles UTF-8; (5) the pairing code could be off-screen on TV — app scrolls to it and exposes it to accessibility services.
- Real TV relay scan over the LAN: 6 BLE advertisers in 8.3 s; through the UI the TV node gets 6 BLE children (observe-only) and ble_relay REAL_HARDWARE_VERIFIED.
- Companion UX per owner request: modern card/checklist design, one "Set up everything" flow that walks through Android's own dialogs (also on first launch), scans enabled automatically after pairing (pausable), "Don't ask again" permissions redirect to the app's permission page.
- Privacy mode `?redact` replaces household device names by category numbers; docs/jury/screens/fabric-tv-relay-redacted-1440.png was captured in that mode from the real network.

## Session restore (owner rule: always offer to restore pre-session settings)

- New session journal + "Finish session…" dialog: lists every change made outside reversible transactions with its original state and restores the owner's selection with verified fixed commands; non-invertible items (Freebox authorization, Bluetooth on) are reported as MANUAL with steps. Tests: tests/fabric/test_session.py, HTTP route test.
- Real use: the four changes made during the 27 Oct TV tests (system Bluetooth app re-enabled on the TV, Companion on TV and phone, ADB Wi-Fi connection) were recorded retroactively (dev/record_test_changes.py, because they had been made through the dev bridge) and the owner chose to restore all of them. Result through the product UI: TV com.android.bluetooth back to disabled-user (enabled=3, re-read), Companion uninstalled from both devices (package absent), ADB Wi-Fi disconnected. Not restored by software: TV location services (turned on by the owner) and the Freebox authorization (revocable in Freebox OS).

## SSDP/UPnP and endurance

- src/fabric/ssdp.py: read-only M-SEARCH (sent twice, TTL 1, LAN interface), replies grouped by description LOCATION, description XML fetched once with DTD/entity refusal and size cap; UPnP UDN is a strong identifier; IGD control is BLOCKED (no SOAP, no port mapping). Real network: the Freebox announced 10 UPnP service types, first shown as 3 devices (embedded sub-devices) and fixed to 1; the Android TV answered DIAL in 1 of 3 runs (it was likely entering standby).
- Endurance (dev/endurance.py, docs/benchmark/STATUS.md): 1,500 nodes, 20 rounds, 5,000 malformed packets, relay churn — bounded time/memory, no crash, no leaked threads.
- README rewritten for the jury around the Device Fabric scenario (old README kept as docs/README_HISTORY.md).

## Device Runtime v2 — /api/v2 on the participant LAN (27 Oct 2026, branch feat/device-runtime-v2)

Reproduce: `python -m dev.runtime_v2_smoke` (read-only; prints counts and finding kinds only). Base commit 055c48a, Windows 11, Python 3.14.4.

- REAL_HARDWARE_VERIFIED: `bounded_discovery` primitive through `POST /api/v2/execute` (CSRF + Origin) → receipt VERIFIED; providers mDNS OK, SSDP OK, ADB OK, Freebox AUTHENTICATED, PC BLE unavailable (no adapter). Graph: 14 devices; 22 capability descriptors (16 REAL_HARDWARE_VERIFIED, 6 BLOCKED — offline emulator), 0 controllable because no authorized Android device was connected.
- REAL_HARDWARE_VERIFIED: `read_facts` on the Freebox (v7, fw 4.13.1) → 13 OBSERVED findings (connection, FTTH optics, uptime, LAN hosts) + 1 INFERRED (presence changes since previous run).
- REAL_HARDWARE_VERIFIED (refusals): free-form primitive → UNKNOWN_PRIMITIVE; write without consent → CONSENT_REQUIRED. `/api/v2/diagnosis` stated `ble_unreachable` (INFERRED: no adapter and no relay candidate at that moment).
- Preflight on the same PC (`python -m src.runtime.preflight`): READY; bleak 3.0.2 and Playwright 1.63.0 match pins; Llama 3.2 3B and Muse Glimmer digests equal the pinned full SHA-256.
- NOT TESTED on hardware in this session: Android diagnostics and USB-unplug-during-write (phone not connected, TV off). Simulated coverage only (tests/runtime).

## Device Runtime v2 — Android diagnostics and real transport loss on the Android TV (27 Oct 2026)

- REAL_HARDWARE_VERIFIED: `read_facts` on the Android TV over ADB Wi-Fi (`python -m dev.runtime_v2_smoke`): 10 OBSERVED findings (no battery, 4.3 GB storage / 1.25 GB free, uptime 132.7 h, Wi-Fi on, 4 cores, 0.35 GB RAM available, user 0, patch 2025-08-01, 11 user apps) + 1 INFERRED (`security_patch_outdated` = 14 months).
- REAL_HARDWARE_VERIFIED, transport loss (`python -m dev.transport_loss_smoke <tv>:5555`): link dropped with `adb disconnect` 0.4 s into the read.
  - First run exposed two defects. The cut-short read was reported VERIFIED with 5 of 11 facts, and the TV was refused after reconnecting because ADB issued a new handle.
  - Fix: a link check after the reads (a cut-short read is now PARTIAL, not verified) and re-attachment by strong identity only.
  - Re-run: PARTIAL (5 facts, verified=false) → BLOCKED DEVICE_UNAVAILABLE on the dead link → VERIFIED with 11 facts after reconnect. Simulated regression tests were added for both.
- USB unplug during a write: still NOT TESTED physically (the phone was not visible to ADB).

## Device Runtime v2 — phone diagnostics and transport reset during a real write (27 Oct 2026)

- REAL_HARDWARE_VERIFIED: `read_facts` on the Xiaomi phone over USB → 13 OBSERVED findings (battery 100 %, 21 °C, health good, charging, 224 GB / 154 GB free, uptime 34 h, Wi-Fi on, 8 cores, 1.8 GB RAM available, user 0, patch 2025-02-01, 74 user apps) + 1 INFERRED (`security_patch_outdated` = 20 months).
- REAL_HARDWARE_VERIFIED, ADB transport reset during a write (`python -m dev.link_loss_write_smoke 0.05 --confirm-owned-device`). This was a host-side `adb reconnect` 50 ms into disabling one allowlisted optional app, not a physical cable pull.
  - Apply → BLOCKED "Transaction quarantined".
  - Immediate revert → refused: the state could not be read, so the external state was not overwritten.
  - Journal state → QUARANTINED. No success was reported at any point.
  - Once the phone was visible again: recovery → REVERTED, read-back equal to the recorded original value (enabled).
  - Reproduced twice.
- Observed limitation: after `adb reconnect` the phone did not reappear until the ADB server was restarted (`adb kill-server`). The TV over Wi-Fi then needed a new `adb connect`. Recovery is safe meanwhile: the transaction stays QUARANTINED in the journal until then.
- Physical cable pull: still NOT TESTED (needs the owner's hand).

## Device Runtime v2 — physical USB cable pull during real writes (27 Oct 2026, 01:24 Paris)

Reproduce: `python -m dev.cable_pull_smoke --confirm-owned-device`, then the owner pulls the phone's cable while the loop runs. Allowlisted optional app, Android user 0, Xiaomi phone.

REAL_HARDWARE_VERIFIED:

- The script ran continuous exact loops (prepare → apply → read-back → revert → read-back); 8 complete verified loops finished before the pull.
- The owner pulled the cable by hand. It landed during the **revert** phase, while the app was still disabled.
- Engine response: "Recovery quarantined; external state was not overwritten"; journal state QUARANTINED. No success was reported for the interrupted transaction.
- The owner re-plugged after about 20 s; the phone reappeared to ADB without restarting the server. The journal still showed QUARANTINED, and normal recovery → REVERTED with read-back equal to the original value (enabled). original_preserved = true.

## Real relay → Capability Forge, end to end on hardware (27 Oct 2026)

Reproduce: `python dev/relay_forge_real.py` from a throwaway copy of this tree that also contains Forge's `src/forge` from feat/capability-forge @ 39e6ed4, unmodified. Xiaomi phone over USB.

REAL_HARDWARE_VERIFIED, all through product code paths:

1. Discovery primitive.
2. Companion installed by the server's install worker, journaled as a session change.
3. Owner-equivalent `pm grant` of BLUETOOTH_SCAN and BLUETOOTH_CONNECT. These are dev-harness steps; in the product the Android dialogs ask the owner.
4. Pairing through `relay_action`, with the code read from the phone's screen.
5. `relay_ble_scan` primitive (consent) → VERIFIED, 3 advertisers.
6. `/api/v2/capabilities` showed ble_relay readable+controllable, REAL_HARDWARE_VERIFIED, SESSION_CLEANUP; the route was FRESH, permission granted, owner enabled.
7. Forge's `RuntimeV1Provider`, via `api_v2.reader`, accepted 3/3 targets as REAL_HARDWARE_VERIFIED, fact age 0.0 s.
8. `relay_revoke` primitive → the next Forge snapshot was refused (RUNTIME_CAPABILITY_OR_ROUTE_UNKNOWN).

The Companion stays installed and is listed in the session journal for the owner's "Finish session" choice.

### Physical publication through Forge's HTTP host (same day, phone unlocked by the owner)

REAL_HARDWARE_VERIFIED. The run used the unmodified Forge `create_forge_server` (current Forge worktree) with `provider=RuntimeV1Provider(api_v2.reader(server), …)` bound to a target seen by the real phone relay.

1. Catalog mode was PHYSICAL_READ_ONLY.
2. `POST /api/publish {consent:true}` → 200, `simulation: false`.
3. Observation route → 200 with 1 relay observation, source `RELAY:…`.
4. `/api/documents` → 200 (OpenAPI, schemas, client).
5. Runtime `relay_revoke` primitive, then the observation route → 409 RUNTIME_CAPABILITY_OR_ROUTE_UNKNOWN.
6. `POST /api/remove` → 200; the observation route → 404 SERVICE_REMOVED.

Before this run, a locked phone blocked the on-screen code read, so the harness failed closed and never paired.

## Runtime v2.1 — power/thermal diagnostics and read-only watchers (27 Oct 2026, branch feat/runtime-v2.1)

Reproduce: `python -m dev.watch_smoke`.

- REAL_HARDWARE_VERIFIED on the Xiaomi phone:
  - New findings `power_state` = dozing and `thermal_status` = none (OBSERVED).
  - `watch_start` primitive (consent) on `memory_available > 0.01 GB`: 2 runs in 40 s, exactly one `watch_triggered` event (edge-triggered); `watch_stop` → STOPPED.
- REAL_HARDWARE_VERIFIED on the Android TV (first run): `thermal_status` = none. The TV went to standby mid-watch, so the watch's next run was BLOCKED and emitted `watch_unavailable`, not a value.
- Defect found on hardware and fixed: `dumpsys power` output exceeds the adapter's 128 KB cap, so the read was refused (fail-closed). These two allowlisted system dumps now have a 2 MB cap; all other reads keep 128 KB.
- REAL_HARDWARE_VERIFIED: Freebox "internet down" watch (`internet_state ne "up"`, `python -m dev.freebox_watch_smoke`): 2 runs, last value "up", 0 triggers (correct while online), stopped cleanly. A real outage trigger is NOT TESTED; the trigger logic is covered by tests/runtime/test_watchers.py.

## Runtime v2.3 — multi-device diagnostic report (27 Oct 2026)

Reproduce: `python -m dev.report_smoke`.

- REAL_HARDWARE_VERIFIED: the `diagnostic_report` primitive on the participant LAN read the phone (16 findings, warning `security_patch_outdated`) and the Freebox (27 findings), both VERIFIED. It listed 12 other devices as observed without a read grant. Labels were redacted ("phone 1", "router 1").
- Two defects were found on the first hardware run and fixed:
  - LAN-inventory hosts with no read grant appeared as BLOCKED sections.
  - A second gateway seen via SSDP was given the Freebox's API facts. Freebox reads now require that device's own `lan_inventory` capability via FREEBOX_API.

## Android TV relay → Capability Forge on hardware (27 Oct 2026)

Reproduce: `python dev/tv_relay_forge.py` from a merged copy with Forge `src/forge`. The TV was on Wi-Fi ADB; the relay was reached over the LAN.

REAL_HARDWARE_VERIFIED, through product paths:

1. The TV system Bluetooth app (disabled by the earlier session restore) was re-enabled and journaled as "System app re-enabled".
2. Companion installed by the server worker (journaled).
3. Location permission granted from the dev harness; the product asks through the Android dialog.
4. Pairing code read from the TV screen → PAIRED, eligible.
5. `relay_ble_scan` primitive (10 s, consent) → VERIFIED, 5 advertisers.
6. Forge `RuntimeV1Provider` accepted 5/5 targets as REAL_HARDWARE_VERIFIED.
7. The source-specific facts route returned `ble_rssi` for this relay only.
8. `relay_revoke` → Forge snapshot refused (RUNTIME_CAPABILITY_OR_ROUTE_UNKNOWN).

Both TV changes stay open in the session journal for the owner's Finish session choice.

## Windows PC through the owner's BridgeWindows agent (27 Oct 2026)

Reproduce: start `agent.exe` on the other PC, then `python -m dev.windows_bridge_smoke` (server option `--windows-bridge`; key in the Windows vault). Second PC: Windows 10 build 17763 x64; agent 3.7.1 (x86 build).

REAL_HARDWARE_VERIFIED:

1. Listener bound to the LAN interface only. The agent authenticated with the configured key and protocol 3.x.
2. Discovery `windows` provider → OK. The PC became a `computer` device with a strong hashed identity and capabilities `windows_diagnostics` (read). run_command, file_write, registry_write, input_injection and agent_update are BLOCKED.
3. `read_facts` → VERIFIED, 9 OBSERVED findings: OS build, architecture, 2 cores, CPU load, RAM 3.91/2.56 GB, uptime, C: free 69 GB, 65 processes. No process names or hostname are returned.
4. `exec.run` was refused by the adapter before sending.

Found on hardware and fixed: the agent is a 32-bit build, so on 64-bit Windows its registry reads use the WOW64 view, where `MachineGuid` (and `ProductId`) are absent. The identity now falls back to `HKLM\SYSTEM\...\Hardware Profiles\0001\HwProfileGuid`, which is not redirected and is hashed with the install salt.

Delivery: `agent.exe` was served to the other PC from a temporary LAN-only download page (single file, SHA-256 shown, auto-stop after 25 min, key not served).

## Windows agent: 64-bit self-update and the Companion onboarding portal (27 Oct 2026)

- REAL_HARDWARE_VERIFIED: the owner moved agent.exe to a writable folder (Desktop) and OpenBridge/BridgeWindows' own `agent.update` hot-swapped the 32-bit agent for the 64-bit build I compiled (`agent_x64.exe`, machine type 0x8664, passes `--selftest`). Result: `updated: true, reconnected: true`, old pid 4344 → new pid 5816, SHA-256 of the running agent equals the x64 build. OpenBridge then read it over the bridge: `Is64BitProcess = True`, architecture `x64 (64-bit)`. Earlier failure (access denied at offset 0) was the agent running from C:\ (non-writable); running from Desktop fixed it.
- The 64-bit build is the same source with one additive change (report `x64`/`x86` by `_WIN64`). Built with `zig cc -target x86_64-windows-gnu` because the installed MinGW GCC is 32-bit only. The user's BridgeWindows project was not modified; the build used a copy.
- New: `dev/agent_portal.py` — a LAN onboarding page for any PC / the jury. One download button for agent.exe (SHA-256 shown), the exact PowerShell launch command (surfaced from BridgeWindows' own `remote_network_helper`, with a clipboard copy button and an http-safe fallback), and a live status that flips to "Connecté ✓ (x64)" with a privacy-safe metrics strip (CPU, RAM %, disk free, uptime, latency — no hostname or identifiers). Private-network clients only; self-stops after --minutes. Verified on the real LAN: page 200, agent.exe 171 KB, state connected=x64, metrics live, hostname not exposed.

## V4-03 crash drill on the phone — five process kills, journal recovery (27 Oct 2026)

Reproduce: `python -m dev.crash_drill --target phone --confirm-owned-device` (main @ PR #12). Xiaomi phone over USB, one allowlisted optional app, Android user 0.

REAL_HARDWARE_VERIFIED, 5/5:

| Failpoint (worker process killed, exit 97) | Journal at restart | App state at restart | Recovery | Read-back = original |
|---|---|---|---|---|
| after_journal_prepared | PREPARED | original | REVERTED | yes |
| after_backup | VERIFIED_BACKUP | original | REVERTED | yes |
| after_executing_marked | EXECUTING | original | REVERTED | yes |
| after_write_before_verify | EXECUTING | **changed (disabled)** | REVERTED | yes |
| during_revert | REVERTING | **changed (disabled)** | REVERTED | yes |

Each recovery ran in a fresh process that read the durable journal and the phone independently (2.7–5.4 s per drill). This is crash recovery for one supported reversible setting, not atomicity across devices.

## Live Meta cloud advisory fixed and verified (27 Oct 2026)

- Bug: `muse-spark-1.3` is a reasoning model; the broker's 900-token completion cap was fully consumed by reasoning (`reasoning_tokens` ≈ 898), so `content` came back empty and `recommend()` failed as "Meta call failed".
- Fix (`src/ai/broker.py`): `max_completion_tokens` raised to 4000; empty/whitespace content is now an explicit `ModelBlocked('Model returned no content…')`; the $0.10 reservation and $1 total ceiling are unchanged. `src/server.py` now reads the key from the OS vault (`meta-api-key`) when `MODEL_API_KEY` is not in the environment.
- REAL (Meta Model API, synthetic facts only, no personal data): one live call returned `muse-spark-1.3` id chatcmpl-01a17d97…, a schema-valid `inspect_only` advisory citing the three supplied keys, usage 110 prompt + 625 completion (533 reasoning), estimated cost **$0.0028**. Within the owner's free promotional credits; the broker enforces a $1 persistent local reservation ceiling, not a provider-wide hard billing cap.
- Only free credits are used: each explicit request reserves $0.10, each fresh observation allows $0.20 and the persistent local lifetime ceiling is $1; no automatic retries; failures keep their reservation.
