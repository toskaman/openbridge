"""Split-screen demo recorder (Windows, 3440x1440): console left, live watch + TV right.

    python -m dev.demo_record --watch 192.168.1.4:46719 --tv 192.168.1.15:5555 --out-dir E:/.../demo

Left half : OpenBridge live console (Chrome --app on http://127.0.0.1:18790, from dev.voice_menus_live).
Right half: scrcpy mirrors of the watch and the TV, --no-control (nothing is injected:
            every tap on the watch is the owner's finger).
Recording : ffmpeg gdigrab of the whole desktop (= the final split-screen video) +
            raw scrcpy recordings of each device. Stop by creating <out-dir>/STOP.
scrcpy uses the SYSTEM adb (ADB env) so the running adb server and its Wi-Fi links stay put.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRCPY = r'E:\OpenBridge-Overnight\tools\scrcpy-win64-v3.1\scrcpy.exe'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--watch', required=True)
    ap.add_argument('--tv', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--console', default='http://127.0.0.1:18790/')
    ap.add_argument('--max-minutes', type=float, default=20)
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    stop = out / 'STOP'
    if stop.exists():
        stop.rename(out / ('STOP.old-' + stamp))
    env = dict(os.environ)
    env.pop('ANDROID_SERIAL', None)
    env['ADB'] = shutil.which('adb') or 'adb'
    log = open(out / ('recorder-%s.log' % stamp), 'a', encoding='utf-8', buffering=1)

    def say(m):
        log.write('%s %s\n' % (datetime.now().strftime('%H:%M:%S'), m))
        print(m, flush=True)

    procs = {}
    say('ADB=%s' % env['ADB'])
    procs['chrome'] = subprocess.Popen([CHROME, '--user-data-dir=' + str(out / 'chrome-profile'), '--no-first-run',
                                        '--app=' + a.console, '--window-position=0,0', '--window-size=1720,1400'],
                                       env=env)
    time.sleep(3)
    common = ['--no-audio', '--no-control', '--no-power-on']
    procs['watch'] = subprocess.Popen([SCRCPY, '-s', a.watch, *common, '--window-title=Galaxy Watch7 - live',
                                       '--window-x=1740', '--window-y=180', '--window-width=640', '--window-height=640',
                                       '--record=' + str(out / ('watch-%s.mkv' % stamp))],
                                      env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    procs['tv'] = subprocess.Popen([SCRCPY, '-s', a.tv, *common, '--max-size=1280', '--window-title=Android TV - live',
                                    '--window-x=2400', '--window-y=300', '--window-width=1030', '--window-height=580',
                                    '--record=' + str(out / ('tv-%s.mkv' % stamp))],
                                   env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    time.sleep(4)
    desk = out / ('splitscreen-%s.mkv' % stamp)
    procs['ffmpeg'] = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-f', 'gdigrab',
                                        '-framerate', '30', '-draw_mouse', '1', '-i', 'desktop',
                                        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', '-pix_fmt', 'yuv420p',
                                        str(desk)], env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
    say('RECORDING %s (stop: create %s)' % (desk, stop))
    for k, p in procs.items():
        say('  %s pid=%s' % (k, p.pid))
    t_end = time.time() + a.max_minutes * 60
    while time.time() < t_end and not stop.exists():
        dead = [k for k in ('watch', 'tv', 'ffmpeg') if procs[k].poll() is not None]
        if dead:
            say('WARNING exited early: %s' % ','.join('%s=%s' % (k, procs[k].returncode) for k in dead))
            for k in dead:
                procs.pop(k)
            if 'ffmpeg' in dead:
                break
        time.sleep(1)
    say('STOPPING')
    f = procs.get('ffmpeg')
    if f and f.poll() is None:
        try:
            f.stdin.write(b'q')
            f.stdin.flush()
            f.wait(20)
        except Exception as e:  # noqa: BLE001
            say('ffmpeg stop: %r' % e)
            f.kill()
    for k in ('watch', 'tv', 'chrome'):
        p = procs.get(k)
        if p and p.poll() is None:
            subprocess.run(['taskkill', '/PID', str(p.pid), '/T'], capture_output=True)   # WM_CLOSE: scrcpy finalizes mkv
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
    for mkv in sorted(out.glob('*%s.mkv' % stamp)):   # remux (no re-encode) to mp4 for editors/players
        mp4 = mkv.with_suffix('.mp4')
        r = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(mkv), '-c', 'copy',
                            '-movflags', '+faststart', str(mp4)], capture_output=True, text=True)
        say('remux %s -> %s (%s)' % (mkv.name, mp4.name, 'ok' if r.returncode == 0 else r.stderr[-200:]))
    say('DONE files: %s' % ', '.join(sorted(x.name for x in out.glob('*%s*' % stamp))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
