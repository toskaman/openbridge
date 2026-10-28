"""Optional browser check: install Playwright and Chromium separately."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import re


def main():
    artifacts = Path('artifacts')
    artifacts.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in (390, 768, 1440, 3440):
            page = browser.new_page(viewport={'width': width, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://127.0.0.1:18765/#/advanced', wait_until='networkidle')   # inspection lives in Advanced diagnostics
            page.screenshot(path=str(artifacts / f'{width}-before.png'), full_page=True)
            page.get_by_role('button', name='Refresh demo').click()
            page.get_by_role('button', name='Inspect evidence').click()
            page.get_by_text('Inspection complete.', exact=False).wait_for()
            assert page.get_by_text('Meta inference', exact=True).is_visible()
            assert page.locator('.check .badge').all_text_contents().count('NOT_TESTED') == 2
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            page.screenshot(path=str(artifacts / f'{width}-after.png'), full_page=True)
            assert page.locator('html').get_attribute('lang') == 'en'
            assert page.get_by_role('button', name='Request Meta advice').is_disabled()
            page.get_by_role('button',name='View recorded Meta proof').click()
            page.get_by_text('RECORDED RUN',exact=False).wait_for()
            assert 'no live request was made' in page.locator('#recorded-proof-result').inner_text()
            page.goto('http://127.0.0.1:18765/#/activity')   # simulated sandbox lives in Activity & Recovery
            page.locator('#demo-consent').check()
            change=page.get_by_role('button',name='Run simulated change')
            expect(change).to_be_enabled()
            initial=page.locator('#demo-setting-state').inner_text()
            original=re.search(r'Screen timeout: (\d+)s',initial).group(1)
            change.click()
            expect(page.locator('#transaction-result')).to_contain_text('SIMULATED · VERIFIED.')
            page.reload(wait_until='networkidle')
            undo=page.get_by_role('button',name='Undo simulated change')
            expect(undo).to_be_enabled()
            undo.click()
            expect(page.locator('#transaction-result')).to_contain_text('SIMULATED · REVERTED.')
            expect(page.locator('#demo-setting-state')).to_contain_text(f'Screen timeout: {original}s.')
            page.screenshot(path=str(artifacts / f'{width}-recovery.png'),full_page=True)
            page.goto('http://127.0.0.1:18765/#/advanced')
            page.route('**/api/devices?source=demo', lambda route: route.abort())
            page.get_by_role('button', name='Refresh demo').click()
            page.get_by_text('Inventory failed:', exact=False).wait_for()
            assert page.get_by_role('button', name='Inspect evidence').count() == 0
            page.unroute('**/api/devices?source=demo')
            page.get_by_role('radio', name='Android USB').check()
            page.get_by_role('button', name='List USB devices').click()
            page.get_by_text('Inventory complete', exact=False).wait_for()
            assert 'SIMULATED' not in page.locator('#device').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(artifacts / f'{width}-usb.png'), full_page=True)
            if page.get_by_role('button',name='Inspect evidence').count():
                page.get_by_role('button',name='Inspect evidence').first.click()
                page.get_by_text('Reading complete. No device was changed.',exact=True).wait_for(timeout=70000)
                assert 'ADB / REAL READING' in page.locator('#report').inner_text()
            page.get_by_role('radio', name='Freebox gateway').check()
            page.get_by_role('button', name='Identify local Freebox').click()
            page.get_by_text('Gateway identification complete:', exact=False).wait_for()
            assert page.get_by_role('button', name='Request Meta advice').is_disabled()
            assert 'SIMULATED' not in page.locator('#device').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(artifacts / f'{width}-gateway.png'), full_page=True)
            if page.get_by_role('button',name='Inspect evidence').count():
                page.get_by_role('button',name='Inspect evidence').click()
                page.get_by_text('Reading complete. No device was changed.',exact=True).wait_for()
                assert 'FREEBOX_DISCOVERY / REAL READING' in page.locator('#report').inner_text()
            page.close()
        browser.close()
    print('Browser discovery, inspection, simulation labels and overflow checks passed at 390/768/1440/3440.')


if __name__ == '__main__':
    main()
