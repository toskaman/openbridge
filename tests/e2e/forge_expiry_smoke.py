"""Expired-evidence recovery in the first planning card; no hardware/model calls."""
import threading
from playwright.sync_api import sync_playwright,expect
from src.forge.demo_host import create_forge_server

def main():
 server=create_forge_server(0);server.provider.current['observed_at']=0
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True)
   for width in (390,768,1440,3440):
    server.provider.current['observed_at']=0
    page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
    expect(page.locator('#plan-result')).to_contain_text('expired')
    refresh=page.get_by_role('button',name='Refresh demo evidence',exact=True);expect(refresh).to_be_visible();assert page.locator('#plan').is_disabled()
    refresh.click();expect(page.locator('#plan')).to_be_enabled();page.select_option('#planner','rules');page.locator('#plan').click();expect(page.locator('#plan-result')).to_contain_text('Path proposed')
    assert not errors,errors;page.close()
   browser.close()
 finally:server.shutdown();server.server_close();thread.join()
 print('Expired fixture recovery passed at four widths; zero hardware or model calls.')
if __name__=='__main__':main()
