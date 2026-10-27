"""Revocation must remain usable while an untrusted proposal is pending; late results are discarded."""
import threading
from playwright.sync_api import sync_playwright,expect
from src.forge.demo_host import create_forge_server
class ConfiguredPlanner:
 supports_model_control=True

def main():
 server=create_forge_server(0,ConfiguredPlanner());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 cases=[('#plan','/api/plan',{'source':'LOCAL_META','model_id':'muse-glimmer:30b-q4_K_M','plan':{'decision':'propose'},'late_result_marker':'SHOULD_NOT_DISPLAY'}),('#model-prepare','/api/model-prepare',{'state':'ready','elapsed_ms':10}),('#model-release','/api/model-release',{'state':'released','elapsed_ms':1})]
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True)
   for button,endpoint,response in cases:
    server.forge.publish(server.snapshot(),consent=True)
    page=b.new_page();pending=[];page.route('**'+endpoint,lambda route:pending.append(route))
    page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
    if button.startswith('#model-'):page.get_by_text('Local planner memory',exact=True).click()
    page.locator(button).click()
    expect(page.locator('#remove')).to_be_enabled(timeout=3000)
    page.locator('#remove').click();expect(page.locator('#operation')).to_contain_text('Stopped and removed');assert server.forge.list_services()==[]
    pending[0].fulfill(json=response)
    expect(page.locator('#planner')).to_be_enabled();assert page.locator('#publish').is_disabled();assert not page.locator('#consent').is_checked();assert 'SHOULD_NOT_DISPLAY' not in page.locator('#output').inner_text();expect(page.locator('#operation')).to_contain_text('Stopped and removed');page.close()
   b.close()
 finally:server.shutdown();server.server_close();thread.join()
 print('Immediate removal during proposal, prepare and release passed; late results preserve owner intent.')
if __name__=='__main__':main()
