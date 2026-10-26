"""Optional browser check: install Playwright and Chromium separately."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    artifacts = Path('artifacts')
    artifacts.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width in (390, 768, 1440, 3440):
            page = browser.new_page(viewport={'width': width, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://127.0.0.1:18765', wait_until='networkidle')
            page.screenshot(path=str(artifacts / f'{width}-before.png'), full_page=True)
            page.get_by_role('button', name='Discover demo device').click()
            page.get_by_role('button', name='Inspect device evidence').click()
            page.get_by_text('Inspection complete.', exact=False).wait_for()
            assert page.get_by_text('Meta inference', exact=True).is_visible()
            assert page.locator('.check .badge').all_text_contents().count('NOT_TESTED') == 2
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            page.screenshot(path=str(artifacts / f'{width}-after.png'), full_page=True)
            page.close()
        browser.close()
    print('Browser discovery, inspection, simulation labels and overflow checks passed at 390/768/1440/3440.')


if __name__ == '__main__':
    main()
