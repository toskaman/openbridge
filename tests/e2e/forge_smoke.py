"""Reproducible four-width Forge walkthrough. Headless browser, fixtures only."""
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright,expect
from src.forge.demo_host import create_forge_server

def main():
    output=Path('artifacts/forge-browser');output.mkdir(parents=True,exist_ok=True)
    server=create_forge_server(0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();rows=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for width in (390,768,1440,3440):
                page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
                expect(page.locator('[data-flow-step=plan]')).to_have_attribute('aria-current','step')
                page.screenshot(path=str(output/f'forge-{width}.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),width
                page.get_by_role('button',name='Find a safe path').click()
                expect(page.locator('#operation')).to_contain_text('META_UNAVAILABLE')
                page.get_by_role('button',name='Refresh simulated fixture').click()
                expect(page.locator('#operation')).to_contain_text('fixture refreshed')
                page.select_option('#planner','rules');page.get_by_role('button',name='Find a safe path').click()
                expect(page.locator('#plan-result')).to_contain_text('Path proposed')
                expect(page.locator('[data-flow-step=approve]')).to_have_attribute('aria-current','step')
                assert page.locator('#publish').is_disabled()
                page.locator('#consent').check();page.get_by_role('button',name='Build local service').click()
                expect(page.locator('#operation')).to_contain_text('published')
                expect(page.locator('#operation')).to_contain_text('First observation read verified')
                expect(page.locator('[data-flow-step=use]')).to_have_attribute('aria-current','step')
                expect(page.locator('#output')).to_contain_text('rssi_dbm')
                page.get_by_role('button',name='Test the local service').click();expect(page.locator('#output')).to_contain_text('rssi_dbm')
                page.get_by_role('button',name='View API contract').click();expect(page.locator('#output')).to_contain_text('3.1.0')
                page.get_by_role('button',name='Stop & remove service').click();expect(page.locator('#operation')).to_contain_text('Stopped and removed')
                expect(page.locator('[data-flow-step=plan]')).to_have_attribute('aria-current','step')
                page.keyboard.press('Tab');assert page.evaluate('document.activeElement.tagName')!='BODY'
                assert not errors,errors
                rows.append({'width':width,'javascript_errors':errors,'lifecycle':'passed','mode':'SIMULATED'})
                page.close()
            browser.close()
    finally:server.shutdown();server.server_close();thread.join()
    (output/'verification.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
    print('Forge browser checks passed at four widths. No hardware or model calls.')
if __name__=='__main__':main()
