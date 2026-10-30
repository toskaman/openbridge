# OpenBridge — Device Fabric

**Local Meta AI that understands the devices around you, reaches the ones your PC can't, and only changes what it can prove it can undo.**

Meta Global AI Developer Hackathon 2026 · Indie Developer · *Push the Frontier* · MIT licence

[Documentation](docs/README.md) · [Release status and next tasks](docs/RELEASE_STATUS.md) · [Evidence](docs/RELEASE_EVIDENCE.md) · [Hackathon entry](#built-for-the-meta-global-ai-developer-hackathon-october-26november-4-2026) · [About the developer](#about-the-developer) · [Device matrix](docs/HARDWARE_TEST_MATRIX.md)

![OpenBridge tour: real captures only — phone Companion, Command Center graph, Watch, Ask panel, XP agent, ESP32 proof](docs/jury/screens/openbridge-tour.gif)

*Every frame above is a real capture from this repository's evidence set — nothing staged. Full frames with context follow below.*

**What Meta accomplishes here:** local Meta models do the understanding — Llama triages requests on CPU, Muse Glimmer plans multi-step actions, explains devices and reads screens on GPU, and hosted Muse Spark answers only with explicit consent — while deterministic safety (typed skills, fingerprint-bound previews, execution receipts, exact undo) fences every AI proposal so nothing changes without proof it can be undone.

Three things you can do with it today:

1. **Ask, preview, approve.** Type a request in English or French; OpenBridge resolves it to a registered skill, shows exactly what will change, and executes only after your approval — every run ends with a receipt and an undo path.
2. **See everything, reach further.** One graph holds your whole home network — including devices your PC cannot see alone (Bluetooth via phone/TV relays, Freebox LAN hosts, a second PC, a Tuya vacuum) — with strong-identity merge so nothing is double-counted.
3. **Control from any screen.** Phone, watch, TV, a second PC, or a P1 port (ESP32, Playdate) all act as real control points over the same fabric: pair once, then command any device from any device.

Don't take our word for it — check the proof: [evidence registry](docs/DEVICE_EVIDENCE.json) (24 verified rows) · [device matrix](docs/HARDWARE_TEST_MATRIX.md) · [claim ↔ evidence matrix](docs/jury/CLAIM_EVIDENCE_MATRIX.md) · [evidence ledger](EVIDENCE_LEDGER.md).

<!-- OPENBRIDGE_HACKATHON_PRESENTATION_START -->
## About the developer

I'm an autistic independent developer who has been passionate about computers, programming, hardware and emerging technologies since childhood. I've always enjoyed exploring how systems work and discovering new ways for different technologies to connect. OpenBridge brings these interests together: making real devices easier to understand, connect and control through Meta AI.

![Real Device Fabric run, household names redacted](docs/jury/screens/fabric-tv-relay-redacted-1440.png)

*Real run on the author's home network, 28 Oct 2026 (names redacted with `?redact`): 24 devices — a Freebox reporting 12 active LAN hosts, mDNS/SSDP discovery, an Android phone over USB and an Android TV over ADB Wi-Fi as paired relays. The PC has no Bluetooth radio; BLE reach through relays is demonstrated on hardware in the [TV-to-phone handover](docs/release/COMPLETE_HANDOVER.md).*

![Ask OpenBridge natural-language panel](docs/jury/screens/ask-openbridge-1440.png)

*Ask OpenBridge: type a request in English or French; tiered Meta-only routing (free local Llama/Glimmer, cloud Spark only with explicit consent) resolves it to a registered skill, shows a fingerprint-bound preview, and executes only after owner approval. Local tiers verified live; cloud path unit-tested, broker unconfigured in this capture.*

![Companion 0.10.0 on a real phone](docs/jury/screens/companion-0-10-phone-main.png)

*Companion 0.10.0 on a real phone (29 Oct 2026): voice orb, typed commands, live link/Bluetooth/scan tiles, and owner controls — all over the signed, encrypted relay channel.*

![Allow full control warning popup](docs/jury/screens/companion-0-10-full-control-popup.png)

*Standing consent, on-device: "Allow full control" shows this warning — the PC may then send any command without asking each time. Revoking is one tap, and unpairing clears it. Proof of the full cycle (popup → allow → revoke → cancel) in the [0.10.0 release notes](docs/release/COMPANION_0_10_0.md).*

![Companion 0.10.0 on Galaxy Watch7](docs/jury/screens/companion-watch-0-10.png)

*Companion 0.10.0 on a Galaxy Watch7 (29 Oct 2026): install verified on-device, relay paired over the signed channel ([device:watch-sm-l310-01]).*

## Built for the Meta Global AI Developer Hackathon (October 26–November 4, 2026)

**Built from the ground up during the hackathon.** I built OpenBridge's project-specific implementation from the ground up for the October 26–November 4, 2026 event — including the Windows agent (Bridge Agent v4), written from scratch for this event. The new features presented for judging are the work completed during the hackathon and are supported by commits, test receipts and the demo. Third-party frameworks and dependencies retain their own origins and licenses.

**Track — Indie Developer.** An independent developer-led project, with contributors and contributions accurately listed in the submission.

**Primary theme — Push the Frontier.** OpenBridge explores how Meta models can inspect unfamiliar physical devices, identify verified interfaces, synthesize missing authorized capabilities, test a plan, and coordinate heterogeneous hardware. It targets the real-world challenge of giving devices new interoperable controls, rather than offering a generic AI chatbot. **Only capabilities backed by actual model, code and device evidence should be claimed as completed.**

**Secondary alignment — Build for Your World.** The project addresses a recurring problem I know personally: otherwise useful computers, phones, watches, televisions and other devices often cannot work together easily. OpenBridge seeks to translate a user's goal into safe operations across their existing hardware.

### Why it may qualify for the hackathon bonus awards

| Bonus award | Project fit | Proof or requirement to verify |
|---|---|---|
| Best Agentic Use-Case | Meta-led multi-step discovery, capability synthesis, verification, and cross-device orchestration | Run a genuine autonomous task with independent real-world result receipts and an honest baseline comparison |
| Best Build on Meta Open Weight Models | Local Muse Glimmer 30B-Q4 plans, advises and reads screens: TV Forge proposal end-to-end, 56/60 usable advisor explanations, TV visual read-back, live agent plan() | [TV Glimmer journey](docs/forge/TV_GLIMMER_JOURNEY.md) · [benchmark status](docs/benchmark/STATUS.md) · digest-pinned provenance in [src/ai/glimmer.py](src/ai/glimmer.py), models on local Ollama |
| Best Creative Build | Potential creative, user-facing UI or media experience with Muse Image or Muse Wonder | Demonstrate an original **working** integration with an eligible model, rather than static AI-generated decoration |
| Most Viral Project | A clear and surprising real-device demonstration is understandable to a wide audience | Publish and submit an authentic post on X and follow the official measured engagement window |
| Community Vote | A usable product and reproducible public demonstration can appeal to other participants | Submit a working accessible gallery entry; follow the verified-account voting rules |

These are **candidate award alignments, not organizer-confirmed eligibility or promises of prizes**. The organizer's decisions and the official final rules control.

### Verified device compatibility

OpenBridge maintains a [living hardware compatibility matrix](docs/HARDWARE_TEST_MATRIX.md), updated as devices are enrolled, tested, changed or regressed. Records distinguish **physical hardware**, **full guest operating systems**, **official emulators**, **protocol simulators**, **emulator-host adapters** and **mocks**. Only operations that passed independent verification are labeled verified. A simulated or emulated device must never be counted as an independently verified physical device.

To reproduce the latest results, consult the [release evidence](docs/RELEASE_EVIDENCE.md), [known limitations](docs/KNOWN_LIMITATIONS.md) and commit-specific test receipts. Links must be reconciled with the actual repository before publishing; do not publish a broken link or a claim without an existing source.

### Competition evaluation

- **Impact (30%)** — cross-device workflows that solve an observable real problem.
- **Use of Meta AI Tooling (25%)** — traceable Meta-driven capability synthesis and orchestration beyond predetermined macros.
- **Technical Depth & Execution (20%)** — authorization, independent postcondition checks, idempotency, lifecycle resilience and accurate failure handling.
- **Demo (25%)** — a repeatable, real-device demonstration with a visible result and a transparent account of what was built during the event.

The runtime language-model intelligence uses **Meta models only**. Development-time assistants, if used for review or code support, are not included as runtime model providers.

### Event-built evidence (30 Oct, main `73cfef5`)

Sealed held-out skill synthesis on a real TV ([REVEAL](docs/evidence/v4/g3-sealed/attempt3_SUCCESS/REVEAL.md), 2 KILLs retained); Companion 0.11.0 full-control cycle + PAIRED/READY on [device:phone-companion-01], [device:tv-companion-01] and [device:watch-sm-l310-01] (signed watch pair); [device:pc2-windows-agent] binary swap hash-verified; [device:vacuum-tuya-01] facts + seek beep; [device:freebox-delta-01] leases + inventory; agent protocol on [device:vm-deb12-01], [device:vm-ub22-01], [device:vm-arm64-01]; legacy agent on XP SP3 + Win7 SP1 QEMU guests (VMs deleted, trace kept); [device:phone-s7-media-01] live capture/send/montage; [device:avd-ob-pixel-01] official emulator adb proof. Full list in the [device registry](docs/DEVICE_EVIDENCE.json) (24 VERIFIED rows).
<!-- OPENBRIDGE_HACKATHON_PRESENTATION_END -->

## The problem
Homes are full of devices on different transports (USB, Wi-Fi, LAN, Bluetooth) behind different permission screens. Tools either see one transport at a time or ask for broad control. Owners cannot tell what is really connected, what each device can do, and whether a change can be undone.

## What OpenBridge does
1. **Discovers** with bounded, read-only providers: mDNS/DNS-SD, SSDP, ADB (USB and Wi-Fi), the **ISP Router API (e.g., Freebox OS / UPnP-IGD)** — Freebox OS with official app authorization, or a generic read-only UPnP-IGD gateway — Bluetooth LE, and **relays**.
2. **Builds one graph.** Observations merge only on strong identifiers (for example the TV's Bluetooth address seen both over mDNS and ADB); weak signals become "possible duplicate" hints. Every link states what it grants: *observe*, *read* or *control*.
3. **Extends reach through relays.** The OpenBridge Companion app (Android phone or Android TV) performs short signed BLE scans for the PC, after on-screen pairing. Devices it hears appear under it as observe-only.
4. **Uses Meta models where they help.** Muse Glimmer and Llama 3.2 run locally; they explain device state, propose at most one reversible step, and suggest the next discovery step. They never see identifiers and cannot bypass the deterministic gate.
5. **Changes only what it can undo.** Consent → snapshot → execute → independent read-back → exact Undo, with crash recovery. A session journal asks before finishing whether to restore every setting changed during the session.
6. **Routes skills across relays (B2).** Typed skill contracts with READY/ACTIVE/STANDBY states, freshness leases, AUTO/PREFERRED/PINNED policies, consent-bound invocation leases and exact-once dedup. A TV-to-phone BLE failover is demonstrated on hardware ([handover](docs/release/COMPLETE_HANDOVER.md)); a frozen synthetic routing evaluation scores 32/32 with full baselines ([results](docs/evaluation/routing-v1/RESULTS.md)).
7. **Asks in natural language (Ask OpenBridge).** English or French requests resolve to registered skills through tiered Meta-only inference; every step (parse → preview → approval → receipt) is shown with model, cost and evidence, and the model can never authorize its own privileged actions.
8. **Runs headless from a terminal.** The `openbridge` CLI drives the same core as the GUI (devices, ask, capabilities, workflows, approvals, evidence, doctor) with identical contracts and consent, over SSH or on machines with no display. See [CLI reference](docs/CLI_REFERENCE.md) and [headless deployment](docs/HEADLESS_DEPLOYMENT.md).

## Verified on real hardware
| Capability | Evidence |
|---|---|
| mDNS discovery of the home LAN (Freebox, TVs, Cast, AirPlay, HomeKit, SMB) | [EVIDENCE_LEDGER](EVIDENCE_LEDGER.md) |
| Freebox official app authorization + read-only LAN inventory (127 known / 12 active hosts) | [Freebox doc](docs/FREEBOX_INTEGRATION.md) |
| Android phone (USB) and Android TV (ADB Wi-Fi) inspection, tolerant per-fact reads | [Hardware matrix](docs/HARDWARE_TEST_MATRIX.md) |
| Bluetooth relay through a phone (9–13 advertisers) and through a TV over the LAN (6) | [Relay security](docs/RELAY_SECURITY.md) |
| Consent-gated agent: Meta plan → gate → act → verify → exact Undo | [agent-loop-receipt](docs/agent-loop-receipt.json) |
| Server crash after a change → planning blocked → exact journal recovery | [crash-recovery-receipt](docs/crash-recovery-receipt.json) |
| Muse Glimmer 30B local inference, digest = official registry manifest | [glimmer receipt](docs/glimmer-smoke-receipt.json) |
| Real TV relay → local Muse Glimmer proposal → verified API publication/read → access denial and removal | [TV/Meta journey and limits](docs/forge/TV_GLIMMER_JOURNEY.md) |
| Session restore of pre-session settings (TV system app, Companion, ADB Wi-Fi) | [Transactions & Undo](docs/TRANSACTION_AND_UNDO.md) |
| TV-to-phone BLE failover on hardware (TV scan VERIFIED → link_down → phone scan VERIFIED, dedup + consent-void proofs) | [Complete handover](docs/release/COMPLETE_HANDOVER.md) |
| Watch hold → single TV action with independent read-back and revocation | [Watch acceptance](docs/release/WATCH_CONTROL_ACCEPTANCE.md) (2-tap/16-action root cause unproven; dup/expiry hardware proof pending) |
| Frozen synthetic routing evaluation: router 32/32, full baselines, Spark pre-run design review | [Results](docs/evaluation/routing-v1/RESULTS.md) (no model-advantage claim) |
| Ask OpenBridge NL → skill resolution (local Llama parse, tiered routing, fingerprint-bound approve/execute) | Live-verified on 18765 (real parse/approve/execute, incl. fabric.status READ of 3 devices) + phone→PC→phone signed loop + fixtures e2e; cloud path unit-tested only |
| Phone hardware facts + task ranking + micro-benchmarks, measured live | §9 merged `2ad4688`; PC1 + BV9300 live runs |
| Android permission states measured + grant flow re-verified live | §10 merged `f1c460c`; 13-entry catalog on BV9300 |
| Multi-device screenshots routed + combined via DAG workflows | [Live USB proof](docs/evidence/s7-live-usb-30oct.md) (1080×2388 capture, hash-identical send, 2160×2388 montage) |
| Official Android emulator driven via adb (capture/probe/send + cleanup) | [AVD proof](docs/evidence/avd-ob-pixel-30oct.md) (level 4, no companion installed) |

Status vocabulary and everything not verified: [HARDWARE_TEST_MATRIX](docs/HARDWARE_TEST_MATRIX.md), [KNOWN_LIMITATIONS](docs/KNOWN_LIMITATIONS.md).

## What Meta models add — measured results

**Muse Glimmer adds explanations of the device graph and a proposed next step.** In the recorded coverage-advisor evaluation, **56/60 synthetic cases (93.3%) passed the usable-explanation checks**, versus 0/60 for Llama 3.2 3B. The fixed-priority rules baseline emits a step ID, not an explanation. This measures output validity and grounding checks, not complex-diagnosis correctness or a capability impossible for rules.

| Task and metric | Rules baseline | Llama 3.2 3B | Muse Glimmer 30B |
|---|---|---|---|
| Coverage advisor: usable explanation (60 synthetic cases) | No explanation output; not scored | 0/60 (0%) | **56/60 (93.3%)** |
| Coverage advisor: selected step matches fixed goal priority | 100% by construction | 0% | 53.3% |
| Narrow agent planning: correct decision (30 cases × 3) | 90.0% | 53.3% | 86.7% |
| Unsafe packages proposed in those 90 attempts (all refused) | 9 | 6 | 3 |

**Models explain and propose; deterministic code retains authorization, consent, validation and execution.** Glimmer produced fewer unsafe package proposals than the naive rules baseline in this run, while rules retained higher narrow planning accuracy. All recorded unsafe proposals were refused. These synthetic results do not establish a general model advantage. Full methodology and unfavorable results remain in [benchmark status](docs/benchmark/STATUS.md) and the [raw advisor receipt](docs/benchmark/advisor-benchmark-glimmer.json).

**Meta on real devices:** a real Android TV relay observed four BLE advertisers; local Muse Glimmer generated a validated Forge proposal, followed by owner-authorized consent in the test-driven UI, verified API publication/read and access removal. The recorded proposal used 259 input / 98 output tokens in 82.4 seconds, with $0 provider cost. This is an end-to-end proof, not a new benchmark or a demonstration of fresh human Android permission-dialog acceptance. [Journey, unsuccessful attempts and limits](docs/forge/TV_GLIMMER_JOURNEY.md).

**Meta Model API:** Muse Spark 1.3 has a [recorded successful synthetic advisory call](docs/runtime-meta-receipt.json), separate from its disclosed visual-design contribution. The experimental multi-transport diagnostic is documented in [Capability Forge PR #1](https://github.com/toskaman/openbridge/pull/1). Its first live attempt was blocked; a subsequent supervised synthetic run returned evidence-linked hypotheses and ordered read-only checks ([successful Spark diagnostic](docs/forge/SPARK_DIAGNOSTIC.md), 349/2,999 tokens, ~$0.0132 promotional). No diagnostic-accuracy score is claimed.

Current release status and remaining acceptance gates: [release index](docs/RELEASE_STATUS.md) and [submission worksheet](docs/release/SUBMISSION_EVIDENCE.md).

Runtime models are Meta only, enforced by [src/ai/registry.py](src/ai/registry.py): Llama 3.2 3B (local, CPU), Muse Glimmer 30B (local, GPU/CPU), Muse Spark 1.3 (cloud, synthetic facts only, recorded call). Built with Llama; Llama 3.2 Community License. Development assistants (Codex, Muse Spark design) are never called at runtime — see [CONTRIBUTIONS](CONTRIBUTIONS.md).

## What's new (30 Oct 2026)
- **Companion 0.11.0 everywhere**: live flow overlay + pill-icon buttons; installed and PAIRED/READY-verified on phone, Android TV and Galaxy Watch7 (signed watch pair `relay-39f86439fbae`). Homepage screenshots still show 0.10.0 (29 Oct captures) — the 0.11.0 flows are verified, not yet reshot.
- **Legacy Windows proven, then cleaned**: legacy C agent (subsystem 5.01, software SHA-256/HMAC) ran mutual-auth + RPC exec on real XP SP3 + Win7 SP1 QEMU guests with screenshots; VMs deleted after proofs, trace kept in [legacy evidence](docs/evidence/vm-legacy-xp-win7-30oct.md) and the [registry](docs/DEVICE_EVIDENCE.json) (15 VERIFIED rows).
- **P0 hardening batch (PR126–PR130, PR135)**: point-of-dispatch full-control recheck, pairing attempt limits, crash-safe invocation journal with honest UNCERTAIN, supervised STT worker, HTTP-level relay-scan verification, idempotency keys + journal claims on HTTP execute and direct intents.
- **Device connect (PR133)**: hardware agent matrix (correct agent per hardware), auto connection planner, per-device connect tutorials and guided agent pick.
- **ESP32 P1**: native IDF agent VERIFIED on QEMU-ESP32 (registry row 16: AUTH + ping + execs + cross-device CROSS_OK via serial gateway); Arduino build keeps the physical WiFi/TFT path.
- **Capability explorer (§6)**: UI schemas matched to live device capabilities (2 cards/118 widgets smoke).
- **Hardware intelligence (§9)**: PC facts + task rankers + micro-benchmarks, live on PC1 + phone.
- **Permissions center (§10)**: 13-entry catalog with measured states + grant flow, live re-verified.
- **Eval-kit baseline (§11)**: 1,000 French turns replayed (200/200 convs, 0 crashes/sends); rules cover 1.4%, model tiers pending.
- **Multi-device orchestration (§7)**: DAG workflows (parallel, approvals, partial failure, durable receipts) + 9 media/file/action skills; live USB capture/send/montage (registry row 17).
- **Official Android emulator (§12)**: Pixel 6 AVD on WHPX driven via adb — capture/probe/hash-verified send + cleanup (registry row 18).
- Full suite 1064 green on Windows + Linux CI.

## What's new (29 Oct 2026)
- **Sealed held-out skill synthesis (G3)**: commit-reveal spec, Muse Spark 1.3 composes a TV skill the system never had — compile → grant → act → independent verify → owner restore → revoke, loop `300000 → 60000 → 300000` on live hardware, $0.0203 over 3 calls, 2 KILLs honestly retained ([SUCCESS reveal](docs/evidence/v4/g3-sealed/attempt3_SUCCESS/REVEAL.md)).
- **v4-synth-4**: true per-primitive input schemas in the prompt, required-input/integer enforcement in the validator, contract tests pinning both against the kernel registry.
- **Encrypted + durable relays**: AEAD-sealed relay channel (standard-crypto review) and OS-vault-held pairing keys — pairings survive server restarts with no re-typing.
- **Sealed UI publish, verified on screen**: server-driven controls install over the encrypted channel and render on the TV (Companion 0.9.0); label E2E with screen read-back.
- Companion 0.10.0 (Allow-full-control toggle + warning popup, relay AEAD, voice orb) on phone + TV; server invoke rails (PR109); full tuya surface + Freebox leases (PR111); full suite green on Windows + Linux CI.

## What's new (28 Oct 2026)
- **B2 skill routing**: typed contracts, AUTO/PREFERRED/PINNED, leases, dedup; hardware TV-to-phone handover + frozen 32/32 evaluation with Spark design review.
- **B3 Companion controls**: owner-granted watch/phone controls routed through B2 (one hold → one action, signed outcomes, revocation); hardware edge acceptance still open.
- **Ask OpenBridge**: natural-language panel (EN request UI, FR text accepted), tiered Meta-only routing, cost guard on the shared broker ledger, fingerprint-bound approve/execute.
- **Durable runtime**: routing policies + unresolved-outcome backlog survive restarts (atomic, corrupt-state blocks visibly).

## What's new (27 Oct 2026)
- **Runtime contract v1 and `/api/v2`**: a versioned read model and one execute endpoint over named safe primitives (schema, consent, identity re-check, per-device locking, honest timeouts). See `docs/api/HTTP.md`.
- **More devices, all owner-authorized**: Galaxy Watch7 (wireless-debugging pairing with an in-app tutorial), a second Windows PC through the owner's agent (read-only), Android phone and TV Companion relays feeding Capability Forge.
- **Crash-recoverable writes**: five process-kill points during a real change on the phone, each recovered from the journal with exact read-back (5/5).
- **Live Meta Model API**: `muse-spark-1.3` advisory verified live on synthetic facts within free credits; local Llama 3.2 3B and Muse Glimmer remain the default.
- **Read-only watchers and a redacted multi-device report.**
Evidence for every item: `EVIDENCE_LEDGER.md` and `docs/HARDWARE_TEST_MATRIX.md`. Limits: `docs/KNOWN_LIMITATIONS.md`.

## V4 additions (27 Oct 2026, evening) — status as of this commit
| Feature | What it does | Status |
|---|---|---|
| Cross-transport diagnosis (V4-01) | One timeline of changes from every read path; competing hypotheses that cite timeline entries ("consistent with", never "caused by"); a read-only re-measure probe | SIMULATED_VERIFIED (CI drills with independent labels); real TV+router capture pending |
| Privacy-preserving cloud escalation (V4-05) | Exact outgoing bytes, diff and categories shown before one explicit consent per payload; golden leak corpus; untrusted answer validated locally. Data minimisation, **not** anonymity | SIMULATED_VERIFIED; live call needs the supervised credit permit |
| Registered ablation (V4-04) | 24 frozen held-out cases; rules 20/24 (fails all WAN-outage cases); model arms run on the owner's PC | rules arm MEASURED; model arms pending |
| Generic UPnP-IGD (router) | Allowlisted read-only queries; port-mapping and every write refused before sending; external IP masked | SIMULATED_VERIFIED (fake IGD); real gateway pending |
| BLE zones (V4-11) | Calibrated zones from two relays, "unknown" when unsure; precision/recall per zone; never coordinates | SIMULATED_VERIFIED; owner calibration run pending |
| Visual read-back (V4-07) | Screenshot (status bar cropped) judged by local Muse Glimmer vs structured screen state; disagreement = INCONCLUSIVE | SIMULATED_VERIFIED; real TV run pending |
| Voice (V4-10) | Push-to-talk → local MMS-1B STT in a supervised worker (cloud `muse-voice-transcribe-1.0` path kept, consent-gated) → typed FR/EN intent proposal; owner reviews and presses Run | REAL_HARDWARE_VERIFIED: frozen corpus 16/16 no wrong-skill, owner voice 2/2 ([N2/N3](docs/evidence/v4/overnight/N2_N3_RESULTS.md)); worker isolation unit-verified |
| Wear OS manifest (V4-08) | Watch capabilities derived from reported features on every read; control BLOCKED | SIMULATED_VERIFIED; Watch7 run pending |
| PC 2 as a client (V4-12) | Runs owner-typed jobs (consent per command, exit code + output returned) and serves pinned Meta models for the scheduler; raw device data never leaves this PC | jobs REAL_HARDWARE_VERIFIED; inference benchmark pending |
| Tuya robot vacuum | Owner-linked via the owner's Tuya IoT project; status reads; suction/volume with exact Undo; full robot control (start, pause, dock, moves with auto-stop, seek, dust, resets) with consent per command | REAL_HARDWARE_VERIFIED: reads, suction change + exact Undo, start/pause, manual moves and return to dock (EVIDENCE_LEDGER) |

Claim-by-claim evidence: [docs/jury/CLAIM_EVIDENCE_MATRIX.md](docs/jury/CLAIM_EVIDENCE_MATRIX.md).

## Run it
Requirements: Windows or Linux, Python 3.14 (no third-party runtime packages), Android platform-tools for ADB. Optional: Ollama for local Meta models, `bleak` for PC Bluetooth.

```powershell
git clone https://github.com/toskaman/openbridge.git
cd openbridge
python -m unittest discover -s tests          # controlled tests; no hardware needed
python -m dev.start_workspace                 # main :18765 + trusted Forge selector :18767
```
With local Meta models and the agent:
```powershell
python -m dev.start_local_meta --pull-model   # Llama 3.2 3B, private CPU service on :11437
python -m dev.start_glimmer --pull-model      # optional Muse Glimmer 30B on :11438 (~18 GB)
python -m src.server --local-meta --glimmer --agent
```
The default launcher starts no discovery, model call or publication. Open **Capability Forge** from the main navigation, refresh verified routes and explicitly select a source-bound observation. Optional Forge local CPU planning uses `python -m dev.start_workspace --glimmer-cpu-v2` with its existing isolated service on :11439. The standalone simulated demo remains `python -m src.forge.demo_host` on :18766. See [trusted physical workspace proof](docs/forge/WORKSPACE_JOURNEY.md) and [frozen v2 evaluation](docs/forge/evaluation-v2/RESULTS.md).

Companion app: `python -m dev.build_companion` (official Android SDK tools), then **Install the OpenBridge Companion** from a phone or TV sheet in the UI.

**Jury walkthrough:** Ask OpenBridge a request (*Scan for bluetooth devices*) → review the fingerprint-bound preview → approve → read the receipt → Discover my environment → open a device sheet (sources, capabilities, statuses) → TV sheet: *Connect over ADB Wi-Fi* → *Use as Bluetooth relay* → *Scan nearby Bluetooth* → *Ask Meta what to do next* → Device agent (Declutter) for a consent-gated change and exact Undo → *Finish session…*. Without hardware: `python -m tests.e2e.command_center_smoke`, `python -m tests.e2e.fabric_smoke` and `python -m tests.e2e.offline_smoke` (all in CI).

## Safety boundaries
Loopback-only server with Host/Origin/CSRF checks; no port scanning; discovery limited to private networks; one owner-triggered connection per device; router/box configuration read-only by policy; Freebox token protected by Windows DPAPI; raw serials/MACs pseudonymized; signed, expiring, replay-protected relay commands; scans only after on-screen pairing and only while the Companion is open; Android permissions only through Android's own dialogs; writes limited to an allowlist with exact restoration or blocked before writing.

## Documentation
Architecture [UNIVERSAL_DEVICE_ARCHITECTURE](docs/UNIVERSAL_DEVICE_ARCHITECTURE.md) · Discovery [DISCOVERY_PROTOCOLS](docs/DISCOVERY_PROTOCOLS.md) · Identity [DEVICE_IDENTITY_AND_DEDUPLICATION](docs/DEVICE_IDENTITY_AND_DEDUPLICATION.md) · UX [DEVICE_FABRIC_UX](docs/DEVICE_FABRIC_UX.md) · Schema [DEVICE_CAPABILITY_SCHEMA](docs/DEVICE_CAPABILITY_SCHEMA.md) · Android TV [ANDROID_TV_ADAPTER](docs/ANDROID_TV_ADAPTER.md) · Companion [ANDROID_COMPANION](docs/ANDROID_COMPANION.md) · Bluetooth [BLUETOOTH_LOCAL_AND_REMOTE](docs/BLUETOOTH_LOCAL_AND_REMOTE.md) · Routers [ROUTER_ADAPTERS](docs/ROUTER_ADAPTERS.md) · Jury [JURY_ACCEPTANCE_DEVICE_FABRIC](docs/JURY_ACCEPTANCE_DEVICE_FABRIC.md) · Evidence [EVIDENCE_LEDGER](EVIDENCE_LEDGER.md), [RELEASE_EVIDENCE](docs/RELEASE_EVIDENCE.md) · Baseline [DEVICE_FABRIC_BASELINE](docs/DEVICE_FABRIC_BASELINE.md) · Earlier README [README_HISTORY](docs/README_HISTORY.md).

All code was written during the event; see [CONTRIBUTIONS](CONTRIBUTIONS.md) and [THIRD_PARTY](THIRD_PARTY.md).

## Website redesign with Meta Muse Wonder 1.0

The current visual foundation was authored by **Meta Muse Wonder 1.0** through the official Meta API on 27 October 2026: design tokens, workspace shell, and component CSS. Codex adapted the markup, wrote the integration layer, preserved existing controls, and performed verification. The original Meta-authored modules are in `src/ui/theme/`; compile them with `python -m dev.build_web_theme`.

The [generation receipt](docs/forge/meta-web-design-receipt.json) records 798 input and 3,500 output tokens, an estimated $0.073192 promotional-credit cost, and `finish_reason: length`. The final explanatory field was truncated; only the five fully decoded fields were extracted. The three complete CSS fields were retained verbatim. This is a real build-time Meta contribution, not a claim that Meta authored all application code or a new runtime model integration. No second provider request was made.

## Current application theme — owner decision, 28 October 2026

The owner selected Claude's latest application shell and main theme (`src/ui/theme/app.css`), replacing the earlier main-site Meta theme. The Forge theme and retained Spark/Wonder receipts describe their actual, separate contributions; they do not establish authorship of the new main shell. Codex integrated and tested the combined changes. No new Meta design call was made for this integration.
