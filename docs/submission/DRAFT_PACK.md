# OpenBridge — submission pack DRAFT (owner submits; do not file from this doc alone)

Track: Indie Developer. Theme: Push the Frontier (secondary: Build for Your World).
Deadline: 4 Nov 2026, 9:00 PM ET (verify on the official portal before filing).
Pack state: 29 Oct 2026 evening, main `13e56ab` (PR117 merged, 0 open PRs, suite 841 green).

## One line
OpenBridge is a local-first device fabric: ask in plain language from PC or
phone, Meta models draft the understanding, deterministic gates verify, and the
owner approves every action.

## What is demonstrated (all evidenced in-repo)
- Ask OpenBridge P0: EN/FR natural language → registered skill → fingerprint-bound
  preview → approve → exactly-once execute. Live-verified with real local Llama
  (`docs/jury/screens/ask-openbridge-*.png`).
- Companion 0.10.0 with Allow-full-control: on-device master switch, warning
  popup, instant revoke; popup→allow→revoke→cancel cycle proven on a real phone
  via uiautomator dumps; flag reported on the signed wire channel
  (`docs/release/COMPANION_0_10_0.md`, `docs/jury/screens/companion-0-10-*.png`).
- Voice: companion push-to-talk (AudioRecord PCM16) → paired PC only → local
  MMS-1B STT (no cloud); STT→parse 16/16 no wrong-skill on the frozen corpus;
  owner human voice 2/2 (`docs/evidence/v4/overnight/N2_N3_RESULTS.md`).
- Real fabric run: 24 devices, Freebox-authenticated, 2 paired relays, redacted
  capture (`docs/jury/screens/fabric-tv-relay-redacted-1440.png`).
- Capability Forge agent layer (V4): Meta models propose new device
  capabilities as strict JSON manifests; evidence binding, primitive allowlists,
  model-identity checks, UI-schema patches, frozen exclusions and proof receipts
  are enforced in code (`src/forge/v4_*.py`, 40+ focused tests).
- **G3 sealed held-out run: SUCCESS (29 Oct).** Commit-reveal spec, 3 attempts
  with 2 honestly retained KILLs, Muse Spark 1.3 (v4-synth-4) → compile → grant
  → act on live TV → independent verify → owner restore → revoke ($0.0203).
  Seal was same-party (Spark), disclosed as weakened held-out:
  `docs/evidence/v4/g3-sealed/attempt3_SUCCESS/REVEAL.md`.
- Spark-vs-local safety finding (N4, 4 broker-guarded calls): Spark abstains on
  unregistered capabilities (lamp, TV pause) where llama 3B confabulates or
  over-resolves — high tier is a registry-safety gain
  (`docs/evidence/v4/overnight/N4_RESULTS.md`).
- Peripheral depth: full 12-command tuya surface, vacuum facts + seek beep on
  hardware, Freebox static leases + 127-host inventory (PR111).
- Multi-PC + multi-OS: second PC binary swap hash-verified; agent wire protocol
  proven on Debian 13 (x2), Debian 12, Ubuntu 22.04, Debian 13 ARM64
  (`docs/evidence/vm-fleet-29oct.md`).
- Frozen evaluations with honest negatives: routing 32/32; explanations v1 0/8
  content (reasoning exhaustion at 800 tokens), v2 3/8 content, 26 SUPPORTED / 0
  UNSUPPORTED sentences (`docs/evaluation/routing-v1/`).
- Machine-readable device registry + generated matrix, CI-gated
  (`docs/DEVICE_EVIDENCE.json`, `docs/HARDWARE_TEST_MATRIX.md`).

## Meta AI use (substantive, exclusive in production inference)
- Llama 3.2 3B (local, Ollama): NL parsing + candidate drafting; every live
  parse cites the model id in machine-readable provenance.
- Muse Glimmer 30B (local): medium tier; honestly reported UNUSABLE on this box
  (30b-q4 needs 12.8 GB CUDA, 10.8 GB free; OOM → honest `escalation_required`)
  — never simulated.
- Muse Spark 1.3 (hosted, explicit consent + broker-guarded spend): high tier,
  frozen explanation evals, G3 synthesis. Ledger: $2.00 global cap; sealed G3
  total $0.0203 over 3 calls. Every cent receipted in `LOCALAPPDATA/OpenBridge/budget.sqlite3`.
- Muse Wonder: build-time design receipt only (main shell replaced since, as
  documented) — not a runtime claim, Best Creative Build not entered.
- Non-Meta assistants were used for development only, never for production inference.

## Honest limits (state on the form)
- Sealed G3 seal was same-party (Spark substituted for unavailable Sol);
  mechanics + honesty proven, held-out novelty weakened — disclosed in REVEAL.
- Watch Companion 0.9.0 installed, PAIRED/READY verified; signed wire probe
  UNVERIFIED (transport dropped at 4% battery); 0.10.0 not yet on watch.
- Android Companion NOT tested in any VM (VM proofs are agent-protocol only).
- XP blocked (no product key), Win7 blocked (no media), x86 guest unstaged.
- Small eval samples; no victory claims.

## Demo script (live-first, ~5 min)
1. Ask panel: "How many devices are online" → preview → approve → READ.
2. Phone Companion 0.10.0: show Allow-full-control popup → Allow → revoke.
3. Voice: push-to-talk on phone → local STT → parse → report (needs ≥6 GB free RAM).
4. G3 sealed: show REVEAL + TV loop on demand (supervised).
5. Screenshots + receipts as fallback if any hardware sleeps. No video
   substitution without an explicit owner request.

## Portal checklist (owner)
- [ ] Title, one-liner, track/theme above.
- [ ] Repo URL + commit hash of the filed tree (fill at filing time).
- [ ] Screenshots: `docs/jury/screens/` PNGs (ask-openbridge-*, companion-0-10-*,
      fabric-tv-relay-redacted-1440).
- [ ] Video: only if owner requests it (live demo is primary).
- [ ] Confirm deadline/timezone on the official page day-of.
