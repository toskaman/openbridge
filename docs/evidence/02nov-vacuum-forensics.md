# 02-Nov vacuum footage — forensic record (03 Nov 2026)

Owner-filmed, delivered re-encoded (Lavf62.13.102, no camera metadata, no audio).
Source files live outside git (owner media drive); hashes + contact sheets + this
classification are the committed record. Full analysis (frame strips, centroid
tracks): release agent ledger `jury-final-03nov/PHYSICAL_EVIDENCE_VERIFICATION.md`.

| File | SHA256 (prefix) | Spec |
|---|---|---|
| start_stop_vacuum.mp4 | 1B1210B5… | 720x1280, 29.67 s, ~30 fps, 19.0 MB |
| retour_dock_noperm_copie_acceleree_x8.mp4 | 1593E62D… | 720x1280, 17.47 s, 30 fps, 11.9 MB |
| retour_dock_copie_acceleree_x8.mp4 | A38A25E8… | 720x1280, 14.37 s, 30 fps, 9.4 MB |
| retour_dock.mp4 (original speed) | — | NOT DELIVERED (x8 factor stated-in-filename only) |

## Verified from frames
- F1: orb THINKING "start vacuum" → panel + remote → "Sending..." →
  vacuum on floor, LEDs lit → TV "Start vacuum: done, verified".
  = filmed UI-confirmed dispatch + device presence. Locomotion NOT observed
  (centroid static ± camera shake over t=15–20 s).
- F2: Dock highlight → "Sending..." → vacuum mid-floor near dock station,
  LEDs on, ENDS undocked. = filmed dock dispatch + presence. Traverse and
  arrival NOT observed. Accelerated copy — label any use.
- F3: "Dock vacuum: Unavailable: lease stale" refusal on real TV, nothing
  dispatched, separate take. = filmed STALE-LEASE denial (expired
  authorization window, not a revoked-grant denial — label exactly).

## Not proven (explicit)
Vacuum locomotion/docking on camera; tx-level receipt correlation for these
takes (needs device-agent logs — UI "verified" is app read-back); x8 exact
factor; single-session continuity across files (treat as separate takes).

Contact sheets: `frames-02nov/contact_*.png` (12 frames each, committed).
