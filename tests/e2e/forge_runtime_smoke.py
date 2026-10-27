"""Controlled runtime-mode UI checks. Fixture assertions are not hardware proof."""
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright,expect
from src.forge.fixtures import manifest
from src.forge.service import MemoryProvider
from src.forge.demo_host import create_forge_server

def main():
 out=Path('artifacts/forge-runtime-browser');out.mkdir(parents=True,exist_ok=True)
 m=manifest();m.update(service_id='runtime-signals',capability_id='runtime-capability',simulation=False,status='REAL_HARDWARE_VERIFIED')
 provider=MemoryProvider(m);server=create_forge_server(0,provider=provider,capability_id=m['capability_id']);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();rows=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True)
   for width in (390,768,1440,3440):
    provider.current['available']=True
    page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
    page.evaluate("""()=>{const p=document.createElement('p');p.textContent='CONTROLLED CONTRACT TEST / NO HARDWARE EVIDENCE';Object.assign(p.style,{position:'static',margin:'0',padding:'8px',background:'#ffe1a9',color:'#151812',zIndex:'9999',fontSize:'12px'});document.body.prepend(p)}""")
    expect(page.locator('#source-pill')).to_have_text('PHYSICAL / READ-ONLY')
    assert page.locator('#refresh-fixture').is_hidden()
    assert 'Living-room TV' not in page.locator('#relay-title').inner_text()
    page.select_option('#planner','rules');page.locator('#plan').click();expect(page.locator('#plan-result')).to_contain_text('Path proposed')
    page.locator('#consent').check();page.locator('#publish').click();expect(page.locator('#operation')).to_contain_text('Read-only observation service published')
    page.locator('#test').click();expect(page.locator('#output')).to_contain_text('"simulation": false')
    page.screenshot(path=str(out/f'runtime-controlled-{width}.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    provider.current['available']=False;page.locator('#refresh-source').click();expect(page.locator('#freshness')).to_contain_text('Unavailable:')
    assert page.locator('#publish').is_disabled() and page.locator('#test').is_disabled()
    expect(page.locator('#remove')).to_be_enabled();page.locator('#remove').click();expect(page.locator('#operation')).to_contain_text('Stopped and removed')
    assert not errors,errors
    rows.append({'width':width,'data':'CONTROLLED_FIXTURE_NOT_HARDWARE','source_label':'passed','fixture_reset_hidden':'passed','dynamic_route':'passed','outage_blocks_reads':'passed','remove_during_outage':'passed','javascript_errors':errors});page.close()
   browser.close()
 finally:server.shutdown();server.server_close();thread.join()
 (out/'verification.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8');print('Controlled runtime UI passed at four widths. No hardware or model calls.')
if __name__=='__main__':main()
