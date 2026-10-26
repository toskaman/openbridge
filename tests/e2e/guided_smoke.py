"""Hermetic guided-UX check: waiting -> requires user action -> authorized, at four widths. Zero device or model calls."""
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect
from src.server import create_server

STATES={'waiting':{'status':'WAITING_FOR_DEVICE','devices':[]},
        'unauthorized':{'status':'OK','devices':[{'id':'usb-1','name':'Android device','state':'unauthorized','transport':'USB','capabilities':[]}]},
        'ready':{'status':'OK','devices':[{'id':'usb-1','name':'Android device','state':'device','transport':'USB','capabilities':['inspect']}]}}


def main():
    out=Path('artifacts/guided');out.mkdir(parents=True,exist_ok=True)
    server=create_server(0,fabric_salt=b'e2e');worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for width in (390,768,1440,3440):
                current={'v':'waiting'}
                page=browser.new_page(viewport={'width':width,'height':900});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/api/devices?source=android',lambda route:route.fulfill(json=STATES[current['v']]))
                page.route('**/api/device-events?source=android',lambda route:route.fulfill(status=503,body=''))
                page.goto(url,wait_until='networkidle')
                guide=page.locator('#guide')
                page.get_by_role('radio',name='Android USB').check()
                page.get_by_role('button',name='List USB devices').click()
                expect(guide).to_be_visible();expect(guide).to_contain_text('Connect your Android phone')
                current['v']='unauthorized';page.get_by_role('button',name='Re-check now').click()
                expect(guide).to_contain_text('REQUIRES USER ACTION');expect(guide).to_contain_text('Allow USB debugging')
                page.screenshot(path=str(out/f'{width}-requires-action.png'))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                # Guide must not block the page (non-modal).
                page.get_by_role('radio',name='Simulated demo').check();expect(guide).to_be_hidden()
                page.get_by_role('radio',name='Android USB').check()
                current['v']='ready';page.get_by_role('button',name='List USB devices').click()
                expect(guide).to_be_hidden();expect(page.locator('#device')).to_contain_text('AUTHORIZED')
                assert not errors,errors
                page.close()
            browser.close()
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)
    print('Guided UX checks passed at 390/768/1440/3440: waiting, requires action, authorized auto-close, non-blocking.')


if __name__=='__main__':
    main()
