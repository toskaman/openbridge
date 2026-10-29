# Phase 0 audit (Claude, systems/platform) — main eae305c, 29 Oct 2026

Grounded in the code at `eae305c` (CI green on the last three main runs), the local suite (774 tests OK, 1 skip after
this branch) and hardware runs today. Older planning documents were not taken as truth.

## What exists and is verified
| area | state | evidence |
|---|---|---|
| Trust kernel (`src/substrate`) | obv4.1 contract, 24 typed primitives (17 runnable, 7 HYPOTHESIS/BLOCKED), compile → owner HMAC grant → invoke with per-step re-checks → signed receipts, revocation, atomic operation ids | unit tests; Sol S4/S5 closed |
| Meta → hardware (G3) | Muse Spark 1.3 candidate → effect binding → compile → grant → physical invoke → independent oracle → restore → revoke → refusal | `docs/evidence/v4/g3-smoke/attempt4_SUCCESS.json` (integration smoke, public target) |
| Sealed held-out tasks | commit-reveal spec, generic runner, candidate pool | `docs/forge/G3_SEALED_TASK_PROTOCOL.md`; awaiting Sol's commitment |
| Dynamic device UI | **v2 this branch**: label/status/button/confirm, revision ACK, status push, persistence, revocation | `docs/evidence/v4/ui-v2/RESULT.md` (Android TV) |
| Command Center | NL parse (Meta tiers), approve/execute, atomic per-intent claim, single paid cloud send | tests; S1 closed |
| Relays / routing (B2/B3) | signed relay channel (HMAC, nonce, expiry), AUTO/PINNED routes, at-most-once presses | earlier transcripts |
| Voice | device clip → paired PC → local Meta MMS-1B, no cloud | Muse PR86/90 evidence |

## Defects found and fixed today (hardware-driven)
1. **Companion crashed on Android TV** (#92 rewrite): `VoiceOrbView` RadialGradient radius ≤ 0 → FATAL at launch, pairing impossible. Fixed `37a89fc`.
2. **Relay offline forever after a Companion restart**: one failed poll removed the relay from polling; queued presses were never fetched. Fixed `cb20adb` (bounded re-probe) + regression test; re-verified on the TV.

## Gaps against the platform brief (honest status, prioritized for 4 Nov)
| gap | status | plan |
|---|---|---|
| Multi-device workflows | **done on this branch**: `src/substrate/workflow.py`, owner-signed DAG, parallel across devices, skip-on-failure, cancel, signed receipts; TV+phone hardware run in `docs/evidence/v4/workflow` | next: Muse planner emits `obv4.1-wf`; durable workflow journal |
| Transport confidentiality | relay messages are authenticated (HMAC) but **not encrypted**; voice clips plaintext on LAN | P1: AEAD envelope (key derived from the pairing key), version-negotiated |
| Relay pairing persistence | relays live in server memory; a server restart needs re-pairing | P1: durable relay store (key wrapped by the vault), corrupt-state fail-closed |
| Companion lifecycle | relay runs only while the app is open (no foreground service); Wear OS uses the same phone APK | P2: foreground service with visible notification; Wear-specific layout pass |
| File transfer, screen capture, contacts, calls | registry HYPOTHESIS only; nothing implemented | P1 file transfer (chunked, SHA-256, resume) then capture (MediaProjection consent); calls stay exploratory (remote-mic probe already negative) |
| Windows companion | BridgeWindows lives outside the repo (unversioned); not audited here | P2: audit before integrating |
| Watch | offline today; v2 renderer not yet run on the Galaxy Watch7 | rerun the ui-v2 driver when it is reachable |

## Not done on purpose
No change to protected files, frozen evaluations, the sealed-task protocol or Muse's prompt. No Claude runtime
dependency. Screenshots were not used as evidence; the UI was verified through the accessibility tree (uiautomator).
