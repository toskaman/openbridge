# Jury video V3 — quality pass (02-Nov-2026, main `2351308`)

V2 (`final-jury-video-718b401.mp4`, sha `3d3e228e…`) stays frozen as history.
V3 is a minimal polish of the same cut — same segments, same EDL timings,
same IRL selects, same honesty labels.

## What changed (and only this)

- Fresh logs on main `2351308`: suite `2115/2115 OK` (341s), fallback
  `--check` PASS, replay smoke PASS @390/1440. Suite card + suite cue + close
  card updated 2096 → 2115; footer now reads `commit 2351308 (main)`.
- Close card gains one text row: `TV sleep/wake+reveal oracle-verified
  02-Nov · remote wakes (no power-on claim)`. No footage segment was added:
  the 02-Nov runs were not filmed and footage is never faked.
- IRL-press subtitle reflowed to 2 lines (`Presses verify live: / every
  button answers.`).
- Kept deliberately: title-first provenance opening, scorecard, GAP row,
  silent track, 159.33s / 720p30.

## Artifact (NOT in repo)

- `E:/OpenBridge-Overnight/overnight-02nov/v3/final-jury-video-2351308.mp4`
  13989568 bytes, h264 1280x720 30fps yuv420p, 159.333s, video-only.
- SHA256 `eee7667180f3661783313fdb1139f40652136a1828e16f900ee59ab08f8bc216`
  (+ srt + thumb in `final-jury-video-2351308-SHA256SUMS.txt`).
- Scene map + narration.srt + thumb next to the mp4.

## Reproduce

From a clean main worktree at `2351308` with the owner IRL rushes on `Z:`:

```
mkdir E:\OpenBridge-Overnight\overnight-02nov\v3\video_v3
python -m unittest discover -s tests -q > ...\v3\video_v3\suite_run.txt 2>&1
python scripts/run/demo_fallback.py --check > ...\v3\video_v3\check_run.txt 2>&1
python -m tests.e2e.demo_replay_smoke > ...\v3\video_v3\demo_smoke_run.txt 2>&1
python scripts/video/build_jury_video_v3.py
```

Builder: `scripts/video/build_jury_video_v3.py` (copy of the frozen V2
builder; replay webm still sourced from `frontier-final/video_v2/`).
QA frames: `overnight-02nov/v3-qa/v3_*.png` (suite card, IRL press,
close card inspected at native resolution).

## Missing shot (unchanged from V2)

Vacuum motion on camera. Still OWNER_REQUIRED (film the unit during a
manual DOCK). The close-card GAP row stays until that footage exists.
