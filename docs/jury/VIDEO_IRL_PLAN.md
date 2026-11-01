# IRL rushes → jury video incorporation plan (01-Nov-2026)

Source: `Z:\OPENBRIDGE` (owner-recorded, 5× 720p30 H.264+AAC, 251 s total).
Review artifacts (not in git): `E:/shots/video-review/` (contact sheets,
dense frames, motion scan). Analysis method: contact sheets + dense
sampling + frame-diff motion scan; every claim below names its timecode.

## Rush inventory

| Rush | Dur | Audio | Content |
|---|---|---|---|
| VID_20261101_182957 | 69.6 s | mean -51.9 dB, 13 silences | TV PAIRED/READY→EXCHANGING, Quick Controls, **START press framing** (Start highlighted + remote, t≈50-54), pan down, vacuum static near stand (t≈57-67) |
| VID_20261101_183214 | 34.9 s | mean -52.4 dB, 7 silences | Pairing→PAIRED transition (t≈0-10), then Google TV launcher browsing (t≈15-34, copyrighted artwork — CUT entirely) |
| VID_20261101_183541 | 90.5 s | mean -44.8 dB, 13 silences | **Ask "start vacuum" THINKING + comet** (t≈28-50), remote DPAD nav (t≈55-75), **"Pause vacuum: done, verified"** (t≈80-85, untranscripted — B-roll only), **lease-stale wide** (t≈87.7) |
| VID_20261101_183952 | 23.1 s | mean -55.5 dB, 7 silences | Blurry approach (t≈0-10, CUT), **"Dock vacuum: Unavailable: lease stale"** (t≈15-22) |
| VID_20261101_185018 | 33.0 s | mean -43.0 dB, 3 silences | **DOCK press framing** (remote + Pause-then-Dock nav, t≈8-12), vacuum cutaway static (t≈16-20), **"Dock vacuum: done, verified" + activity log 18:50:28** (t≈28), **revoke → NOT PAIRED** (t≈30-32) |

## Key findings (honest)

- **Vacuum MOTION: not visible in any sampled frame.** Motion scan top
  diffs are all camera pans. Vacuum is stationary everywhere it appears;
  its displacement across rushes (TV stand → doorway) happened off-camera
  (repositioned; cause unclaimable from footage). The oracle
  standby→goto_charge (tx-63ee07451c4099ce) proves the drive command, not
  visible motion. → Beat 3 stays **verified-dispatch (DISPATCH VERIFIED +
  oracle)**, never a motion claim. Storyboard edit plan already allows this.
- **Transcript-mapped moments ON CAMERA**: START press framing (≈18:30:47,
  attempt-1 window, tx-8abdd1eb), DOCK press + "done, verified" + activity
  log (18:50:28-34, tx-63ee07451c4099ce), revoke → NOT PAIRED (18:50:45,
  relay_revoke VERIFIED), lease-stale (attempt-1 adverse, rush3/4).
- **"Pause vacuum: done, verified" is real on screen but untranscripted**
  (no tx in either chain transcript — owner pressed outside scripted
  waits). Usable as B-roll ("every button live-verifies") WITHOUT a tx
  caption, or dropped. Recommended: use 2 s, no tx claim.
- **Audio**: near-silent beds + isolated peaks (handling/possible voice).
  Jury cut stays silent-with-burned-subtitles (established); mute all IRL
  audio. No transcription needed unless the owner wants voice kept.

## EDL — IRL selects for the 180 s storyboard cut (≈32 s)

Speed rule (owner request): dead time accelerated, proof moments sacred.

| # | Source | TC in–out | Speed | Out | Beat / caption |
|---|---|---|---|---|---|
| 1 | 183541 | t=30.0–34.0 | 1x | 4 s | B3 Ask: THINKING "start vacuum" appears |
| 2 | 183541 | t=40.0–46.0 | 1.5x | 4 s | B3 inference: comet + thinking (time-compressed) |
| 3 | 182957 | t=48.0–54.0 | 1x | 6 s | B3 START press: Start highlighted + remote (tx-8abdd1eb) |
| 4 | 185018 | t=8.0–12.0 | 1x | 4 s | B3 DOCK press: remote nav (tx-63ee07451c4099ce) |
| 5 | 185018 | t=16.0–20.0 | 2x | 2 s | B3 cutaway: vacuum in room (STATIC — no motion implied) |
| 6 | 185018 | t=26.0–29.5 | 1x | 3.5 s | B3 receipt: "done, verified" + activity log 18:50:28 |
| 7 | 183952 | t=15.0–20.0 | 1x | 5 s | B5 honesty: "Unavailable: lease stale" (adverse shown) |
| 8 | 185018 | t=30.0–32.5 | 1x | 2.5 s | B5 revoke: NOT PAIRED |
| 9 | 183541 | t=80.0–82.0 | 1x | 2 s | B-roll: Pause verified (NO tx caption) — optional |

CUT (unusable): all fast pans/blur (183541 t≈70-77; 185018 t≈0-4, 13-15,
21-25; 183952 t≈0-10), launcher browsing (183214 t≈15-34), typing waits
(keep ≤2 s @2x if needed for Ask setup), vacuum-static watches beyond EDL.

## Assembly notes (render step, needs owner Go)

- Target: storyboard 175–180 s. Keep fallback skeleton (title/suite/
  checks/replay/stills/scorecard/close), INSERT IRL beats at B3 (32–85)
  and B5 (112–140); rebalance narration SRT to new boundaries.
- Provenance overlays on every IRL second: `REAL_HARDWARE · 01-Nov-2026 ·
  <rush>+TC · tx-…` (B5 lease-stale: `ADVERSE · disclosed`).
- Redaction: bare foot (182957 t≈57.5 — outside EDL, n/a), launcher
  artwork (cut), no serials/IPs/keys visible in selects (verified).
- Framework decision for the render: extend the reproducible ffmpeg
  pipeline (`VIDEO_BUILD.md`, jury-trusted) vs HyperFrames general-video
  (skill-mandated default). Recommend ffmpeg extension for provenance
  continuity; owner decides.
- Subtitles: silent cut, burned EN subtitles (existing convention).
- Manifest: revision, scene times, source paths → `E:/shots/manifest/`.
