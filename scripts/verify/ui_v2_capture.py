"""UI V2 evidence capture: real screenshots of the running app at the blueprint viewports.

Usage:
  python scripts/verify/ui_v2_capture.py --out artifacts/ui_v2/after [--port 18795] [--views home,devices,...]

Starts `python -m src.server` from the repo root on a loopback port, opens each view at each viewport
with headless Chromium and saves `<view>-<w>x<h>.png`. Fails (exit 1) on page errors or horizontal
page overflow. Needs Playwright + Chromium (dev only, not a runtime dependency).
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIEWPORTS = [(390, 844), (768, 1024), (1024, 768), (1280, 720), (1440, 900), (1920, 1080), (3440, 1440)]
DEFAULT_VIEWS = ['home', 'devices', 'capabilities', 'studio', 'workflows', 'activity', 'settings']


def wait_up(url, proc, timeout=60):
    for _ in range(timeout * 4):
        time.sleep(0.25)
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
    ap.add_argument('--out', required=True)
    ap.add_argument('--port', type=int, default=18795)
    ap.add_argument('--views', default=','.join(DEFAULT_VIEWS))
    ap.add_argument('--sizes', default='')
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sizes = VIEWPORTS if not args.sizes else [tuple(int(x) for x in s.split('x')) for s in args.sizes.split(',')]
    env = {**os.environ, 'PYTHONPATH': str(ROOT)}
    srv = subprocess.Popen([sys.executable, '-m', 'src.server', '--port', str(args.port)], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f'http://127.0.0.1:{args.port}/'
    failures = []
    try:
        if not wait_up(url, srv):
            print('server did not come up')
            return 1
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for w, h in sizes:
                ctx = browser.new_context(viewport={'width': w, 'height': h})
                page = ctx.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                for view in args.views.split(','):
                    page.goto(url + '#/' + view, wait_until='networkidle')
                    page.wait_for_timeout(700)
                    page.screenshot(path=str(out / f'{view}-{w}x{h}.png'))
                    if not page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'):
                        failures.append(f'{view} {w}x{h}: horizontal overflow')
                if errors:
                    failures.append(f'{w}x{h}: page errors {errors}')
                ctx.close()
            browser.close()
    finally:
        srv.terminate()
        srv.wait(10)
    for f in failures:
        print('FAIL', f)
    print(f'{len(sizes)} viewport(s) captured into {out}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
