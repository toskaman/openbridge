# Fallback video — reproducible build (E3, Campaign Three §5.6)

Honest technical fallback video. No physical-device footage exists in this
cut, so none is claimed: the video assembles only real captures — actual
test-suite output, the judge demo run, a screen-captured offline UI replay
(`scripts/run/demo_fallback.py`), and committed evidence stills. Every
non-physical frame carries a REPLAY/SIMULATED (or SCREEN RENDER) tag plus
the source-revision label. Gaps are recorded on screen and in §6, never
fabricated around.

- Artifact (NOT in repo):
  `E:/OpenBridge-Overnight/frontier90/evidence/f90-fallback-video-2d12512.mp4`
- Specs: 78.13 s · 4,315,975 bytes (4.3 MB) · 1280x720 · 30 fps ·
  H.264 yuv420p · silent, narration burned in as subtitles.
- Source revision: `2d125127cc1739f3480d4f2169e97d82953a73ae`
  (branch `feat/f90-video`, 2026-11-01).
- Subtitles: `evidence/video_build/narration.srt` (also burned in).

## 1. Tools (exact)

| Tool | Version / path |
|---|---|
| Python | 3.14.4 (MSC v.1944 64-bit) |
| Pillow | 12.2.0 |
| Playwright + Chromium | chromium-1243 headless (`PLAYWRIGHT_BROWSERS_PATH` pointed at the `.pw-browsers` store) |
| ffmpeg / ffprobe | N-123918-gf7ca6f7481-20260411 (`C:\Users\TheBox\AppData\Local\agy\bin\`) |
| Fonts | `C:/Windows/Fonts/arial.ttf`, `C:/Windows/Fonts/consola.ttf` |

## 2. Terminal captures (verbatim logs)

Run from the worktree root with UTF-8 capture (PowerShell `>` alone
writes UTF-16 and mangles `×`/accents — pipe through `Out-File` instead):

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PLAYWRIGHT_BROWSERS_PATH='C:/Users/TheBox/Desktop/Hackaton/.pw-browsers'
cd E:/OpenBridge-Overnight/frontier90/worktrees/e3-video
python scripts/run/demo_fallback.py --check | Out-File -Encoding utf8 ../evidence-staging/check_run.txt
python -m tests.e2e.demo_replay_smoke | Out-File -Encoding utf8 ../evidence-staging/demo_smoke_run.txt
python -m unittest discover -s tests -q 2>&1 | Out-File -Encoding utf8 ../evidence-staging/suite_run.txt
```

Recorded results (this session, on the source revision above):

- `--check`: `demo_fallback --check: PASS (2 scenarios × 9 stages, SIMULATED, receipts present)` — exit 0.
- smoke: `Demo fallback replay passed at 390/1440: REPLAY+SIMULATED labels, 9 stages × 2 scenarios, verbatim receipts, scripted autoplay. Zero POST/model/hardware calls.` — exit 0.
- suite: `Ran 2029 tests in 174.731s — OK` — exit 0 (an earlier run on the
  same revision gave `206.208s — OK`; count and verdict identical).

Copy the three logs to `E:/OpenBridge-Overnight/frontier90/evidence/video_build/`.

## 3. Offline UI screen capture (real footage)

`capture_replay.py` starts the real server on a loopback auto-port, opens
`/#/replay/autoplay` in headless Chromium (1280x720, video recording on),
waits for the S5 autoplay to reach step 9, switches to S5b, plays it to
step 9, and saves the WebM plus two PNG checkpoints. Recorded footage:
30.12 s. Adjust `ROOT`/`STAGING` to your checkout. (Listing omits two
dead no-op lines present in the staged file; verified same constants +
same 357-op opcode sequence.)

```python
"""E3 video: REAL screen capture of the offline replay UI (Campaign Three s5.6 fallback).

Starts the real OpenBridge server on loopback, opens the real replay view in
headless Chromium with video recording, autoplays S5 then S5b, saves screenshots.
No hardware, no model, no pairing: exactly one GET /api/demo-replay per load.
"""
import sys
import threading
from pathlib import Path

ROOT = Path("E:/OpenBridge-Overnight/frontier90/worktrees/e3-video")
sys.path.insert(0, str(ROOT))
import os

os.chdir(str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from src.server import create_server  # noqa: E402

STAGING = Path("E:/OpenBridge-Overnight/frontier90/evidence/video_build")
STAGING.mkdir(parents=True, exist_ok=True)

server = create_server(0)
worker = threading.Thread(target=server.serve_forever, daemon=True)
worker.start()
base = "http://127.0.0.1:%d" % server.server_port
print("server on", base, flush=True)

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(STAGING / "replay_video"),
            record_video_size={"width": 1280, "height": 720},
            reduced_motion="no-preference",
        )
        page = ctx.new_page()
        page.goto(base + "/#/replay/autoplay", wait_until="networkidle")
        page.wait_for_selector(".replay-banner", timeout=10000)
        page.wait_for_selector(
            '.replay-stage[data-stage-idx="8"].active', timeout=30000
        )
        print("S5 autoplay reached step 9", flush=True)
        page.wait_for_timeout(2500)
        page.screenshot(path=str(STAGING / "replay_s5_step9.png"))
        page.get_by_role("button", name="S5b").click()
        page.get_by_role("button", name="Play").click()
        page.wait_for_selector(
            '.replay-stage[data-stage-idx="8"].active', timeout=30000
        )
        print("S5b autoplay reached step 9", flush=True)
        page.wait_for_timeout(2500)
        page.screenshot(path=str(STAGING / "replay_s5b_step9.png"))
        page.wait_for_timeout(1000)
        page.close()
        ctx.close()
        browser.close()
        vids = sorted((STAGING / "replay_video").glob("*.webm"))
        print("videos:", [str(v) for v in vids], flush=True)
finally:
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)
print("CAPTURE DONE", flush=True)
```

Run it:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH='C:/Users/TheBox/Desktop/Hackaton/.pw-browsers'
python E:/OpenBridge-Overnight/frontier90/evidence/video_build/capture_replay.py
```

## 4. Assembly (cards + overlays + subtitles + encode)

`build_video.py` renders title/terminal-output/closing cards with PIL
(terminal text verbatim from the §2 logs — wrapped at 92 columns only),
frames six committed stills with provenance bars, overlays a top
`OFFLINE REPLAY · SIMULATED · commit <sha>` bar on the footage, builds
`narration.srt` from the real segment boundaries, concatenates, and burns
the subtitles (`libx264`, CRF 23, `yuv420p`, silent). Adjust
`FFMPEG`/`FFPROBE`/`ROOT`/`EV` to your machine. (Listing uses literal
UTF-8 where the staged file uses `\uXXXX` escapes; verified same
constants + same 204-op opcode sequence.)

```python
"""E3 video: assemble the honest technical fallback video from REAL captures only.

Inputs (all real, produced this session or committed):
  - evidence/video_build/suite_run.txt          full suite output (2029 tests OK)
  - evidence/video_build/demo_smoke_run.txt     judge demo smoke output (PASS)
  - evidence/video_build/replay_video/*.webm    real Chromium capture of replay UI
  - docs/jury/screens/*.png                    committed evidence stills
Output:
  - evidence/f90-fallback-video-<sha>.mp4  (NOT in repo)
  - evidence/video_build/narration.srt     narration subtitles (also burned in)
"""
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FFMPEG = r"C:\Users\TheBox\AppData\Local\agy\bin\ffmpeg.exe"
FFPROBE = r"C:\Users\TheBox\AppData\Local\agy\bin\ffprobe.exe"
ROOT = Path("E:/OpenBridge-Overnight/frontier90/worktrees/e3-video")
EV = Path("E:/OpenBridge-Overnight/frontier90/evidence")
STAGING = EV / "video_build"
SCREENS = ROOT / "docs/jury/screens"
W, H, FPS = 1280, 720, 30
BG = (11, 18, 32)
FG = (235, 240, 250)
DIM = (150, 165, 190)
ACCENT = (45, 212, 191)
WARN = (251, 191, 36)
GREEN = (52, 211, 153)

SHA = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), capture_output=True,
    text=True, check=True).stdout.strip()
SHA_FULL = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
    text=True, check=True).stdout.strip()
BRANCH = subprocess.run(
    ["git", "branch", "--show-current"], cwd=str(ROOT), capture_output=True,
    text=True, check=True).stdout.strip()
TODAY = date.today().isoformat()

FONT_SANS = "C:/Windows/Fonts/arial.ttf"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"


def font(path, size):
    return ImageFont.truetype(path, size)


def base_card():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=ACCENT)
    d.rectangle([0, H - 8, W, H], fill=ACCENT)
    return img, d


def read_log(path):
    """PowerShell '>' redirects as UTF-16LE; unittest may mix encodings."""
    raw = Path(path).read_bytes()
    if b"\x00" in raw[:400]:
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def footer_rev(d):
    # Top-right: bottom 140px stays clear for burned subtitles.
    f = font(FONT_MONO, 18)
    d.text((W - 24, 18), "commit %s (%s) · %s" % (SHA, BRANCH, TODAY),
           font=f, fill=DIM, anchor="ra")


def save_card(img, name):
    p = STAGING / name
    img.save(p)
    print("card:", p, flush=True)
    return p


def title_card():
    img, d = base_card()
    d.text((80, 130), "OpenBridge — Technical Fallback Video",
           font=font(FONT_SANS, 56), fill=FG)
    d.text((80, 215), "Campaign Three §5.6 · judge-C W3",
           font=font(FONT_SANS, 34), fill=ACCENT)
    d.text((80, 300), "NO PHYSICAL-DEVICE FOOTAGE IN THIS CUT",
           font=font(FONT_SANS, 34), fill=WARN)
    for i, line in enumerate([
        "Assembled only from real captures: test-suite output,",
        "judge demo run, offline UI screen capture, committed stills.",
        "Every non-physical frame is tagged REPLAY / SIMULATED.",
    ]):
        d.text((80, 380 + i * 44), line, font=font(FONT_SANS, 26), fill=DIM)
    footer_rev(d)
    return save_card(img, "card_title.png")


def mono_card(name, heading, tag, cmd_lines, body_text, foot_note):
    """Verbatim terminal-output card. body_text rendered as-is (wrapped only)."""
    img, d = base_card()
    footer_rev(d)
    d.text((60, 52), heading, font=font(FONT_SANS, 36), fill=FG)
    d.text((60, 104), tag, font=font(FONT_SANS, 24), fill=WARN)
    y = 156
    fm_cmd, fm_body = font(FONT_MONO, 22), font(FONT_MONO, 21)
    for cmd in cmd_lines:
        d.text((60, y), cmd, font=fm_cmd, fill=ACCENT)
        y += 34
    y += 8
    for raw in body_text.splitlines():
        for line in textwrap.wrap(raw, width=92) or [""]:
            if y > H - 200:
                break
            fill = GREEN if line.strip() in ("OK",) or "PASS" in line or "passed" in line else FG
            d.text((60, y), line, font=fm_body, fill=fill)
            y += 28
    d.text((60, min(y + 18, H - 175)), foot_note, font=font(FONT_MONO, 19), fill=DIM)
    return save_card(img, name)


def close_card():
    img, d = base_card()
    d.text((80, 90), "What this video proves", font=font(FONT_SANS, 48), fill=FG)
    rows = [
        ("[ok] 2029 / 2029 tests green on the recorded commit", FG),
        ("[ok] Offline replay: 2 scenarios × 9 stages, zero live calls", FG),
        ("[ok] Committed stills: TV panel installed → pressed → revoked", FG),
        ("GAP: no camera footage of manual press / vacuum motion", WARN),
        ("(owner-gated; recorded as missing, never faked)", WARN),
    ]
    for i, (line, fill) in enumerate(rows):
        d.text((80, 190 + i * 52), line, font=font(FONT_SANS, 27), fill=fill)
    d.text((80, 480), "github.com/toskaman/openbridge",
           font=font(FONT_SANS, 30), fill=ACCENT)
    d.text((80, 525), "Reproduce: docs/jury/VIDEO_BUILD.md",
           font=font(FONT_SANS, 24), fill=DIM)
    footer_rev(d)
    return save_card(img, "card_close.png")


def still_frame(src, top_tag, bottom_label):
    """Committed still -> 1280x720 frame with provenance bars (PIL only)."""
    im = Image.open(src).convert("RGB")
    im.thumbnail((W, H - 250), Image.LANCZOS)
    frame = Image.new("RGB", (W, H), (5, 8, 16))
    frame.paste(im, ((W - im.width) // 2, 104 + (H - 244 - im.height) // 2))
    d = ImageDraw.Draw(frame)
    d.rectangle([0, 0, W, 100], fill=(5, 8, 16))
    d.text((24, 8), top_tag, font=font(FONT_SANS, 26), fill=WARN)
    d.text((24, 46), bottom_label, font=font(FONT_MONO, 20), fill=DIM)
    out = STAGING / ("frame_" + Path(src).stem + ".png")
    frame.save(out)
    print("frame:", out, flush=True)
    return out


def lower_third():
    bar = Image.new("RGBA", (W, 64), (5, 8, 16, 210))
    d = ImageDraw.Draw(bar)
    d.text((24, 14), "OFFLINE REPLAY · SIMULATED · commit %s · no hardware touched"
           % SHA, font=font(FONT_SANS, 26), fill=(251, 191, 36, 255))
    out = STAGING / "lower_third.png"
    bar.save(out)
    return out


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def seg_from_image(img, dur, out):
    run([FFMPEG, "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS),
         "-i", str(img), "-t", "%.2f" % dur, "-c:v", "libx264", "-pix_fmt",
         "yuv420p", "-r", str(FPS), str(out)])


def probe_dur(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def srt_time(sec):
    h, rem = divmod(sec, 3600)
    m, rem = divmod(rem, 60)
    s, ms = divmod(rem, 1)
    return "%02d:%02d:%02d,%03d" % (int(h), int(m), int(s), int(ms * 1000))


def main():
    STAGING.mkdir(parents=True, exist_ok=True)
    segs = STAGING / "segs"
    segs.mkdir(exist_ok=True)

    suite_lines = [ln for ln in read_log(STAGING / "suite_run.txt").splitlines()
                 if ln.strip()]
    suite_tail = "\n".join(suite_lines[-6:])
    smoke_txt = read_log(STAGING / "demo_smoke_run.txt").strip()
    check_txt = read_log(STAGING / "check_run.txt").strip()

    # 1. cards
    t0 = title_card()
    t1 = mono_card("card_suite.png", "Full test suite — actual output",
                   "SCREEN RENDER OF VERBATIM LOG · NOT DEVICE FOOTAGE",
                   ["$ python -m unittest discover -s tests -q"],
                   suite_tail, "exit 0 · full 33 KB log: evidence/video_build/suite_run.txt")
    t2 = mono_card("card_checks.png", "Replay checks — actual output",
                   "SCREEN RENDER OF VERBATIM LOG · NOT DEVICE FOOTAGE",
                   ["$ python scripts/run/demo_fallback.py --check",
                    "$ python -m tests.e2e.demo_replay_smoke"],
                   check_txt + "\n" + smoke_txt,
                   "both exit 0 · recorded this session on this commit")
    t5 = close_card()

    # 2. stills (committed, real)
    stills = [
        ("fabric-tv-relay-redacted-1440.png", "DETERMINISTIC UI STILL",
         "docs/jury/screens/fabric-tv-relay-redacted-1440.png · 24 dev / 31 links · redacted"),
        ("s5b_installed.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "docs/jury/screens/s5b_installed.png · Meta T2 panel on the real TV"),
        ("s5b_pressed.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "docs/jury/screens/s5b_pressed.png · after hold-press FIND · tx-4a96f8f6"),
        ("s5b_revoked.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "docs/jury/screens/s5b_revoked.png · after revoke: controls gone"),
        ("refusal_channel.png", "SEEDED-UI STILL · REAL REFUSAL PAYLOAD",
         "docs/jury/screens/refusal_channel.png · refused press in Activity timeline"),
        ("tv-wd7-direct-drain-caption.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "docs/jury/screens/tv-wd7-direct-drain-caption.png · direct-LAN signed report"),
    ]
    frames = [still_frame(SCREENS / name, tag, label) for name, tag, label in stills]

    # 3. replay footage + lower third
    webm = sorted((STAGING / "replay_video").glob("*.webm"))[0]
    replay_dur = probe_dur(webm)
    print("replay footage: %s (%.2fs)" % (webm, replay_dur), flush=True)
    bar = lower_third()
    replay_seg = segs / "seg_replay.mp4"
    run([FFMPEG, "-y", "-v", "error", "-i", str(webm), "-i", str(bar),
         "-filter_complex", "[0:v]format=yuv420p,fps=30[bg];[bg][1:v]overlay=0:0",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(replay_seg)])

    # 4. segments
    plan = [(t0, 6.0, "seg_title.mp4"), (t1, 10.0, "seg_suite.mp4"),
            (t2, 8.0, "seg_checks.mp4")]
    seg_files = []
    for img, dur, name in plan:
        out = segs / name
        seg_from_image(img, dur, out)
        seg_files.append((out, dur))
    seg_files.append((replay_seg, probe_dur(replay_seg)))
    for f in frames:
        out = segs / ("seg_" + f.stem + ".mp4")
        seg_from_image(f, 3.0, out)
        seg_files.append((out, 3.0))
    close_out = segs / "seg_close.mp4"
    seg_from_image(t5, 6.0, close_out)
    seg_files.append((close_out, 6.0))

    # 5. narration SRT aligned to real segment boundaries
    bounds, t = [0.0], 0.0
    for _, dur in seg_files:
        t += dur
        bounds.append(t)
    total = bounds[-1]
    still_start = bounds[4]
    still_end = bounds[4 + len(frames)]
    cues = [
        (bounds[0], bounds[1],
         "OpenBridge technical fallback.\nNo physical-device footage exists in this cut."),
        (bounds[1], bounds[2],
         "The full suite: 2029 tests, passing\non the recorded commit."),
        (bounds[2], bounds[3],
         "The offline replay checks pass:\nscripted receipts, zero live calls."),
        (bounds[3], bounds[4],
         "The real interface replays recorded S5 and S5b receipts.\nEvery stage is labeled simulated."),
        (still_start, still_end,
         "Committed evidence stills: the TV panel lived,\nwas pressed, and was revoked."),
        (bounds[-2], bounds[-1],
         "OpenBridge: every claim receipted,\nevery limit labeled."),
    ]
    srt = STAGING / "narration.srt"
    with open(srt, "w", encoding="utf-8") as fh:
        for i, (a, b, text) in enumerate(cues, 1):
            fh.write("%d\n%s --> %s\n%s\n\n" % (i, srt_time(a), srt_time(b), text))
    print("srt:", srt, "total %.2fs" % total, flush=True)

    # 6. concat + burn subtitles
    lst = segs / "concat.txt"
    with open(lst, "w", encoding="utf-8") as fh:
        for path, _ in seg_files:
            fh.write("file '%s'\n" % str(path).replace("'", "'\\''"))
    silent = segs / "full_silent.mp4"
    run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i",
         str(lst), "-c", "copy", str(silent)])
    out = EV / ("f90-fallback-video-%s.mp4" % SHA)
    srt_filter = "subtitles='" + str(srt).replace("\\", "/").replace(":", "\\:") + "'"
    run([FFMPEG, "-y", "-v", "error", "-i", str(silent), "-vf", srt_filter,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
         "-preset", "medium", str(out)])
    dur = probe_dur(out)
    size = out.stat().st_size
    print("VIDEO: %s" % out, flush=True)
    print("DURATION: %.2fs  SIZE: %d bytes (%.1f MB)" % (dur, size, size / 1e6), flush=True)
    print("SHA_FULL: %s" % SHA_FULL, flush=True)
    (STAGING / "build_meta.txt").write_text(
        "video=%s\nduration_s=%.2f\nsize_bytes=%d\nsha=%s\nbranch=%s\ndate=%s\n"
        % (out, dur, size, SHA_FULL, BRANCH, TODAY), encoding="utf-8")


if __name__ == "__main__":
    main()
```

Run it:

```powershell
python E:/OpenBridge-Overnight/frontier90/evidence/video_build/build_video.py
```

Expected output tail:

```text
VIDEO: E:\OpenBridge-Overnight\frontier90\evidence\f90-fallback-video-2d12512.mp4
DURATION: 78.13s  SIZE: 4315975 bytes (4.3 MB)
SHA_FULL: 2d125127cc1739f3480d4f2169e97d82953a73ae
```

## 5. Segment map + narration timing (this cut)

The video is silent; narration is delivered as burned-in subtitles
(plus the standalone `narration.srt`). Timecodes below are the actual
segment boundaries.

| # | Time | Dur | Picture | Narration (verbatim, ≤2 lines) |
|---|---|---|---|---|
| 1 | 0:00.000–0:06.000 | 6.0 s | Title card + `commit 2d12512 (feat/f90-video)` | `OpenBridge technical fallback.` / `No physical-device footage exists in this cut.` |
| 2 | 0:06.000–0:16.000 | 10.0 s | Suite card: last 6 non-blank lines of `suite_run.txt` verbatim (`Ran 2029 tests in 174.731s` / `OK`) | `The full suite: 2029 tests, passing` / `on the recorded commit.` |
| 3 | 0:16.000–0:24.000 | 8.0 s | Checks card: `--check` + smoke outputs verbatim | `The offline replay checks pass:` / `scripted receipts, zero live calls.` |
| 4 | 0:24.000–0:54.133 | 30.13 s | Real Chromium capture: S5 autoplay → S5b autoplay, top bar `OFFLINE REPLAY · SIMULATED · commit 2d12512` | `The real interface replays recorded S5 and S5b receipts.` / `Every stage is labeled simulated.` |
| 5 | 0:54.133–1:12.133 | 18.0 s | 6 committed stills × 3 s, each with provenance header (filename + `MEDIA_MANIFEST.md` tag) | `Committed evidence stills: the TV panel lived,` / `was pressed, and was revoked.` |
| 6 | 1:12.133–1:18.133 | 6.0 s | Closing card: claims + on-screen GAP + repo link | `OpenBridge: every claim receipted,` / `every limit labeled.` |

Still order in segment 5: `fabric-tv-relay-redacted-1440.png`
(DETERMINISTIC) → `s5b_installed.png` → `s5b_pressed.png` →
`s5b_revoked.png` (all REAL_HARDWARE) → `refusal_channel.png`
(SEEDED-UI, real refusal payload) →
`tv-wd7-direct-drain-caption.png` (REAL_HARDWARE).

## 6. Labeling rules applied

- Title/terminal/closing cards: `SCREEN RENDER OF VERBATIM LOG · NOT
  DEVICE FOOTAGE` (terminal cards) or explicit `NO PHYSICAL-DEVICE
  FOOTAGE` (title); every card carries `commit <sha> (<branch>) · <date>`
  top-right.
- Replay footage: the UI itself shows the pinned `REPLAY · SIMULATED`
  banner plus per-stage `SIMULATED` chips; the build adds a top
  `OFFLINE REPLAY · SIMULATED · commit <sha> · no hardware touched` bar.
- Stills: header shows the committed path plus the manifest tag —
  REAL_HARDWARE only where `MEDIA_MANIFEST.md` says so, SEEDED-UI for
  `refusal_channel.png`.
- Receipt values on screen (tx ids, relay id, model id) are pixels of
  the real UI / real stills, never re-typed.

## 7. Gaps recorded (not faked)

1. No camera footage of the S5 manual press, S5 vacuum motion, or the S6
   watch press exists — owner-gated (hardware + presence + explicit
   media authorization). The storyboard beats that need them are
   replaced by the scripted replay + stills, and the gap is stated on
   the closing card.
2. No voiceover track was recorded — narration exists as timed
   subtitles (this file + `narration.srt`) so a narrator can lay it
   down 1:1 later. Any future voiceover must keep the same honest
   wording; numbers must be re-verified against the then-current
   revision before recording.

## 8. Verification performed

- `ffprobe`: 1280x720, H.264, 30 fps, 78.13 s, 4.3 MB (≤ ~50 MB).
- Spot frames extracted at t = 3 / 12 / 20 / 40 / 60 / 76 s and
  inspected: cards legible, subtitles clear of all fixed labels,
  footage shows the real replay UI at S5/S5b step 9, stills carry
  provenance headers.
- Log tail of this build: `E:/OpenBridge-Overnight/frontier90/logs/e3-video.log`.
```
