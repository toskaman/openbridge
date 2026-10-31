# Final 180-second storyboard (31 Oct 2026) — ONE story

Supersedes `DEMO_STORYBOARD_180S.md` (kept for history) per the §12 redesign:
one cohesive arc, not a feature tour. Real captures only; each beat shows its
status label on screen. **Video BLOCKED: no recording without the owner's new
explicit authorization.**

## Arc

| Time | Beat | Screen | Proof | Status tonight |
|---|---|---|---|---|
| 0–12 | The problem | Fragmented devices: PC, phone, TV, watch, vacuum on separate islands | Staged narration over real discovery stills | READY (stills on file) |
| 12–32 | One Device Fabric | "Discover my environment" → live topology with evidence chips | REAL_HARDWARE receipts | READY |
| 32–85 | The breakthrough | "Create a control panel on my TV so I can operate my robot vacuum" → Meta inference → strict VALID → panel on the real TV → manual press → vacuum moves → receipt | S5 runbook (`DEMO_PHYSICAL_RUNBOOK.md`) | PENDING owner run (prior `s5-tv-panel-31oct` lacks observed motion + manual press) |
| 85–112 | Watch chain | Watch QUICK CONTROLS → second device obeys → read-back | S6 runbook | PENDING owner run |
| 112–140 | Safe by construction | Permission review → approval → revocation → refused re-press in the Activity timeline | Refusal-channel shot + receipts | READY (shot `E:/shots/refusal_channel.png`) |
| 140–160 | Why it is hard | Meta-only runtime · local inference scores · crash-safe ledger · honest REAL vs SIMULATED labels | Eval scorecard + 5/5 crash receipts | READY after eval lands |
| 160–180 | Close | Finished app + one-line proposition + repo link | — | READY |

## Narration (one line per beat)

1. "Our homes are full of devices that were never designed to work together."
2. "OpenBridge discovers them and proves every capability before using it."
3. "Ask in plain language — Meta AI composes new controls, and the TV obeys."
4. "Even the watch on your wrist can drive another machine — with your consent."
5. "Nothing runs without approval, and every refusal is shown, not hidden."
6. "Local Meta models, a crash-proof ledger, and labels you can trust."
7. "OpenBridge — Meta AI that moves real hardware, provably."

## Capture manifest (fill on recording day)

| Scene | Source path | Revision | Take time | Provenance overlay |
|---|---|---|---|---|
| Problem stills | `E:/shots/fabric-*.png` | — | — | DETERMINISTIC |
| Live discovery | screen capture | `git rev-parse HEAD` | — | DETERMINISTIC |
| S5 request → inference | screen capture | HEAD | — | model id + digest |
| S5 TV panel + manual press | camera + adb screenshot | HEAD | — | REAL_HARDWARE |
| S5 vacuum motion | camera, timestamped | HEAD | — | REAL_HARDWARE + oracle |
| S6 watch press → effect | camera + screen capture | HEAD | — | REAL_HARDWARE |
| Refusal timeline | `E:/shots/refusal_channel.png` or live | HEAD | — | DETERMINISTIC |
| Scorecard still | eval report | HEAD | — | MEASURED |
| Close | screen capture | HEAD | — | — |

## Recording checklist

- Owner present; media authorization explicit; consent taps on record.
- Devices awake: TV, vacuum (safe area agreed), watch (awake, not dozing).
- Preflight GO: `python scripts/verify/demo_preflight.py --timeout 30`.
- No private pixels: redact names, serials, IPs, keys; no notifications visible.
- 16:9, readable UI, English narration or subtitles, silent-audio intent kept.
- Provenance overlay on beats 2–6 (model/path, commit SHA, receipt id).
- Manifest (revision, scene times, source paths) in `E:/shots/manifest/`.

## Edit plan

- Beats are locked to the timings above; total 175–180 s.
- No terminal walls, no benchmark tables on screen (scorecard still only).
- Cut list (apply before the final take): any beat without its listed proof is
  DROPPED, neighbors keep their timing, never replaced with mock-ups.
- If S5 motion is unavailable on the day: keep a verified-dispatch beat
  (labeled DISPATCH ONLY) or drop to the refusal/safety beat.
  S5b (31 Oct PM: T2 panel → hold-press FIND → receipt tx-4a96f8f6 →
  15-poll oracle → revoke/deny VERIFIED, `E:/shots/s5b/`) is the
  ready-made DISPATCH ONLY fallback: same chain, zero motion, fully receipted.
- Final pass: duration, codec, dimensions, redaction sweep, frame inspection.
