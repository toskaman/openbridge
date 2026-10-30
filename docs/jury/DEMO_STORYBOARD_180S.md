# 180-second demo storyboard (30 Oct 2026)

Real captures only, names redacted. Each beat shows its status label on
screen. Record only after the listed proof exists; otherwise DROP the beat —
never simulate it. **Video BLOCKED: no recording without the owner's new
explicit authorization.**

| Time | Beat | Screen | Proof shown | Status |
|---|---|---|---|---|
| 0–10 | Problem | Empty fabric → "Discover my environment" | — | staged narration |
| 10–30 | One graph | Topology: Freebox, phone USB, TV ADB, BLE via relay, Watch7, PC2 | VERIFIED chips | REAL_HARDWARE |
| 30–55 | Orchestration | Screenshot captured, hash-verified send, 2-frame montage | receipts + sha256 match | REAL_HARDWARE (single-device loop, labeled) |
| 55–75 | Ask Meta, privately | Consent split (local vs outgoing bytes) → Spark ranking | live receipt (model, payload hash) | REAL (receipt on file) |
| 75–95 | Change only what undoes | Plan → consent → act → read-back → crash drill → exact Undo | 5/5 crash receipt | REAL_HARDWARE |
| 95–110 | Emulator lab | Pixel 6 AVD: capture/probe/send + cleanup | receipts, ls empty | EMULATOR level 4 (labeled) |
| 110–125 | RetroArch | VERSION + GET_STATUS verified replies; VOLUME_UP sent-unverified | receipts, stated honesty | REAL_HARDWARE (localhost) |
| 125–140 | Relay dashboard | Vacuum + TV controls generated, patched, saved, restored | FakeCompanion sim | SIMULATED (watch live pending) |
| 140–160 | Measured, not claimed | Rules 1.4% on 1,000 turns; ablations; G3 honest negative | reports on file | MEASURED |
| 160–175 | Boundaries + disclosure | Meta-only · read-only default · exact Undo · event-built + prototype disclosed | CONTRIBUTIONS.md | stated |
| 175–180 | Close | Title + repo link | — | — |

## Narration (one line per beat)
1. "Our homes are full of devices that can't work together."
2. "OpenBridge builds one verified graph across every transport."
3. "One workflow captures, routes and combines screens — every hop hashed."
4. "Meta models advise; you see exactly what leaves the PC before it does."
5. "Nothing changes unless the system proves it can undo it — even after a crash."
6. "The same commands drive an official emulator — labeled as emulation, always."
7. "Even the emulator on this PC answers — and unverified stays unverified."
8. "Dashboards generate, patch and restore on any relay screen."
9. "We measure honestly: rules cover hundredths of French requests; models are next."
10. "Meta-only, read-only by default — built during the event, prototype disclosed."
11. "OpenBridge — prove it before you change it."

## Recording checklist
- Devices: PC1 (server + captures), phone USB (BV9300), AVD ob-pixel on E:,
  RetroArch portable on E:. TV/watch only if back online (else drop their shots).
- Permissions: owner USB adb, owner consent taps on record, no private pixels
  (redact names, no notifications visible, airplane radios as needed).
- Provenance overlay (bottom-third, beats 3–9): model or path used
  (rules / Llama 3.2 3B / Glimmer 30B / Spark 1.3 / deterministic), commit SHA,
  receipt id. Deterministic beats say DETERMINISTIC, never a model name.
- Contribution disclosure (beat 10, 5 s card): event-built 26 Oct–4 Nov 2026;
  pre-event owner prototype rewritten as Bridge Agent v4 (see CONTRIBUTIONS.md).
- Backup evidence per beat (if live fails on the day): the committed still
  capture or receipt listed in the Proof column. Live preferred; stills are
  honest fallback, labeled as such.
- Rehearsal protocol: dry-run each beat twice (once narrated, once timed);
  total must land 175–180 s; cut list applied before the final take, never
  during. Manifest (revision, scene times, source paths) in E:/shots/manifest
  (local only).

Cut list if a beat is not proven by recording day: drop it, keep the timing
of the others, never replace with mock-ups.
