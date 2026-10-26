# OpenBridge — Device Fabric

**Local Meta AI that understands the devices around you, reaches the ones your PC can't, and only changes what it can prove it can undo.**

Meta Global AI Developer Hackathon 2026 · Indie Developer · *Push the Frontier* · MIT licence

![Real Device Fabric run, household names redacted](docs/jury/screens/fabric-tv-relay-redacted-1440.png)

*Real run on the author's home network (names redacted with `?redact`): a Freebox and the 12 active hosts it reports, an Android phone over USB, an Android TV over ADB Wi-Fi merged with its mDNS identity, and 6 Bluetooth devices that the PC cannot hear itself (it has no Bluetooth radio) found through the TV acting as a relay.*

## The problem
Homes are full of devices on different transports (USB, Wi-Fi, LAN, Bluetooth) behind different permission screens. Tools either see one transport at a time or ask for broad control. Owners cannot tell what is really connected, what each device can do, and whether a change can be undone.

## What OpenBridge does
1. **Discovers** with bounded, read-only providers: mDNS/DNS-SD, ADB (USB and Wi-Fi), the Freebox OS API (with official app authorization), Bluetooth LE, and **relays**.
2. **Builds one graph.** Observations merge only on strong identifiers (for example the TV's Bluetooth address seen both over mDNS and ADB); weak signals become "possible duplicate" hints. Every link states what it grants: *observe*, *read* or *control*.
3. **Extends reach through relays.** The OpenBridge Companion app (Android phone or Android TV) performs short signed BLE scans for the PC, after on-screen pairing. Devices it hears appear under it as observe-only.
4. **Uses Meta models where they help.** Muse Glimmer and Llama 3.2 run locally; they explain device state, propose at most one reversible step, and suggest the next discovery step. They never see identifiers and cannot bypass the deterministic gate.
5. **Changes only what it can undo.** Consent → snapshot → execute → independent read-back → exact Undo, with crash recovery. A session journal asks before finishing whether to restore every setting changed during the session.

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
| Session restore of pre-session settings (TV system app, Companion, ADB Wi-Fi) | [Transactions & Undo](docs/TRANSACTION_AND_UNDO.md) |

Status vocabulary and everything not verified: [HARDWARE_TEST_MATRIX](docs/HARDWARE_TEST_MATRIX.md), [KNOWN_LIMITATIONS](docs/KNOWN_LIMITATIONS.md).

## Meta AI — honest evaluation
| Task | Rules only | Llama 3.2 3B | Muse Glimmer 30B |
|---|---|---|---|
| Agent planning (30 cases × 3) correct | 90.0% | 53.3% | 86.7% |
| Unsafe packages proposed (all refused by the gate) | 9 | 6 | 3 |
| Coverage advisor usable explanation | n/a | 0% | 93.3% |

The deterministic gate guarantees safety (100% of unsafe proposals refused); a simple rule decides as well as the models on these narrow tasks; Glimmer's value is grounded explanation and fewer unsafe proposals. Unfavourable results are kept: [benchmark/STATUS](docs/benchmark/STATUS.md), [model usage](docs/MODEL_USAGE_AND_EVALUATION.md).

Runtime models are Meta only, enforced by [src/ai/registry.py](src/ai/registry.py): Llama 3.2 3B (local, CPU), Muse Glimmer 30B (local, GPU/CPU), Muse Spark 1.3 (cloud, synthetic facts only, recorded call). Built with Llama; Llama 3.2 Community License. Development assistants (Claude, Codex, Muse Spark design) are never called at runtime — see [CONTRIBUTIONS](CONTRIBUTIONS.md).

## Run it
Requirements: Windows or Linux, Python 3.14 (no third-party runtime packages), Android platform-tools for ADB. Optional: Ollama for local Meta models, `bleak` for PC Bluetooth.

```powershell
git clone https://github.com/toskaman/openbridge.git
cd openbridge
python -m unittest discover -s tests          # 170+ tests, no hardware needed
python -m src.server                          # http://127.0.0.1:18765
```
With local Meta models and the agent:
```powershell
python -m dev.start_local_meta --pull-model   # Llama 3.2 3B, private CPU service on :11437
python -m dev.start_glimmer --pull-model      # optional Muse Glimmer 30B on :11438 (~18 GB)
python -m src.server --local-meta --glimmer --agent
```
Companion app: `python -m dev.build_companion` (official Android SDK tools), then **Install the OpenBridge Companion** from a phone or TV sheet in the UI.

**Jury walkthrough:** Discover my environment → open a device sheet (sources, capabilities, statuses) → TV sheet: *Connect over ADB Wi-Fi* → *Use as Bluetooth relay* → *Scan nearby Bluetooth* → *Ask Meta what to do next* → Device agent (Declutter) for a consent-gated change and exact Undo → *Finish session…*. Without hardware: `python -m tests.e2e.fabric_smoke` and `python -m tests.e2e.offline_smoke` (both in CI).

## Safety boundaries
Loopback-only server with Host/Origin/CSRF checks; no port scanning; discovery limited to private networks; one owner-triggered connection per device; router/box configuration read-only by policy; Freebox token protected by Windows DPAPI; raw serials/MACs pseudonymized; signed, expiring, replay-protected relay commands; scans only after on-screen pairing and only while the Companion is open; Android permissions only through Android's own dialogs; writes limited to an allowlist with exact restoration or blocked before writing.

## Documentation
Architecture [UNIVERSAL_DEVICE_ARCHITECTURE](docs/UNIVERSAL_DEVICE_ARCHITECTURE.md) · Discovery [DISCOVERY_PROTOCOLS](docs/DISCOVERY_PROTOCOLS.md) · Identity [DEVICE_IDENTITY_AND_DEDUPLICATION](docs/DEVICE_IDENTITY_AND_DEDUPLICATION.md) · UX [DEVICE_FABRIC_UX](docs/DEVICE_FABRIC_UX.md) · Schema [DEVICE_CAPABILITY_SCHEMA](docs/DEVICE_CAPABILITY_SCHEMA.md) · Android TV [ANDROID_TV_ADAPTER](docs/ANDROID_TV_ADAPTER.md) · Companion [ANDROID_COMPANION](docs/ANDROID_COMPANION.md) · Bluetooth [BLUETOOTH_LOCAL_AND_REMOTE](docs/BLUETOOTH_LOCAL_AND_REMOTE.md) · Routers [ROUTER_ADAPTERS](docs/ROUTER_ADAPTERS.md) · Jury [JURY_ACCEPTANCE_DEVICE_FABRIC](docs/JURY_ACCEPTANCE_DEVICE_FABRIC.md) · Evidence [EVIDENCE_LEDGER](EVIDENCE_LEDGER.md), [RELEASE_EVIDENCE](docs/RELEASE_EVIDENCE.md) · Baseline [DEVICE_FABRIC_BASELINE](docs/DEVICE_FABRIC_BASELINE.md) · Earlier README [README_HISTORY](docs/README_HISTORY.md).

All code was written during the event; see [CONTRIBUTIONS](CONTRIBUTIONS.md) and [THIRD_PARTY](THIRD_PARTY.md).
