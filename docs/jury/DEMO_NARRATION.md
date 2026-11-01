# OpenBridge — Demo narration (final 180 s, one story)

Companion to [DEMO_STORYBOARD_FINAL.md](DEMO_STORYBOARD_FINAL.md) (timings,
shots, cut rules) and [DEMO_PHYSICAL_RUNBOOK.md](DEMO_PHYSICAL_RUNBOOK.md)
(device actions). **No recording without the owner's new explicit
authorization.** Total narration ≈ 80 words over 180 s — sparse by design;
slow, calm delivery; let the screens breathe.

## Script (English, with timecodes)

| Time | Narration (verbatim) | On-screen text |
|---|---|---|
| 0:00–0:12 | "Our homes are full of devices that were never designed to work together." | `5 islands: PC · phone · TV · watch · vacuum` |
| 0:12–0:32 | "OpenBridge discovers them and proves every capability before using it." | `Discover my environment → 24 devices, every link proven` |
| 0:32–1:25 | "Ask in plain language — Meta AI composes new controls, and the TV obeys." | `"Create a control panel on my TV…" → VALID → installed → receipt` |
| 1:25–1:52 | "Even the watch on your wrist can drive another machine — with your consent." | `Watch QUICK CONTROLS → one press → one verified action` |
| 1:52–2:20 | "Nothing runs without approval, and every refusal is shown, not hidden." | `approval → receipt → revoke → DENIED (shown, not hidden)` |
| 2:20–2:40 | "Local Meta models, a crash-proof ledger, and labels you can trust." | `Meta-only runtime · 2013 tests · REAL vs SIMULATED, labeled` |
| 2:40–3:00 | "OpenBridge — Meta AI that moves real hardware, provably." | `OpenBridge · github.com/toskaman/openbridge` |

## Delivery notes

- One narrator, neutral pace (~27 words/min); pause 1–2 s between beats.
- Beats 3–4 carry the story: if S5 motion or the S6 watch chain is
  unavailable on the day, apply the storyboard cut list (DISPATCH ONLY label
  or drop the beat) — never voice over a claim the footage doesn't show.
- Numbers spoken on air must match the committed evidence at record time
  (suite count, registry rows, run ids); re-verify against
  [RELEASE_STATUS.md](../RELEASE_STATUS.md) on recording day.

## Provenance overlays (beats 2–6, lower third)

`model: muse-glimmer:30b-q4_K_M · digest de878ce3… · commit <SHA> · receipt <id>`
Use the real values from the run; omit any field that isn't from the take.

## Subtitles

- English SRT, max 2 lines, ≤ 42 chars/line, synchronized to the beats above.
- Burned-in captions only for the on-screen-text column; narration lives in
  subtitles + voiceover so the UI stays readable.
- Final pass: spelling, redaction sweep (no names, serials, IPs, keys,
  notifications), 16:9, duration 175–180 s.
