# OpenBridge — Verified capabilities (31 Oct 2026)

Source of truth for what works today. Every verdict maps to the
[claim matrix](CLAIM_EVIDENCE_MATRIX.md) and the [registry](../DEVICE_EVIDENCE.json)
(30 rows: 21 REAL_HARDWARE, 7 FULL_GUEST_OS, 2 OFFICIAL_PLATFORM_EMULATOR).

Status words: VERIFIED REAL HARDWARE · VERIFIED EMULATOR/FULL-GUEST ·
VERIFIED UNIT/INTEGRATION/SIMULATED · IMPLEMENTED NOT VALIDATED ·
EXPERIMENTAL · PLANNED · BLOCKED/KNOWN LIMITATION.

## Scenario A — AI-created controls (TV panel → vacuum)

**IMPLEMENTED, NOT YET FULLY VALIDATED.** Dispatch + revocation are
VERIFIED REAL HARDWARE; the full story (manual press + observed motion) is not.

- Glimmer 30B panel installed on a real TV, 4/4 controls bound, OCR-verified
  render, hold-press dispatched (tx-ab731d7b885b5e1a), revoke→deny VERIFIED —
  VERIFIED REAL HARDWARE ([S5](../evidence/s5-tv-panel-31oct.md), row 28).
- T2 seek chain with 15-poll oracle + revoke + relay_revoke — VERIFIED REAL
  HARDWARE ([S5b](../evidence/s5b-safe-seek-31oct.md), row 30).
- Gaps: presses ADB-injected (labeled); vacuum docked/cleaning, motion never
  observed; n=1. Manual-press + motion runs are owner-gated
  ([runbook](DEMO_PHYSICAL_RUNBOOK.md)).

## Scenario B — Devices extending each other (BLE relay)

**VERIFIED REAL HARDWARE.** A PC with no Bluetooth reaches BLE devices through
phone/TV relays; a proven TV-to-phone handover keeps scans alive across relay
loss, with dedup + consent-void proofs
([handover](../release/COMPLETE_HANDOVER.md), rows 25/29).
This is routed, consented capability — not mere detection.
Limits: one TV model, foreground scans by design, Doze soak untested.

## Scenario C — Control from different screens

**PARTIAL — per surface, not every action everywhere.**

- Phone / TV / Watch7 Companion: installed, paired, operational, controls
  rendered, commands dispatched — VERIFIED REAL HARDWARE
  ([G04](../evidence/g04-watch-30oct.md), rows 22–25, 29).
- Watch cross-device chain (manual press → second device obeys → read-back):
  IMPLEMENTED, owner run PENDING ([runbook](DEMO_PHYSICAL_RUNBOOK.md) §6).
- 2nd Windows PC jobs: VERIFIED REAL HARDWARE (plaintext v4 caveat applies).
- ESP32: native IDF agent VERIFIED EMULATOR (QEMU serial + CROSS_OK); WiFi,
  TFT, and physical run pending ([row 16](../evidence/esp32-idf-qemu-30oct.md)).
- Playdate (simulator steps 1/2/4, no registry row): EXPERIMENTAL. Tizen/webOS,
  Minitel, C64, Game Boy, Palm, Pebble/Garmin, TI-84: PLANNED
  ([catalog](../KNOWN_LIMITATIONS.md)).

## Scenario D — Safe AI execution

**VERIFIED REAL HARDWARE for journaled scope.** Request → Meta reasoning →
validation → preview → consent → execution → read-back → receipt → eligible
undo or revocation. Meta proposes; deterministic gates authorize.
Journaled setting changes replay with RESTORED/FAILED/MANUAL verdicts;
physical acts (dock, volume, moves) are labeled non-undoable before approval
and have no Undo. Refusals render in the timeline (TDD 3/3).
Crash drill 5/5; idempotency refuses re-execution (honest UNCERTAIN).

## Meta model contributions (what rules alone don't do)

Without Meta inference, nothing understands requests, nothing composes new
controls, and nothing explains devices — the fabric would be static plumbing.
Measured contributions:

- Capability selection + single-step control proposals (local Glimmer/Llama,
  digest-pinned, `authorizes_execution: false`) — VERIFIED (code + receipts).
- Device-state explanations users can act on (56/60 usable, Glimmer) —
  VERIFIED SIMULATED (synthetic eval, published with misses).
- Not Meta-implemented: state-explanation rephrase (rules-only), orchestration
  (deterministic DAG), runtime dashboards (store CRUD). Build-time Meta design
  (Spark/Wonder receipts) is disclosed separately, never as runtime use.

## Vision platforms (honest split)

Working today: Android phone/TV/Watch7, Windows/Linux/macOS hosts, Freebox,
Tuya vacuum, QEMU Linux + legacy Windows guests, Pixel AVD, ESP32-QEMU.
Everything else in [the catalog](../KNOWN_LIMITATIONS.md) is a named plan
with a 5-step promotion pipeline — no registry row until all five pass.

## Vision: Meta-driven discovery (future, not claimed)

Today Meta *guides* discovery: the coverage advisor proposes the next
discovery step and NL routing resolves what the user asks for — the probing
itself (mDNS/SSDP/ADB/BLE) is deterministic. The roadmap is Meta *driving*
discovery loops: the model deciding what to probe next across transports,
which relay to task, and when evidence is sufficient — still fenced by the
same deterministic gates, consent, and receipts. Stated as direction only:
no timeline promised, no current result presented as such.
