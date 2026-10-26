"""Controlled browser event tests; no device mutation and no model requests."""
import json
from playwright.sync_api import sync_playwright, expect


def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        page.add_init_script('''window.testStreams=[];window.EventSource=class {
            constructor(url){this.url=url;this.closed=false;window.testStreams.push(this);}
            close(){this.closed=true;}
        };''')
        pending=[]
        page.route('**/api/inspect',lambda route:pending.append(route))
        page.goto('http://127.0.0.1:18765',wait_until='networkidle')
        page.get_by_role('radio',name='Android USB').check()
        device={'id':'test-opaque','name':'Test Android','state':'unauthorized','source':'ADB',
                'transport':'USB','simulated':False,'capabilities':[]}
        def emit(devices):
            event={'type':'inventory','status':'READY','devices':devices}
            page.evaluate('(event)=>window.testStreams[0].onmessage({data:JSON.stringify(event)})',event)
        emit([device])
        expect(page.locator('#device')).to_contain_text('UNAUTHORIZED')
        assert page.get_by_role('button',name='Inspect evidence').count()==0
        device.update(state='device',capabilities=['inspect'])
        emit([device])
        page.get_by_role('button',name='Inspect evidence').click()
        page.get_by_text('Reading authorized device facts',exact=False).wait_for()
        device.update(state='offline',capabilities=[])
        emit([device])
        expect(page.locator('#device')).to_contain_text('OFFLINE')
        assert page.get_by_role('button',name='Inspect evidence').count()==0
        assert len(pending)==1
        pending[0].fulfill(json={'summary':'STALE_DEVICE_RESULT','simulated':False,'source':'ADB','observed_at':'test','evidence':[],'checks':[]})
        expect(page.locator('#report')).not_to_contain_text('STALE_DEVICE_RESULT')
        page.get_by_role('radio',name='Freebox gateway').check()
        assert page.evaluate('window.testStreams[0].closed')
        emit([device])
        expect(page.locator('#device')).not_to_contain_text('Test Android')
        browser.close()
    print('Controlled Android event UI passed: unauthorized/offline updates, stale-read rejection, source-change cleanup.')


if __name__=='__main__':
    main()
