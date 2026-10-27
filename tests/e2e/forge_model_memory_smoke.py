"""Explicit model-memory controls in a real browser, with a controlled no-model planner."""
import threading
from playwright.sync_api import sync_playwright,expect
from src.forge.demo_host import create_forge_server
from src.forge.compiler import ForgeError
class Planner:
 supports_model_control=True
 def __init__(self):self.calls=[];self.fail=False
 def prepare(self):
  if self.fail:raise ForgeError('META_UNAVAILABLE')
  self.calls.append('prepare');return {'state':'ready','elapsed_ms':10,'keep_alive_seconds':300,'tokens_generated':0,'device_data_read':False,'authorizes_execution':False}
 def release(self):self.calls.append('release');return {'state':'released','elapsed_ms':1,'device_data_read':False,'authorizes_execution':False}
def main():
 planner=Planner();server=create_forge_server(0,planner);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True)
   for width in (390,768,1440,3440):
    planner.calls=[];planner.fail=False;page=b.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle');assert planner.calls==[]
    page.get_by_role('button',name='Prepare local planner',exact=True).click();expect(page.locator('#local-model-status')).to_contain_text('prepared')
    page.get_by_role('button',name='Release planner memory',exact=True).click();expect(page.locator('#local-model-status')).to_contain_text('released')
    assert planner.calls==['prepare','release'];planner.fail=True;page.get_by_role('button',name='Prepare local planner',exact=True).click();expect(page.locator('#local-model-status')).to_contain_text('not confirmed')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;page.close()
   b.close()
 finally:server.shutdown();server.server_close();t.join()
 print('Explicit prepare/release and unavailable states passed at four widths; no actual model or hardware calls.')
if __name__=='__main__':main()
