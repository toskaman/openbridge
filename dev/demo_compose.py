"""Compose the final presentation video from one demo_record take (Windows ffmpeg).

Left: the OpenBridge live console cropped from the desktop capture (1720x1400).
Right: raw scrcpy watch mirror (top) + raw TV mirror (bottom), both --no-control.
Sync (take 20261102-204814), checked on composed frames against the console clock:
watch "Sending..." / "done" and the TV volume OSD must land on the logged press times.
Defaults --watch-delay 4.0 --tv-delay -2.5 (-itsoffset; scrcpy VFR clips -> fps=30).

    python -m dev.demo_compose <out-dir> <stamp> [--end 480] [--watch-delay 4.0] [--tv-delay -2.5]
"""
import argparse
import subprocess
import sys
from pathlib import Path

FONT = 'C\\:/Windows/Fonts/segoeui.ttf'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out_dir')
    ap.add_argument('stamp')
    ap.add_argument('--end', type=float, default=None)
    ap.add_argument('--watch-delay', type=float, default=4.0)
    ap.add_argument('--tv-delay', type=float, default=-2.5)
    a = ap.parse_args()
    d = Path(a.out_dir)
    desk, watch, tv = (d / ('%s-%s.mp4' % (n, a.stamp)) for n in ('splitscreen', 'watch', 'tv'))
    out = d / ('final-%s.mp4' % a.stamp)
    def label(text, x, y):
        return ("drawtext=fontfile='%s':text='%s':fontcolor=0xc7d2fe:fontsize=26:x=%d:y=%d"
                % (FONT, text, x, y))
    fc = ('color=c=0x0b0f17:s=2560x1440:r=30[bg];'
          '[0:v]crop=1720:1400:0:0,setpts=PTS-STARTPTS[con];'
          '[1:v]fps=30,scale=640:640[w];'
          '[2:v]fps=30,scale=820:-2[t];'
          '[bg][con]overlay=0:20:shortest=1[a];'
          '[a][w]overlay=1820:80:eof_action=repeat[b];'
          '[b][t]overlay=1730:840:eof_action=repeat,'
          + label('Galaxy Watch7  -  miroir live (lecture seule)', 1780, 30) + ','
          + label('Android TV  -  miroir live (lecture seule)', 1780, 790) + '[v]')
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-y']
    if a.end:
        cmd += ['-t', str(a.end)]
    cmd += ['-i', str(desk), '-itsoffset', str(a.watch_delay), '-i', str(watch), '-itsoffset', str(a.tv_delay), '-i', str(tv),
            '-filter_complex', fc, '-map', '[v]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)]
    print(' '.join(cmd), flush=True)
    r = subprocess.run(cmd)
    print('exit', r.returncode, out, flush=True)
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
