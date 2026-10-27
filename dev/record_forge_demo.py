"""Direct evidence recording of the actual simulated Forge browser workflow."""
import json
from pathlib import Path
import subprocess
import threading
import time
from playwright.sync_api import sync_playwright,expect
from src.forge.demo_host import create_forge_server

def main():
 output=Path('artifacts/forge-demo');output.mkdir(parents=True,exist_ok=False)
 revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
 s=create_forge_server(0);thread=threading.Thread(target=s.serve_forever,daemon=True);thread.start();scenes=[]
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True);ctx=b.new_context(viewport={'width':1920,'height':1080},record_video_dir=str(output),record_video_size={'width':1920,'height':1080});page=ctx.new_page();page.goto(f'http://127.0.0.1:{s.server_port}',wait_until='networkidle');start=time.monotonic()
   def scene(name,caption):
    page.evaluate('''text=>{let box=document.getElementById('film-caption');if(!box){box=document.createElement('div');box.id='film-caption';document.body.append(box);}Object.assign(box.style,{position:'fixed',bottom:'24px',left:'15%',width:'70%',padding:'18px 26px',background:'#0b1210f2',color:'#fff1da',border:'1px solid #c29164',font:'23px/1.4 Segoe UI,sans-serif',zIndex:'9999',borderRadius:'6px',boxShadow:'0 5px 20px #0008'});box.textContent=text;}''',caption)
    scenes.append({'at_seconds':round(time.monotonic()-start,2),'name':name,'caption':caption});print('Scene:',name,flush=True)
   def hold(until):
    remaining=until-(time.monotonic()-start)
    if remaining>0:time.sleep(remaining)
   scene('problem','Capability Forge turns verified observations into a reusable local service. This entire walkthrough is SIMULATED: no physical TV or beacon is being scanned.')
   hold(20);page.locator('.path').scroll_into_view_if_needed();scene('path','The workspace has no direct observation in this fixture. An approved TV relay supplies signal observations. A relay path never implies control of the beacon.')
   hold(39);page.locator('#plan').scroll_into_view_if_needed();page.locator('#plan').click();expect(page.locator('#operation')).to_contain_text('META_UNAVAILABLE');scene('unavailable','Honest model state: the local Glimmer route is unavailable here. Separate recorded startup attempts failed. No model success is simulated and no cloud fallback occurs.')
   hold(57);page.select_option('#planner','rules');page.locator('#plan').click();expect(page.locator('#plan-result')).to_contain_text('Path proposed');scene('explicit-rules','We explicitly choose deterministic rules. The validated plan reads existing relay observations, then proposes publication. It cannot grant consent or execute a hardware action.')
   hold(78);page.locator('#refresh-fixture').scroll_into_view_if_needed();page.locator('#refresh-fixture').click();page.select_option('#planner','rules');page.locator('#plan').click();expect(page.locator('#plan-result')).to_contain_text('Path proposed');page.locator('#consent').check();page.locator('#publish').click();expect(page.locator('#operation')).to_contain_text('published');scene('publish','After refreshing only the synthetic fixture, the owner approves publication. A real local HTTP service is created from a fixed read-only primitive, with current permission and freshness checks.')
   hold(100);page.locator('#test').scroll_into_view_if_needed();page.locator('#test').click();expect(page.locator('#output')).to_contain_text('rssi_dbm');scene('read','The local API returns actual fixture data: signal strength, relay provenance, observation time and evidence references. This is not a temperature or battery measurement.')
   hold(120);page.locator('#documents').click();expect(page.locator('#output')).to_contain_text('3.1.0');page.locator('#output').scroll_into_view_if_needed();scene('contract','The compiler emits OpenAPI 3.1, standalone JSON Schemas and a fixed Python client. Model-generated code is never executed. A separate client test verified this route and its revocation.')
   hold(137);page.locator('#remove').scroll_into_view_if_needed();page.locator('#remove').click();expect(page.locator('#path-state')).to_contain_text('REVOKED');scene('revocation','Stop and remove: the service is REVOKED. Its observation route returns 404. No device setting was changed, so physical Undo is neither needed nor claimed.')
   hold(151);page.locator('#performance').scroll_into_view_if_needed();scene('results','Measured results remain visible: rules 64/64 accepted plans; Llama 0/64; Glimmer unavailable. No intelligence advantage is claimed. Provider credits used for these local tests: $0.')
   hold(163);scene('close','OpenBridge · github.com/toskaman/openbridge · feat/capability-forge. Tested contracts and real loopback API; simulated observations. Physical relay integration remains gated on runtime evidence and timestamps.')
   hold(170);video=page.video;ctx.close();raw=video.path();b.close()
 finally:s.shutdown();s.server_close();thread.join()
 manifest={'source_revision':revision,'mode':'SIMULATED','capture':'actual headless Chromium session, no desktop control','audio':'intentionally silent; English captions','model_calls_during_capture':0,'hardware_calls_during_capture':0,'scenes':scenes,'raw_video':str(raw)}
 (output/'capture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print('Capture complete:',raw,flush=True)
if __name__=='__main__':main()
