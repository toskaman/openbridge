"""Campaign Three §5.6 + judge-C W3: demo fallback browser smoke.

Hermetic: loopback server, recorded receipt bundle only. Asserts the real UI
replays S5 + S5b with unmissable REPLAY/SIMULATED labels, all 9 stages per
scenario, verbatim receipt ids, working scenario switch + scripted autoplay —
and zero POST/model/hardware calls.
"""
import threading

from playwright.sync_api import sync_playwright, expect

from src.server import create_server


def main():
    server = create_server(0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width in (390, 1440):
                page = browser.new_page(viewport={'width': width, 'height': 1000})
                errors = []
                live_calls = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                def guard(route):
                    if route.request.method != 'GET':
                        live_calls.append(route.request.url + ' ' + route.request.method)
                        route.abort()
                    else:
                        route.continue_()
                page.route('**/api/*', guard)
                page.goto(url + '/#/replay', wait_until='networkidle')
                banner = page.locator('.replay-banner')
                expect(banner).to_be_visible()
                expect(banner).to_contain_text('REPLAY')
                expect(banner).to_contain_text('SIMULATED')
                expect(banner).to_contain_text('nothing here touches live hardware')
                expect(page.locator('.replay-stage')).to_have_count(9)
                expect(page.locator('.replay-stage .tag.sim')).to_have_count(9)
                for heading in ('User intent', 'Model identity', 'Capability proposal',
                                'Validation', 'Consent', 'Interface publication',
                                'Action', 'Verification', 'Revocation'):
                    expect(page.get_by_role('heading', name=heading)).to_be_visible()
                expect(page.locator('.replay-body')).to_contain_text('tx-ab731d7b885b5e1a')
                expect(page.locator('.replay-body')).to_contain_text('NOT a manual tap')
                page.get_by_role('button', name='S5b').click()
                expect(page.locator('.replay-body')).to_contain_text('tx-4a96f8f626a1adc5')
                expect(page.locator('.replay-body')).to_contain_text('EXECUTED_UNVERIFIED')
                page.get_by_role('button', name='Play').click()
                page.wait_for_selector('.replay-stage[data-stage-idx="8"].active', timeout=20000)
                expect(page.locator('[data-replay="counter"]')).to_contain_text('Step 9 of 9')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors, errors
                assert not live_calls, live_calls
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    print('Demo fallback replay passed at 390/1440: REPLAY+SIMULATED labels, 9 stages × 2 scenarios, '
          'verbatim receipts, scripted autoplay. Zero POST/model/hardware calls.')


if __name__ == '__main__':
    main()
