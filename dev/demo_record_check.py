"""Recorder preflight (no window, no input): 3 s desktop grab + 6 s headless scrcpy record of each device."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dev.demo_record import SCRCPY

OUT = Path(r'E:\OpenBridge-Overnight\device-frontier\demo\check')


def probe(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height:format=duration',
                        '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return (r.stdout or r.stderr).strip().replace('\n', ' | ')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop('ANDROID_SERIAL', None)
    env['ADB'] = shutil.which('adb') or 'adb'
    d = OUT / 'desk.mkv'
    r = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'gdigrab', '-framerate', '30',
                        '-t', '3', '-i', 'desktop', '-c:v', 'libx264', '-preset', 'ultrafast', str(d)],
                       capture_output=True, text=True, timeout=60)
    print('desktop', r.returncode, probe(d) if d.exists() else r.stderr[-300:])
    for name, serial in (('tv', sys.argv[1]), ('watch', sys.argv[2])):
        f = OUT / ('%s.mkv' % name)
        r = subprocess.run([SCRCPY, '-s', serial, '--no-audio', '--no-control', '--no-window', '--no-power-on',
                            '--time-limit=6', '--record=' + str(f)], env=env, capture_output=True, text=True, timeout=60)
        print(name, r.returncode, probe(f) if f.exists() else '', (r.stdout + r.stderr).strip().splitlines()[-3:])


if __name__ == '__main__':
    main()
