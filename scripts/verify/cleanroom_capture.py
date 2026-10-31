"""Clean-room UI capture (§3.3/§15): start the extracted app server, screenshot
real views, record a short clip, fail on console errors.

Usage:
  python scripts/verify/cleanroom_capture.py --root <extracted-app> --out <dir> [--port 18791]

Produces: home.png, activity.png, diagnostics.png, tour.webm, console.log.
Needs playwright + chromium installed (CI job installs them; not a runtime dep).
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def wait_up(url, proc, timeout=60):
    for _ in range(timeout):
        time.sleep(1)
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--port', type=int, default=18791)
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    root, out = Path(args.root), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'PYTHONPATH': str(root), 'PYTHONNOUSERSITE': '1'}
    py = sys.executable
    srv = subprocess.Popen([py, '-m', 'src.server', '--port', str(args.port)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=root, env=env)
    url = f'http://127.0.0.1:{args.port}/'
    try:
        if not wait_up(url, srv):
            print('server did not come up')
            return 1
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={'width': 1280, 'height': 800},
                                      record_video_dir=str(out), record_video_size={'width': 1280, 'height': 800})
            page = ctx.new_page()
            errors, logs = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: logs.append(f'{m.type}: {m.text}') if m.type == 'error' else None)
            page.goto(url + '/#/home', wait_until='networkidle')
            page.screenshot(path=str(out / 'home.png'))
            page.goto(url + '/#/activity', wait_until='networkidle')
            page.screenshot(path=str(out / 'activity.png'))
            page.goto(url + '/#/advanced', wait_until='networkidle')
            page.screenshot(path=str(out / 'diagnostics.png'))
            page.goto(url + '/#/home', wait_until='networkidle')
            ctx.close()
            video = None
            for f in out.iterdir():
                if f.suffix == '.webm':
                    video = f
            if video is not None:
                video.rename(out / 'tour.webm')
            (out / 'console.log').write_text('\n'.join(errors + logs), encoding='utf-8')
            browser.close()
            if errors:
                print('page errors:', errors[:3])
                return 1
        print('capture OK: home/activity/diagnostics + tour.webm')
        return 0
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=15)
        except subprocess.TimeoutExpired:
            srv.kill()


if __name__ == '__main__':
    sys.exit(main())
