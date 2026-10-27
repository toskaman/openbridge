"""Failed first-read cleanup and explicit recovery, using fixtures and headless DOM automation."""
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect
from src.forge.demo_host import create_forge_server


def main():
    server=create_forge_server(0)
    original=server.provider.snapshot
    failure={'armed':False,'calls':0}
    def snapshot(capability_id):
        current=original(capability_id)
        if failure['armed']:
            failure['calls']+=1
            if failure['calls']>=3:current['available']=False
        return current
    server.provider.snapshot=snapshot
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    rows=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for width in (390,768,1440,3440):
                failure.update(armed=False,calls=0)
                page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
                page.locator('#refresh-fixture').click()
                page.select_option('#planner','rules');page.locator('#plan').click()
                expect(page.locator('#plan-result')).to_contain_text('Path proposed')
                page.locator('#consent').check()
                failure.update(armed=True,calls=0)
                page.locator('#publish').click()
                expect(page.locator('#operation')).to_contain_text('PUBLICATION_VERIFICATION_FAILED')
                expect(page.locator('#output')).to_contain_text('newly created service was removed')
                expect(page.locator('#consent')).not_to_be_checked()
                expect(page.locator('#remove')).to_be_disabled()
                assert server.forge.list_services()==[]
                failure['armed']=False
                page.locator('#refresh-fixture').click();page.locator('#plan').click()
                expect(page.locator('#plan-result')).to_contain_text('Path proposed')
                expect(page.locator('#publish')).to_be_disabled()
                page.locator('#consent').check();page.locator('#publish').click()
                expect(page.locator('#operation')).to_contain_text('First observation read verified')
                expect(page.locator('#output')).to_contain_text('rssi_dbm')
                page.locator('#remove').click()
                expect(page.locator('#operation')).to_contain_text('Stopped and removed')
                assert not errors,errors
                rows.append({'width':width,'failed_publication_removed':True,'recovery_requires_consent':True,'mode':'SIMULATED'})
                page.close()
            browser.close()
    finally:server.shutdown();server.server_close();worker.join()
    output=Path('artifacts/forge-publication');output.mkdir(parents=True,exist_ok=True)
    (output/'failure-recovery.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('Publication failure cleanup and explicit recovery passed at four widths; no model/hardware calls.')


if __name__=='__main__':main()
