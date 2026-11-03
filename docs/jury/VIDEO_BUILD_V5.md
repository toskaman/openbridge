# Jury video V5 — new-footage cut (03-Nov-2026, branch `release/jury-final-03nov`)

§0 HISTORICAL DRAFT — never the submission. Official video = owner-filmed only, canonical slot `submission/final-video.mp4`, status FINAL_OWNER_VIDEO_PENDING.

V2/V3/V4 (`3d3e228e…`/`eee76671…`/`12f49234…`) stay frozen as history.
V5 adds the 02-Nov owner footage: filmed START/DOCK dispatch,
"done, verified" on screen, and a filmed lease-stale refusal.

## Artifact (NOT in repo)

- `E:/OpenBridge-Overnight/jury-final-03nov/media/v5/final-jury-video-a5e8208.mp4`
  10065846 bytes, h264 1280x720 30fps yuv420p, 170.70 s, ONE video stream,
  no audio. 5121 frames.
- SHA256 `b3cb41e7645d81a48e9d3f429a25cf2f2631e130a6f53032dbf110463df9c391`
  (+ srt `5690681e…`, thumb `f75e6247…` in `final-jury-video-a5e8208-SHA256SUMS.txt`).
- Scene map + narration.srt + thumb next to the mp4. QA frames:
  `media/v5/v5-qa/v5_t{2,8,14,30,36,55,60,100,110,120,131,140,160,167}.png`
  (14/14 inspected, all PASS).
- Footer stamps `commit a5e8208 (release/jury-final-03nov)`; suite card shows
  the fresh `2132/2132 OK` log (381.6 s) recorded on this branch.

## Story order (35 scenes, HOOK→FINISH)
Hook (dispatch + verified + manual receipts, 0–20 s) → title → problem →
META (NL THINKING + Glimmer panel) → suite + checks → replay (trimmed 20 s) →
proof chain (ask1/ask2/pause/vacuum/lease/revoke + new dock beats) → S5c →
filmed refusal → safety stills → watch stills → scorecard → close card.

## Honesty record (what V5 does NOT claim)
- Vacuum locomotion/docking: NOT visibly filmed. Every floor beat carries
  STATIC + the close card keeps the GAP row. Forensic basis:
  [02nov-vacuum-forensics](../evidence/02nov-vacuum-forensics.md) (centroid tracks, frame strips).
- The two x8 files are accelerated copies (encoder Lavf, factor stated in
  filename, unverified from bytes — no original on Z:). Labeled on-screen.
- The refusal is a STALE-LEASE denial ("Unavailable: lease stale"), not a
  revoked-grant denial. Labeled exactly; separate take from the dock clip.
- tx-level receipt correlation for the new takes is PENDING (no device-agent
  handoff yet); on-screen "verified" text is app read-back, presented as such.

## Reproduce

From this branch with Z: footage + the V4 staging dir:

```
mkdir E:\OpenBridge-Overnight\jury-final-03nov\media\v5\video_v5
python -m unittest discover -s tests -q > ...\v5\video_v5\suite_run.txt 2>&1
python scripts/run/demo_fallback.py --check > ...\v5\video_v5\check_run.txt 2>&1
$env:PLAYWRIGHT_BROWSERS_PATH='E:\pw-browsers'; python -m tests.e2e.demo_replay_smoke > ...\v5\video_v5\demo_smoke_run.txt 2>&1
python scripts/video/build_jury_video_v5.py
```

Fresh logs used: suite `2132/2132 OK` (381.6 s), fallback `--check` PASS,
replay smoke PASS. Builder: `scripts/video/build_jury_video_v5.py`.

NOTE: the 01-Nov VID_20261101 rushes are absent from Z: (only the 3 new files
remain; searched E:/OpenBridge-Overnight too). The builder reuses the 9 frozen
V4 IRL segments byte-identical for those beats (logged in build_meta.txt as
`reused_v4_segs=...`, all 9 present). Restoring the rushes to Z: makes V5 fully
source-reproducible; until then the V4 staging dir is a required input.

## Missing shots (unchanged)
Vacuum motion/docking on camera (owner-gated). Watch/multi-device scenes:
capture runbooks not committed — filming owner-gated, all UNVERIFIED
until filmed. Duration fit vs portal max is owner-gated
(170.70 s, no padding).
