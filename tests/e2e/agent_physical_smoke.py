"""Real-hardware agent UI check: requires a running server with --local-meta --agent on port 18799 and one authorized phone.
Performs ONE consented reversible change and exact Undo through the browser. Not part of CI."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE='http://127.0.0.1:18799'


def main():
    out=Path('artifacts/agent');out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for width,act in ((390,False),(1440,True)):
            page=browser.new_page(viewport={'width':width,'height':900})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(BASE,wait_until='networkidle')
            page.get_by_text('Agent ready.',exact=False).wait_for()
            page.get_by_role('radio',name='Android USB').check()
            page.get_by_role('button',name='List USB devices').click()
            page.get_by_text('Inventory complete',exact=False).wait_for(timeout=30000)
            page.get_by_role('button',name='Inspect evidence').first.click()
            page.get_by_text('Reading complete. No device was changed.',exact=True).wait_for(timeout=70000)
            page.get_by_role('radio',name='Declutter optional apps').check()
            page.get_by_role('button',name='Ask Meta for a plan').click()
            page.get_by_text('Policy gate:',exact=False).wait_for(timeout=120000)
            page.locator('#agent').screenshot(path=str(out/f'{width}-plan.png'))
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),'horizontal overflow'
            if act and page.get_by_role('button',name='Execute approved step').is_visible():
                assert page.get_by_role('button',name='Execute approved step').is_disabled()
                page.locator('#agent-consent').check()
                page.get_by_role('button',name='Execute approved step').click()
                page.get_by_text('Change verified on the phone.',exact=False).wait_for(timeout=60000)
                page.locator('#agent').screenshot(path=str(out/f'{width}-executed.png'))
                page.get_by_role('button',name='Undo exactly').click()
                page.get_by_text('Loop complete',exact=False).wait_for(timeout=60000)
                page.locator('#agent').screenshot(path=str(out/f'{width}-undone.png'))
                print('AGENT_UI_LOOP_PASS')
            assert not errors,errors
            print(width,'steps:',page.locator('#agent-steps').inner_text().replace('\n',' | '))
            page.close()
        browser.close()


if __name__=='__main__':
    main()
