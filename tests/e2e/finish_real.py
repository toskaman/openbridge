"""Real 'Finish session' run (not CI): opens the dialog, restores every listed change, prints results."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
def main():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1000})
        page.goto('http://127.0.0.1:18799/?redact',wait_until='networkidle')
        page.get_by_role('button',name='Finish session…').click()
        expect(page.locator('#finish')).to_be_visible();page.wait_for_timeout(500)
        Path('artifacts/session').mkdir(parents=True,exist_ok=True);page.screenshot(path='artifacts/session/finish-before.png')
        page.get_by_role('button',name='Restore selected').click()
        expect(page.locator('#finish-result')).not_to_be_empty(timeout=60000)
        page.screenshot(path='artifacts/session/finish-after.png')
        print(page.locator('#finish-result').inner_text());b.close()
if __name__=='__main__':main()
