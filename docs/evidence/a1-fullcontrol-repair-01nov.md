# A1 Android full_control reset — fix + validation status (01-Nov-2026 evening)

## The bug (security review A1)

`RelayServer.confirmPairing()` stored the fresh pairing key without
resetting the `full_control` pref. Any (re-)pairing NOT preceded by
`unpair()` — process death, key loss, backup/restore — silently restored
full control with no fresh owner consent. (`unpair()` itself already
cleared the pref; only the pair-accept path was missing the reset.)

## The fix

`companion/android/.../RelayServer.java`, `confirmPairing()` (1 pref +
comment): a fresh pairing now forces `full_control=false`. The owner
re-allows it explicitly in-app (`toggleFullControl` dialog), as before.
One-directional, minimal, mirrors `unpair()`.

- Compiles: `dev/build_companion.py` (SDK `E:/Android/sdk`,
  build-tools 34.0.0, android-34) → `artifacts/companion/
  openbridge-companion.apk`, 345638 bytes,
  sha256 `f8ca9ae08e6553e31638d51c71af1e4f56d576f7ff4a301d72aed2654441d09c`.
- Instrument: `dev/a1_repair_probe.py` — pair → expect False → UI-grant
  Allow → True → force-stop WITHOUT unpair → re-pair → MUST be False →
  white-box pref read → UI re-allow → True → bounded Doze force-idle
  check → UI unpair → gone. Transcript to `E:/shots/a1-emu/`.

## Local emulator validation: BLOCKED by a host-side VM killer

6 controlled boots of `ob-pixel` (API 34, WHPX operational), all with
`-no-window -no-snapshot`:

| # | Flags | Result |
|---|---|---|
| 1 | `-gpu swiftshader_indirect` | boot OK, install OK, `am start` → host death <15s |
| 2 | `-gpu off` | identical death |
| 3 | idle, no install (150 s + boot) | ALIVE (uptime 190 s+) — not time-based |
| 4 | `-gpu off`, Settings launch | ALIVE — Companion-specific, not `am start` |
| 5 | `-gpu off -no-audio` | identical death (voice is button-gated, never at startup) |
| 6 | `-gpu off -no-audio`, guest WiFi off | identical death (NSD/multicast exonerated) |

Evidence: `E:/shots/a1-emu/death-logcat.txt` (app DISPLAYS ok, heavy
main thread, then silence — no app crash, no FATAL), `E:/Android/
emulator-boot-a1*.log` (all end at "Boot completed"), 0-byte crash DB,
no Windows Application/System GPU-TDR entries, 13 GB host RAM free.

Falsified: GPU renderer mode, audio backend, guest WiFi/NSD-multicast,
time-based death, `am start` in general. The A1 change itself is
logically excluded (it executes only at pair-confirm; death precedes
any pairing). Untried: API 33 image (CI's level; local has only
API 34), AVD clone+wipe, host-GPU de-saturation. Per systematic
debugging (6 falsified hypotheses): stop blind retries, document,
decide with the owner.

## What DOES validate the fix

- Same app launches green on CI Linux emulators (android 5/5 on main);
  this PR's Android legs re-prove launch-with-fix (no-regression).
- Logic review: the added reset is exactly `unpair()`'s clearing, on the
  only path that missed it; the consent dialog path is untouched.
- Owner options: (a) phone validation later (personal device, needs
  explicit OK — NOT done), (b) retry local emulator after a host/GPU
  change, (c) accept CI-level validation.

## Residuals (unchanged)

Doze multi-hour soak and full-control re-pair on real hardware remain
open; the probe automates the bounded Doze check once a live emulator
exists. TV/watch frozen by the owner tonight — untouched.
