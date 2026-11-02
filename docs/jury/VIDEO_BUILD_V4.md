# Jury video V4 — cold-open reorder (02-Nov-2026, exec branch `e2d5eb3`)

V3 (`final-jury-video-2351308.mp4`, sha `eee76671…`) stays frozen as history.
V2 (`3d3e228e…`) stays frozen. V4 reuses the SAME segments, SAME trims,
SAME 159.33 s total — only the assembly order changes, plus caption upgrades.

## What changed (and only this)

- Cold open: the three press/receipt IRL beats (`start` 6 s + `dockpress`
  4 s + `dockok` 3.5 s) move to 0:00–0:13.5 as the hook, ahead of the title
  card. A stranger now sees a hand, a remote, a real TV panel, and verified
  receipts inside the first 15 seconds (jury finding J7/W7).
- Uniform 1280x720: portrait phone rushes are letterboxed (scale + pad,
  background `#050810`) so every segment matches the cards. V2/V3 concats
  mixed portrait IRL segs into a landscape header (latent defect, now fixed
  in V4 only — frozen cuts untouched).
- S5b panel still gains the synthesis attribution it can prove:
  `Glimmer 30B de878ce3…` (`src/ai/glimmer.py:4-5`). The Ask-wait bar stays
  unattributed: that take's serving model is not on record, and
  `DEMO_NARRATION.md:33-34` forbids unattested fields (§14 P1#6, honest form).
- Watch press-ack still gains the independent repeat: `R1 22→23 + R4 23→24`
  (`docs/evidence/s6-watch-tv-volume-01nov.md:90-91`) (§14 P1#7).
- Closing narration softened `moves` → `commands` real hardware: dispatch is
  verified, motion is not — the word now matches the GAP row on the same card.
- New vacuum-beat subtitle: "The vacuum stands by, unmoving: / dispatch
  verified, motion never claimed."
- Footer stamps `commit e2d5eb3 (feat/first-place-exec-02nov)` honestly;
  rebuild on the submitted SHA before upload.

## Artifact (NOT in repo)

- `E:/OpenBridge-Overnight/overnight-02nov/v4/final-jury-video-e2d5eb3.mp4`
  8582629 bytes, h264 1280x720 30fps yuv420p, 159.333s, ONE video stream,
  no audio. 4780 frames.
- SHA256 `12f492343e32c75077a8140d35959b40540463308ecb46f4026590641259f941`
  (+ srt + thumb in `final-jury-video-e2d5eb3-SHA256SUMS.txt`).
- Scene map + narration.srt + thumb next to the mp4. QA frames:
  `overnight-02nov/v4/v4-qa/v4_t{3,11,90,101,129,155b}.png` (hook, receipt,
  STATIC, Glimmer caption, R1/R4 caption, close card — all inspected).

## Reproduce

From this branch with the owner IRL rushes on `Z:`:

```
mkdir E:\OpenBridge-Overnight\overnight-02nov\v4\video_v4
python -m unittest discover -s tests -q > ...\v4\video_v4\suite_run.txt 2>&1
python scripts/run/demo_fallback.py --check > ...\v4\video_v4\check_run.txt 2>&1
$env:PLAYWRIGHT_BROWSERS_PATH='E:\pw-browsers'; python -m tests.e2e.demo_replay_smoke > ...\v4\video_v4\demo_smoke_run.txt 2>&1
python scripts/video/build_jury_video_v4.py
```

Fresh logs used: suite `2115/2115 OK` (273.4 s), fallback `--check` PASS,
replay smoke PASS @390/1440. Builder refuses stale numbers (suite log must
end OK) and missing inputs.

Builder: `scripts/video/build_jury_video_v4.py` (copy of the frozen V3
builder + cold-open assembly + letterbox + captions; replay webm still
sourced from `frontier-final/video_v2/`, still labeled dd669c2).

## Missing shot (unchanged from V3)

Vacuum motion on camera. Still OWNER_REQUIRED (film the unit during a
manual DOCK). The close-card GAP row stays until that footage exists.
Duration fit vs the portal video max is owner-gated (no padding applied).
