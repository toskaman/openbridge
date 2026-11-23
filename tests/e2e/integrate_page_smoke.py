"""The "Bring your device" page: load the example API, see the mapping, download a zip whose files are exactly what
`openbridge partner new --from-openapi` writes, and whose generated tests pass. No network beyond the local server."""
import functools
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'site'))
import build_site  # noqa: E402

from src import partner_kit as kit  # noqa: E402
from src import partner_kit_api as api  # noqa: E402


def expected_files():
    doc = json.loads((ROOT / 'docs' / 'partners' / 'examples' / 'openapi.acme-glow.json').read_text(encoding='utf-8'))
    _, files = kit.plan('Acme Glow', None, 'lamp', root='/', spec=api.api_spec(doc))
    out = {str(p.relative_to(Path('/'))).replace('\\', '/'): (kit.PY_HEADER + t) if p.suffix == '.py' else (t + kit.MD_FOOTER)
           for p, t in files.items()}
    out['tests/partners/__init__.py'] = ''
    return out


def run_generated_tests(files):
    """Write the zip's files to a temporary folder, load them as modules and run their tests."""
    import importlib.util
    with tempfile.TemporaryDirectory() as d:
        for rel, text in files.items():
            (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(d) / rel).write_text(text, encoding='utf-8')
        names = []

        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            names.append(name)
            spec.loader.exec_module(module)
            return module
        try:
            load('src.adapters.acme_glow', Path(d) / 'src/adapters/acme_glow.py')
            load('src.adapters.acme_glow_emulator', Path(d) / 'src/adapters/acme_glow_emulator.py')
            load('src.fabric.acme_glow_ingest', Path(d) / 'src/fabric/acme_glow_ingest.py')
            tests = load('zip_acme_glow_tests', Path(d) / 'tests/partners/test_acme_glow.py')
            return unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        finally:
            for n in names:
                sys.modules.pop(n, None)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        site = build_site.build(Path(tmp) / '_site')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        handler = functools.partial(Quiet, directory=str(site))
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = 'http://127.0.0.1:%d/integrate.html' % server.server_port
        try:
            with sync_playwright() as p:
                browser = getattr(p, os.environ.get('OB_PLAYWRIGHT_ENGINE', 'chromium')).launch(headless=True)
                for width, lang in ((1280, 'en'), (390, 'fr')):
                    page = browser.new_page(viewport={'width': width, 'height': 900}, accept_downloads=True)
                    errors, outside = [], []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('request', lambda r: outside.append(r.url) if not r.url.startswith(('http://127.0.0.1', 'data:', 'blob:')) else None)
                    page.goto(url + '?lang=' + lang, wait_until='networkidle')
                    page.locator('#example').click()
                    expect(page.locator('#map tr')).to_have_count(14)         # 6 read, 4 settings, 2 commands, 2 refused
                    expect(page.locator('#tabs button')).to_have_count(5)
                    expect(page.locator('#code')).to_contain_text('WRITABLE = {')
                    expect(page.locator('#map')).to_contain_text('POST /firmware/update' if lang == 'en' else 'firmware')
                    with page.expect_download() as dl:
                        page.locator('#zip').click()
                    data = Path(dl.value.path()).read_bytes()
                    with zipfile.ZipFile(io.BytesIO(data)) as z:
                        assert z.testzip() is None
                        got = {n: z.read(n).decode('utf-8') for n in z.namelist()}
                    assert got == expected_files(), 'the zip differs from what the command line writes'
                    result = run_generated_tests(got)
                    assert result.wasSuccessful() and result.testsRun == 7, (result.failures, result.errors)
                    if os.environ.get('OB_SHOT'):
                        page.screenshot(path=os.environ['OB_SHOT'] + '-%s.png' % lang, full_page=True)
                    page.locator('#src').fill('{"openapi": "2.0"')
                    page.locator('#go').click()
                    expect(page.locator('#err')).not_to_be_empty()
                    assert not errors, errors
                    assert not outside, outside
                    page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print('integrate page: OK')


if __name__ == '__main__':
    main()
