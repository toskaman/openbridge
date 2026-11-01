# Jury video v2 (with IRL footage) — reproducible build (2026-11-01)

Output: `E:\OpenBridge-Overnight\frontier-final\final-jury-video-718b401.mp4`
(159.33 s, 1280x720, 30 fps, H.264 yuv420p, CRF 23, **silent**,
13.4 MB) + burned EN subtitles + standalone `video_v2/narration.srt` +
thumbnail + `final-jury-video-718b401-SHA256SUMS.txt` + scene map.
Builder (committed, reviewable): `scripts/video/build_jury_video.py`
(run from the repo root). Method extends `VIDEO_BUILD.md` §1–§4
(same cards/stills/concat mechanics); only the new IRL path, the new
cards, and the new plan are documented here.

## 1. Inputs (all real, all checkable)

- Fresh logs, recorded this session on the stamped commit (lot branch):
  `video_v2/suite_run.txt` (2096 tests, 297.8 s, exit 0),
  `video_v2/check_run.txt` (demo_fallback --check PASS),
  `video_v2/demo_smoke_run.txt` (replay smoke PASS, chromium store
  `Hackaton/.pw-browsers`, `PLAYWRIGHT_BROWSERS_PATH` set).
- Replay: `video_v2/replay_video/*.webm` (dd669c2 capture, 3.1 MB);
  on-screen overlay keeps its TRUE source rev (`recorded rev dd669c2`).
- IRL rushes `Z:\OPENBRIDGE\VID_20261101_*.mp4` (owner camera, 5× 720p30,
  251 s): trims + speeds per `VIDEO_IRL_PLAN.md` EDL (9 selects, 33 s
  out). Speeds: proof moments ×1 (sacred), waits ×1.5–×2 (labeled on
  screen, e.g. `@1.5x`). Audio dropped on every segment (silent cut).
- Committed stills `docs/jury/screens/`: problem (fabric-real,
  ask-openbridge, fabric-tv-relay), s5b ×3 (tx-4a96f8f6), s5c ×3
  (01-Nov manual chain, tx-63ee07451c), watch ×3 (+ tx-5b326915),
  safety ×2. Every still frame carries its repo path on screen.

## 2. New cards (same PIL style as v1)

- Title: "OpenBridge — Jury Cut / FINAL FRONTIER · with real-device
  footage" + honesty footer.
- Scorecard ("Measured, not claimed"): S8 4→0 unsafe on 48 held-out
  ($0 local), no fully-correct proposal blocked (strict rescore exit 1 +
  analysis on record), ModelStudy48 rules 36.1% vs Llama 22.2% (loss
  published), F90 1128 ops green, Glimmer 7× env OOM (reported, never a
  quality claim).
- Close: 3 proof rows with both tx ids + the motion GAP row
  ("vacuum motion not visible on camera (oracle-only return proof) /
  recorded as missing, never faked") + repo link + this doc's path.

## 3. IRL segment recipe (novel vs v1)

Per EDL row: `ffmpeg -ss A -to B -i <rush> -i <PIL bar PNG>
-filter_complex "[0:v]setpts=PTS/RATE,fps=30,format=yuv420p[bg];
[bg][1:v]overlay=0:0" -an` → probed duration feeds the concat plan
and the SRT boundaries. Bars (green, top): `REAL_HARDWARE · <rush>
t=A-B [@RATE] · <what> · [tx-…]`; adverse/static rows say so
(`ADVERSE DISCLOSED`, `STATIC, no motion claimed`, `no tx, outside
script`). Subtitle cues (16, EN, ≤2 lines) are computed from the
measured boundaries, then burned with libass `subtitles`.

## 4. Verification (all observed, 01-Nov)

- `ffprobe`: h264, 1280x720, yuv420p, 30/1 fps, 159.33 s, ONE stream
  (video only — no audio track at all), 14040282 bytes.
- 12-frame QA sheet (every beat) + 2 full-res frames: cards legible,
  replay + SIMULATED bars present, IRL bars legible at 720p, burned
  subtitles readable, no bar/subtitle overlap (bars top, subs bottom).
- Redaction sweep: no serials / IPs / keys / faces in any used second
  (relay id fragment `relay-dabd2a79` is a random session id);
  copyrighted launcher artwork and the bare-foot frame were cut at EDL
  stage, never rendered.
- SHA256SUMS written for mp4 + srt + thumb; scene map
  (`final-jury-video-718b401-SCENE_MAP.md`) lists all 29 segments with
  measured boundaries.

## 5. Honesty deltas vs the 31-Oct storyboard

- Beat 3 is verified-dispatch (DISPATCH VERIFIED + oracle), NOT motion:
  no sampled IRL frame shows the vacuum moving (motion-scan verified);
  the close card + scene map + `VIDEO_IRL_PLAN.md` say so.
- Beat 4 (watch) uses committed stills + receipt (tx-5b326915), labeled
  "no camera footage" — §6 camera run still owner-pending.
- Replay UI predates the Ask-hero follow-up (#175); its overlay keeps
  the true source rev (dd669c2) instead of claiming current.
- Total 159 s (storyboard aspirational 175–180; actuals bind).

## 6. What is NOT changed

- The frozen v0.2.0 release (tag dd669c2, MIT, 78 s fallback cut) is
  untouched. This jury cut is post-tag material (lot branch 718b401)
  for the PORTAL submission upload — owner-only, NOT submitted by me.
