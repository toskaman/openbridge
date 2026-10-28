"""Read-only route inspector with contract fixtures; no device/model/dispatch calls."""
import copy
import json
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from src.server import create_server

FIX=Path(__file__).resolve().parents[1]/'contracts/b2'

def main():
 server=create_server(0);worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True)
   for width in (390,768,1440,3440):
    page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    doc=json.loads((FIX/'skill_routes_ble_relays.json').read_text())
    result={'status':200,'body':doc};requests=[]
    def route(r):
     requests.append(r.request.method);r.fulfill(status=result['status'],json=result['body'])
    page.route('**/api/v2/skill_routes?*',route)
    page.goto(f'http://127.0.0.1:{server.server_port}/#/skills',wait_until='networkidle')
    button=page.get_by_role('button',name='Refresh route snapshot',exact=True)
    expect(button).to_be_visible()
    assert not requests,'No automatic route requests'
    button.click()
    expect(page.locator('#route-truth')).to_contain_text(doc['policy']['mode'])
    expect(page.locator('#route-truth')).to_contain_text('Snapshot')
    assert requests==['GET']
    expect(page.locator('#route-truth')).to_contain_text(doc['routes'][0]['route_id'])
    result['body']=copy.deepcopy(doc);result['body']['graph_revision']['seq']-=1
    button.click();expect(page.locator('#route-truth')).to_contain_text('Outdated route snapshot refused')
    result['body']=copy.deepcopy(doc);result['body']['routes'][0]['evidence']='SIMULATED'
    button.click();expect(page.locator('#route-truth')).to_contain_text('SIMULATED')
    result['body']=copy.deepcopy(doc);result['body']['schema_version']='unknown'
    button.click();expect(page.locator('#route-truth')).to_contain_text('Unsupported or invalid')
    expect(page.locator('#route-truth .route-card')).to_have_count(0)
    result.update(status=404,body={'error':'not implemented'})
    button.click();expect(page.locator('#route-truth')).to_contain_text('Routing backend is not available')
    result.update(status=200,body=json.loads((FIX/'skill_routes_empty.json').read_text()))
    button.click();expect(page.locator('#route-truth')).to_contain_text('No eligible routes')
    assert all(m=='GET' for m in requests)
    assert not errors,errors
    page.close()
   browser.close()
 finally:server.shutdown();server.server_close();worker.join(2)
 print('Route snapshots, invalid/backend-unavailable/empty states and GET-only behavior passed at four widths.')
if __name__=='__main__':main()
