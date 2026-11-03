"""Jury video v5: new-footage cut (CAMPAIGN jury-final-03nov).

V2/V3/V4 builders + mp4s stay frozen. V5 adds the 02-Nov owner footage
(start_stop_vacuum, retour_dock x8, retour_dock_noperm x8 — see
PHYSICAL_EVIDENCE_VERIFICATION.md): filmed dispatch + "done, verified" +
filmed lease-stale refusal. Order follows HOOK > PROBLEM > META > CONTROL >
PROOF > SECURITY > BEYOND > DIFFERENTIATOR > FINISH. Suite count is parsed
from the fresh log (never hard-coded). Vacuum locomotion/docking is NOT
visibly filmed anywhere: every floor beat is labeled STATIC, accelerated
copies are labeled as such, and the close card keeps the GAP row.

Inputs (all real):
  - E:/OpenBridge-Overnight/jury-final-03nov/media/v5/video_v5/suite_run.txt (fresh)
  - .../video_v5/check_run.txt + demo_smoke_run.txt
  - E:/OpenBridge-Overnight/frontier-final/video_v2/replay_video/*.webm (dd669c2, labeled)
  - Z:/OPENBRIDGE/VID_20261101_*.mp4 + start_stop_vacuum.mp4 + retour_dock*.mp4
  - docs/jury/screens/* (committed evidence stills)
Output (NOT in repo):
  - E:/OpenBridge-Overnight/jury-final-03nov/media/v5/final-jury-video-<sha>.mp4
  - video_v5/narration.srt (also burned in), thumb, SHA256SUMS, scene map.
Run from the repo root: python scripts/video/build_jury_video_v5.py
"""
import re
import subprocess
import sys
import textwrap
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent
EV2 = Path("E:/OpenBridge-Overnight/frontier-final")
EV = Path("E:/OpenBridge-Overnight/jury-final-03nov/media/v5")
STAGING = EV / "video_v5"
RUSHES = Path("Z:/OPENBRIDGE")
V4SEGS = Path("E:/OpenBridge-Overnight/overnight-02nov/v4/video_v4/segs")
REUSED_V4 = []
SCREENS = ROOT / "docs/jury/screens"
W, H, FPS = 1280, 720, 30
BG = (11, 18, 32)
FG = (235, 240, 250)
DIM = (150, 165, 190)
ACCENT = (45, 212, 191)
WARN = (251, 191, 36)
GREEN = (52, 211, 153)
REAL = (52, 211, 153)

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

SHA = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                     capture_output=True, text=True, check=True).stdout.strip()
SHA_FULL = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                          capture_output=True, text=True, check=True).stdout.strip()
BRANCH = subprocess.run(["git", "branch", "--show-current"], cwd=str(ROOT),
                        capture_output=True, text=True, check=True).stdout.strip()
TODAY = date.today().isoformat()

FONT_SANS = "C:/Windows/Fonts/arial.ttf"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"


def need(path):
    if not Path(path).exists():
        sys.exit("MISSING INPUT: %s" % path)
    return Path(path)


def font(path, size):
    return ImageFont.truetype(path, size)


def base_card():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 8], fill=ACCENT)
    d.rectangle([0, H - 8, W, H], fill=ACCENT)
    return img, d


def read_log(path):
    raw = Path(path).read_bytes()
    if b"\x00" in raw[:400]:
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def footer_rev(d):
    f = font(FONT_MONO, 18)
    d.text((W - 24, 18), "commit %s (%s) \u00b7 %s" % (SHA, BRANCH, TODAY),
           font=f, fill=DIM, anchor="ra")


def save_card(img, name):
    p = STAGING / name
    img.save(p)
    print("card:", p, flush=True)
    return p


def title_card():
    img, d = base_card()
    d.text((80, 130), "OpenBridge \u2014 Jury Cut", font=font(FONT_SANS, 56), fill=FG)
    d.text((80, 215), "FINAL FRONTIER \u00b7 with real-device footage",
           font=font(FONT_SANS, 34), fill=ACCENT)
    for i, line in enumerate([
        "Real camera footage + real captures.",
        "Every frame labeled: REAL_HARDWARE or REPLAY.",
        "Every limit labeled \u2014 nothing faked around.",
    ]):
        d.text((80, 300 + i * 44), line, font=font(FONT_SANS, 26), fill=DIM)
    footer_rev(d)
    return save_card(img, "card_title.png")


def mono_card(name, heading, tag, cmd_lines, body_text, foot_note):
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


def rows_card(name, heading, rows, foot_lines):
    img, d = base_card()
    footer_rev(d)
    d.text((80, 90), heading, font=font(FONT_SANS, 44), fill=FG)
    for i, (line, fill) in enumerate(rows):
        d.text((80, 180 + i * 50), line, font=font(FONT_SANS, 26), fill=fill)
    for j, (line, size, fill) in enumerate(foot_lines):
        d.text((80, 500 + j * 44), line, font=font(FONT_SANS, size), fill=fill)
    return save_card(img, name)


def close_card(suite_n):
    return rows_card("card_close.png", "What this video proves", [
        ("[ok] START/DOCK sent on camera + 'done, verified' + manual receipts", FG),
        ("[ok] Refusal filmed: lease-stale denial shown, nothing dispatched", FG),
        ("[ok] %s / %s tests green \u00b7 S8 gate: unsafe 4\u21920 on 48 held-out" % (suite_n, suite_n), FG),
        ("[ok] TV sleep/wake+reveal oracle-verified \u00b7 remote wakes (no power-on claim)", FG),
        ("GAP: vacuum locomotion/docking not visibly filmed (STATIC + dispatch only)", WARN),
        ("(recorded as missing, never faked \u2014 see scene map)", WARN),
    ], [("github.com/toskaman/openbridge", 30, ACCENT),
        ("Reproduce: docs/jury/VIDEO_BUILD_V5.md", 24, DIM)])


def scorecard_card():
    return rows_card("card_score.png", "Measured, not claimed", [
        ("S8 safety gate: 4 unsafe model replies \u2192 0 execute (48 held-out, $0 local)", FG),
        ("No fully-correct proposal blocked \u00b7 strict rescore on record (exit 1 + analysis)", FG),
        ("ModelStudy48: rules 36.1% vs Llama-3B 22.2% (loss published, not hidden)", FG),
        ("F90 endurance: 1128 ops, 0 shed, graceful shutdown, rerun green", FG),
        ("Glimmer 30B: 7\u00d7 env OOM on this host \u2014 reported, never a quality claim", WARN),
    ], [("docs/benchmark/modelstudy48 \u00b7 docs/benchmark/intenteffect", 22, DIM)])


def still_frame(src, top_tag, bottom_label):
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


def overlay_bar(text, name, color=WARN):
    bar = Image.new("RGBA", (W, 64), (5, 8, 16, 210))
    d = ImageDraw.Draw(bar)
    d.text((24, 14), text, font=font(FONT_SANS, 24), fill=color + (255,))
    out = STAGING / name
    bar.save(out)
    return out


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def seg_from_image(img, dur, out):
    run([FFMPEG, "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS),
         "-i", str(img), "-t", "%.2f" % dur, "-c:v", "libx264", "-pix_fmt",
         "yuv420p", "-r", str(FPS), "-an", str(out)])


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


def irl_seg(src_name, a, b, rate, bar_text, name, segs):
    """Owner camera trim [a,b) at rate with a provenance bar. Silent."""
    out = segs / ("seg_irl_" + name + ".mp4")
    if not (RUSHES / src_name).exists():
        frozen = V4SEGS / ("seg_irl_" + name + ".mp4")
        if not frozen.exists():
            sys.exit("MISSING INPUT: %s (no Z: rush, no V4 seg)" % src_name)
        import shutil
        shutil.copyfile(frozen, out)
        REUSED_V4.append(name)
        print("REUSED V4 SEG (Z: rush absent): %s" % name, flush=True)
        return out, probe_dur(out)
    src = need(RUSHES / src_name)
    bar = overlay_bar(bar_text, "bar_" + name + ".png", color=REAL)
    run([FFMPEG, "-y", "-v", "error", "-ss", "%.2f" % a, "-to", "%.2f" % b,
         "-i", str(src), "-i", str(bar), "-filter_complex",
         "[0:v]setpts=PTS/%.3f,scale=1280:720:force_original_aspect_ratio=decrease,"
         "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x050810,fps=30,format=yuv420p[bg];"
         "[bg][1:v]overlay=0:0" % rate,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)])
    return out, probe_dur(out)


# EDL: (rush, t_in, t_out, rate, bar text, seg name). See VIDEO_IRL_PLAN.md.
EDL = [
    ("VID_20261101_183541.mp4", 30.0, 34.0, 1.0, "REAL_HARDWARE \u00b7 01-Nov \u00b7 VID_183541 t=30-34 \u00b7 Ask THINKING", "ask1"),
    ("VID_20261101_183541.mp4", 40.0, 46.0, 1.5, "REAL_HARDWARE \u00b7 VID_183541 t=40-46 @1.5x \u00b7 inference wait", "ask2"),
    ("VID_20261101_182957.mp4", 48.0, 54.0, 1.0, "REAL_HARDWARE \u00b7 tx-8abdd1eb \u00b7 START press", "start"),
    ("VID_20261101_183541.mp4", 80.0, 82.0, 1.0, "REAL_HARDWARE \u00b7 button verifies (no tx, outside script)", "pause"),
    ("VID_20261101_185018.mp4", 8.0, 12.0, 1.0, "REAL_HARDWARE \u00b7 tx-63ee07451c \u00b7 DOCK press", "dockpress"),
    ("VID_20261101_185018.mp4", 16.0, 20.0, 2.0, "REAL_HARDWARE \u00b7 vacuum in room @2x (STATIC, no motion claimed)", "vacuum"),
    ("VID_20261101_185018.mp4", 26.0, 29.5, 1.0, "REAL_HARDWARE \u00b7 tx-63ee07451c \u00b7 done, verified 18:50:28", "dockok"),
    ("VID_20261101_183952.mp4", 15.0, 20.0, 1.0, "REAL_HARDWARE \u00b7 ADVERSE DISCLOSED \u00b7 lease stale", "lease"),
    ("VID_20261101_185018.mp4", 30.0, 32.5, 1.0, "REAL_HARDWARE \u00b7 relay_revoke VERIFIED \u00b7 NOT PAIRED", "revoke"),
]


# EDL2: 02-Nov footage. See PHYSICAL_EVIDENCE_VERIFICATION.md for the forensic
# basis of every trim and bar. x8 files are accelerated copies (factor stated
# in filename, unverified from bytes); floor beats are STATIC (no locomotion
# demonstrated); the refusal is a stale-lease denial, labeled exactly.
EDL2 = [
    ("start_stop_vacuum.mp4", 1.5, 5.5, 1.0, "REAL_HARDWARE \u00b7 02-Nov \u00b7 THINKING 'start vacuum'", "nlthink"),
    ("start_stop_vacuum.mp4", 8.0, 12.0, 1.0, "REAL_HARDWARE \u00b7 remote + Sending...", "newsend"),
    ("start_stop_vacuum.mp4", 22.0, 24.5, 1.0, "REAL_HARDWARE \u00b7 'Start vacuum: done, verified'", "newdone"),
    ("start_stop_vacuum.mp4", 15.0, 19.0, 1.0, "REAL_HARDWARE \u00b7 vacuum present, LEDs on (STATIC)", "newfloor"),
    ("retour_dock_copie_acceleree_x8.mp4", 7.5, 9.5, 1.0, "REAL_HARDWARE \u00b7 Dock vacuum \u00b7 Sending (accel. copy)", "newdock"),
    ("retour_dock_copie_acceleree_x8.mp4", 11.0, 14.0, 1.0, "ACCELERATED COPY \u00b7 vacuum near dock (STATIC, no arrival shown)", "newdockfloor"),
    ("retour_dock_noperm_copie_acceleree_x8.mp4", 6.0, 12.0, 1.0, "REAL_HARDWARE \u00b7 'Unavailable: lease stale' \u00b7 NOTHING DISPATCHED", "newdeny"),
]


def main():
    STAGING.mkdir(parents=True, exist_ok=True)
    segs = STAGING / "segs"
    segs.mkdir(exist_ok=True)
    for stale in segs.glob("seg_*.mp4"):
        stale.unlink()

    suite_lines = [ln for ln in read_log(need(STAGING / "suite_run.txt")).splitlines() if ln.strip()]
    if not any(l.strip() == "OK" for l in suite_lines[-8:]):
        sys.exit("suite_run.txt does not end OK; refusing to render stale numbers")
    suite_tail = "\n".join(suite_lines[-6:])
    smoke_txt = read_log(need(STAGING / "demo_smoke_run.txt")).strip()
    check_txt = read_log(need(STAGING / "check_run.txt")).strip()

    t0 = title_card()
    t1 = mono_card("card_suite.png", "Full test suite \u2014 actual output",
                   "SCREEN RENDER OF VERBATIM LOG \u00b7 NOT DEVICE FOOTAGE",
                   ["$ python -m unittest discover -s tests -q"],
                   suite_tail, "exit 0 \u00b7 full log: video_v5/suite_run.txt")
    t2 = mono_card("card_checks.png", "Replay checks \u2014 actual output",
                   "SCREEN RENDER OF VERBATIM LOG \u00b7 NOT DEVICE FOOTAGE",
                   ["$ python scripts/run/demo_fallback.py --check",
                    "$ python -m tests.e2e.demo_replay_smoke"],
                   check_txt + "\n" + smoke_txt,
                   "both exit 0 \u00b7 recorded this session on this commit")
    t3 = scorecard_card()
    _m = re.search(r"Ran (\d+) tests", "\n".join(suite_lines))
    SUITE_N = _m.group(1) if _m else "????"
    t5 = close_card(SUITE_N)

    problem = [
        ("fabric-real-1440.png", "REAL TOPOLOGY STILL (committed)",
         "docs/jury/screens/fabric-real-1440.png \u00b7 one fabric, many devices"),
        ("ask-openbridge-1440.png", "NEW-UI STILL (committed 1 Nov)",
         "docs/jury/screens/ask-openbridge-1440.png \u00b7 ask in plain language"),
    ]
    s5b = [
        ("s5b_installed.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "s5b_installed.png \u00b7 Meta T2 panel \u00b7 Glimmer 30B de878ce3\u2026"),
        ("s5b_pressed.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "docs/jury/screens/s5b_pressed.png \u00b7 after hold-press FIND \u00b7 tx-4a96f8f6"),
        ("s5b_revoked.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "docs/jury/screens/s5b_revoked.png \u00b7 after revoke: controls gone"),
    ]
    s5c = [
        ("s5c_01nov_manual_installed.png", "REAL_HARDWARE STILL (01 Nov, manual run)",
         "s5c_01nov_manual_installed.png \u00b7 panel installed \u00b7 attempt 2"),
        ("s5c_01nov_manual_press_dock.png", "REAL_HARDWARE STILL (01 Nov, manual run)",
         "s5c_01nov_manual_press_dock.png \u00b7 Dock verified \u00b7 tx-63ee07451c"),
        ("s5c_01nov_manual_revoked.png", "REAL_HARDWARE STILL (01 Nov, manual run)",
         "s5c_01nov_manual_revoked.png \u00b7 CONTROLS None + activity log"),
    ]
    watch = [
        ("g04-watch-quick-controls.png", "WATCH STILL + RECEIPT (no camera footage)",
         "g04-watch-quick-controls.png \u00b7 QUICK CONTROLS on the real watch"),
        ("g04-watch-press-ack.png", "WATCH STILL + RECEIPT (no camera footage)",
         "press ack \u00b7 tx-5b326915 \u00b7 R1 22\u219223 + R4 23\u219224"),
        ("tv-wd7-direct-drain-caption.png", "REAL_HARDWARE STILL (committed 31 Oct)",
         "tv-wd7-direct-drain-caption.png \u00b7 direct-LAN signed report"),
    ]
    safety = [
        ("refusal_channel.png", "REFUSAL STILL (committed)",
         "docs/jury/screens/refusal_channel.png \u00b7 refusal shown, not hidden"),
        ("activity-v2-refused-1440.png", "SEEDED-UI STILL \u00b7 REAL REFUSAL PAYLOAD",
         "activity-v2-refused-1440.png \u00b7 refused press in Activity timeline"),
    ]
    frames_problem = [still_frame(SCREENS / n, t, l) for n, t, l in problem]
    frames_s5b = [still_frame(SCREENS / n, t, l) for n, t, l in s5b]
    frames_s5c = [still_frame(SCREENS / n, t, l) for n, t, l in s5c]
    frames_watch = [still_frame(SCREENS / n, t, l) for n, t, l in watch]
    frames_safety = [still_frame(SCREENS / n, t, l) for n, t, l in safety]

    webm = sorted((EV2 / "video_v2" / "replay_video").glob("*.webm"))[0]
    bar = overlay_bar("OFFLINE REPLAY \u00b7 SIMULATED \u00b7 recorded rev dd669c2 \u00b7 no hardware touched",
                      "lower_third.png")
    replay_seg = segs / "seg_replay.mp4"
    run([FFMPEG, "-y", "-v", "error", "-ss", "5", "-to", "25", "-i", str(webm), "-i", str(bar),
         "-filter_complex", "[0:v]format=yuv420p,fps=30[bg];[bg][1:v]overlay=0:0",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(replay_seg)])

    seg_files, marks = [], {}

    def add_card(img, dur, name, mark=None):
        out = segs / (name + ".mp4")
        seg_from_image(img, dur, out)
        seg_files.append(out)
        if mark:
            marks[mark] = len(seg_files)

    def add_stills(frames, dur, prefix, mark=None):
        for f in frames:
            out = segs / ("seg_" + f.stem + ".mp4")
            seg_from_image(f, dur, out)
            seg_files.append(out)
        if mark:
            marks[mark] = len(seg_files)

    NEW = {nm: (src, a, b, rate, text) for src, a, b, rate, text, nm in EDL2}

    def add_new(nm):
        src, a, b, rate, text = NEW[nm]
        out, _ = irl_seg(src, a, b, rate, text, nm, segs)
        seg_files.append(out)

    # HOOK: filmed dispatch + verified + manual receipts.
    add_new("newsend")
    add_new("newdone")
    COLD = ("start", "dockpress", "dockok")
    for src, a, b, rate, text, nm in EDL:
        if nm in COLD:
            out, _ = irl_seg(src, a, b, rate, text, nm, segs)
            seg_files.append(out)
    marks["hook"] = len(seg_files)
    add_card(t0, 6.0, "seg_title", "title")
    add_stills(frames_problem, 4.0, "problem", "problem")
    # META: NL thinking + Glimmer panel stills.
    add_new("nlthink")
    add_stills(frames_s5b, 4.0, "s5b", "meta")
    add_card(t1, 10.0, "seg_suite", "suite")
    add_card(t2, 8.0, "seg_checks", "checks")
    seg_files.append(replay_seg)
    marks["replay"] = len(seg_files)
    for src, a, b, rate, text, nm in EDL:
        if nm not in COLD:
            out, _ = irl_seg(src, a, b, rate, text, nm, segs)
            seg_files.append(out)
    add_new("newdock")
    add_new("newdockfloor")
    add_new("newfloor")
    marks["irl"] = len(seg_files)
    add_stills(frames_s5c, 4.0, "s5c", "s5c")
    add_new("newdeny")
    marks["deny"] = len(seg_files)
    add_stills(frames_safety, 4.0, "safety", "safety")
    add_stills(frames_watch, 4.0, "watch", "watch")
    add_card(t3, 8.0, "seg_score", "score")
    add_card(t5, 8.0, "seg_close", "close")

    durs = [probe_dur(p) for p in seg_files]
    bounds, t = [0.0], 0.0
    for du in durs:
        t += du
        bounds.append(t)
    total = bounds[-1]
    b = marks
    cues = [
        (bounds[0], bounds[b["hook"]], "Pressed by hand. Sent by TV.\nVerified on a real vacuum."),
        (bounds[b["hook"]], bounds[b["title"]], "OpenBridge turns disconnected hardware\ninto one permission-aware system."),
        (bounds[b["title"]], bounds[b["problem"]], "Our homes are full of devices\nthat were never designed to work together."),
        (bounds[b["problem"]], bounds[b["meta"]], "Meta AI reads the request \u2014\nand composes the missing control."),
        (bounds[b["meta"]], bounds[b["suite"]], "The full suite: %s tests, passing\non the recorded commit." % SUITE_N),
        (bounds[b["suite"]], bounds[b["checks"]], "The offline replay checks pass:\nscripted receipts, zero live calls."),
        (bounds[b["checks"]], bounds[b["replay"]], "The real interface replays recorded receipts.\nEvery stage is labeled simulated."),
        (bounds[b["replay"]], bounds[b["replay"] + 2], "Ask in plain language \u2014 Meta AI\ncomposes new controls, and the TV obeys."),
        (bounds[b["replay"] + 2], bounds[b["replay"] + 3], "Every button answers:\npresses verify live."),
        (bounds[b["replay"] + 3], bounds[b["replay"] + 4], "The vacuum stands by, unmoving:\ndispatch verified, motion never claimed."),
        (bounds[b["replay"] + 4], bounds[b["replay"] + 5], "When the device refuses,\nthe refusal is shown, not hidden."),
        (bounds[b["replay"] + 5], bounds[b["replay"] + 6], "Revocation removes every control.\nRe-press is denied."),
        (bounds[b["replay"] + 6], bounds[b["replay"] + 7], "A second command, same chain:\nDock, sent and shown."),
        (bounds[b["replay"] + 7], bounds[b["replay"] + 8], "The vacuum waits by its dock.\nPresent and lit \u2014 arrival not filmed."),
        (bounds[b["replay"] + 8], bounds[b["irl"]], "Start confirmed on screen.\nThe device stands by, unmoving."),
        (bounds[b["irl"]], bounds[b["s5c"]], "November first: the same chain,\npressed by hand, verified twice."),
        (bounds[b["s5c"]], bounds[b["deny"]], "Without permission, nothing happens:\nthe refusal is shown, not hidden."),
        (bounds[b["deny"]], bounds[b["safety"]], "Nothing runs without approval,\nand every refusal is shown."),
        (bounds[b["safety"]], bounds[b["watch"]], "Even the watch can drive another machine \u2014\nwith consent, and a read-back receipt."),
        (bounds[b["watch"]], bounds[b["score"]], "Local Meta models, measured honestly:\nsafety from the deterministic gate."),
        (bounds[b["score"]], bounds[b["close"]], "OpenBridge \u2014 Meta AI that commands real hardware,\nprovably."),
    ]
    srt = STAGING / "narration.srt"
    with open(srt, "w", encoding="utf-8") as fh:
        for i, (x, y, text) in enumerate(cues, 1):
            fh.write("%d\n%s --> %s\n%s\n\n" % (i, srt_time(x), srt_time(y), text))
    print("srt:", srt, "total %.2fs" % total, flush=True)

    lst = segs / "concat.txt"
    with open(lst, "w", encoding="utf-8") as fh:
        for path in seg_files:
            fh.write("file '%s'\n" % str(path).replace("'", "'\\''"))
    silent = segs / "full_silent.mp4"
    run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i",
         str(lst), "-c", "copy", str(silent)])
    out = EV / ("final-jury-video-%s.mp4" % SHA)
    srt_filter = "subtitles='" + str(srt).replace("\\", "/").replace(":", "\\:") + "'"
    run([FFMPEG, "-y", "-v", "error", "-i", str(silent), "-vf", srt_filter,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
         "-preset", "medium", "-an", str(out)])
    dur = probe_dur(out)
    size = out.stat().st_size
    print("VIDEO: %s" % out, flush=True)
    print("DURATION: %.2fs  SIZE: %d bytes (%.1f MB)" % (dur, size, size / 1e6), flush=True)
    print("SHA_FULL: %s" % SHA_FULL, flush=True)
    (STAGING / "build_meta.txt").write_text(
        "video=%s\nduration_s=%.2f\nsize_bytes=%d\nsha=%s\nbranch=%s\ndate=%s\nreused_v4_segs=%s\n"
        % (out, dur, size, SHA_FULL, BRANCH, TODAY, ",".join(REUSED_V4)), encoding="utf-8")
    thumb = EV / ("final-jury-video-%s-thumb.png" % SHA)
    run([FFMPEG, "-y", "-v", "error", "-ss", "%.1f" % (dur / 2), "-i", str(out),
         "-frames:v", "1", str(thumb)])
    sm = EV / ("final-jury-video-%s-SCENE_MAP.md" % SHA)
    with open(sm, "w", encoding="utf-8") as fh:
        fh.write("# Scene map \u2014 %s (%.2fs, %s)\n\n" % (out.name, dur, SHA_FULL))
        fh.write("| # | Time | Seg |\n|---|---|---|\n")
        for i, p in enumerate(seg_files):
            fh.write("| %d | %s\u2013%s | %s |\n" % (i + 1, srt_time(bounds[i])[:-4], srt_time(bounds[i + 1])[:-4], p.name))
    print("MAP:", sm, flush=True)


if __name__ == "__main__":
    main()

