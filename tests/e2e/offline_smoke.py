"""Hermetic local browser checks: synthetic state, mocked missing hardware, zero model calls."""
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from playwright.sync_api import sync_playwright, expect
from src.adapters.simulated_setting import SimulatedSetting
from src.core.transactions import TransactionEngine
from src.server import create_server


def main():
    with TemporaryDirectory() as directory:
        adapter=SimulatedSetting(Path(directory)/'setting.sqlite')
        engine=TransactionEngine(Path(directory)/'journal.sqlite',adapter)
        server=create_server(0,demo_engine=engine)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                for width in (390,768,1440,3440):
                    page=browser.new_page(viewport={'width':width,'height':1000})
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.route('**/api/devices?source=android',lambda route:route.fulfill(json={'status':'ADB_MISSING','devices':[]}))
                    page.route('**/api/device-events?source=android',lambda route:route.fulfill(content_type='text/event-stream',body='data: {"type":"unavailable","status":"ADB_MISSING","devices":[]}\n\n'))
                    page.route('**/api/devices?source=freebox',lambda route:route.fulfill(json={'status':'GATEWAY_UNAVAILABLE','devices':[]}))
                    page.goto(url,wait_until='networkidle')
                    assert page.locator('html').get_attribute('lang')=='en'
                    page.get_by_role('button',name='Refresh demo').click()
                    page.get_by_role('button',name='Inspect evidence').click()
                    page.get_by_text('Inspection complete.',exact=False).wait_for()
                    assert page.get_by_role('button',name='Request Meta advice').is_disabled()
                    page.get_by_role('button',name='View recorded Meta proof').click()
                    page.get_by_text('RECORDED RUN',exact=False).wait_for()
                    page.locator('#demo-consent').check()
                    page.get_by_role('button',name='Run simulated change').click()
                    expect(page.locator('#transaction-result')).to_contain_text('SIMULATED · VERIFIED.')
                    page.reload(wait_until='networkidle')
                    undo=page.get_by_role('button',name='Undo simulated change');expect(undo).to_be_enabled();undo.click()
                    expect(page.locator('#transaction-result')).to_contain_text('SIMULATED · REVERTED.')
                    expect(page.locator('#demo-setting-state')).to_contain_text('Screen timeout: 30s.')
                    page.get_by_role('radio',name='Android USB').check()
                    expect(page.locator('#device')).to_contain_text('ADB is missing.')
                    assert page.get_by_role('button',name='Run simulated change').is_disabled()
                    page.get_by_role('radio',name='Freebox gateway').check()
                    page.get_by_role('button',name='Identify local Freebox').click()
                    expect(page.locator('#device')).to_contain_text('No compatible Freebox responded.')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert not errors,errors
                    page.close()
                browser.close()
        finally:
            server.shutdown();server.server_close();worker.join(timeout=5)
    print('Offline browser checks passed at 390/768/1440/3440: demo, recorded proof, reload/Undo, missing ADB/gateway. Zero physical or model calls.')


if __name__=='__main__':
    main()
