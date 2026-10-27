"""Actual live local-Meta browser evidence, synthetic source, under three minutes."""
import json
from pathlib import Path
import subprocess
import threading
import time
from playwright.sync_api import sync_playwright,expect
from src.forge.demo_host import create_forge_server
from src.forge.local_models import IsolatedGlimmerCPU
from src.forge.planner_v2 import SchemaConstrainedPlanner

def main():
 out=Path('artifacts/forge-glimmer-demo');out.mkdir(parents=True,exist_ok=False)
 s=create_forge_server(0,SchemaConstrainedPlanner(IsolatedGlimmerCPU()));worker=threading.Thread(target=s.serve_forever,daemon=True);worker.start();scenes=[];responses=[]
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(headless=True);ctx=b.new_context(viewport={'width':1920,'height':1080},record_video_dir=str(out),record_video_size={'width':1920,'height':1080});page=ctx.new_page();page.on('response',lambda r:responses.append(r) if r.url.endswith('/api/plan') else None)
   page.goto(f'http://127.0.0.1:{s.server_port}',wait_until='networkidle');start=time.monotonic()
   def scene(name,text):
    page.evaluate("""text=>{let e=document.querySelector('#film-caption');if(!e){e=document.createElement('div');e.id='film-caption';document.body.append(e);}Object.assign(e.style,{position:'fixed',bottom:'22px',left:'15%',width:'70%',padding:'17px 25px',background:'#0b1210f2',color:'#fff1da',border:'1px solid #c29164',font:'23px/1.4 Segoe UI,sans-serif',zIndex:'9999',borderRadius:'6px'});e.textContent=text;}""",text)
    scenes.append({'at_seconds':round(time.monotonic()-start,2),'name':name,'caption':text});print('Scene:',name,flush=True)
   def hold(until):
    remaining=until-(time.monotonic()-start)
    if remaining>0:time.sleep(remaining)
   scene('intro','OpenBridge Capability Forge. This is the SIMULATED fallback: a real local service and a live local Meta call, using synthetic relay observations. No physical scan or change occurs.')
   hold(5);page.locator('#refresh-fixture').click();page.select_option('#planner','glimmer');page.locator('#plan').click();scene('live-meta','LIVE REQUEST: pinned Meta Muse Glimmer, running locally on CPU. No provider credits or cloud fallback. The model may propose a plan; it cannot authorize publication.')
   hold(25);page.locator('.path').scroll_into_view_if_needed();scene('path','A workspace reads through an approved relay. The fixture TV observes a nearby signal source. Permissions, provenance and freshness are checked by deterministic policy.')
   hold(45);page.locator('#consent').scroll_into_view_if_needed();scene('waiting','The local model is processing the complete structured proposal. Even a valid proposal cannot grant consent, invent an approved primitive, or change a device.')
   remaining=max(1,110-(time.monotonic()-start));expect(page.locator('#plan-result')).to_contain_text('Path proposed',timeout=remaining*1000)
   trace=responses[-1].json();assert trace['source']=='LOCAL_META' and trace['planner_version']==2
   page.locator('#plan-result').scroll_into_view_if_needed();scene('validated','ACTUAL GLIMMER OUTPUT: read the verified relay observations, then publish a read-only local service. Exact IDs, transition order, evidence and post-inference freshness passed validation.')
   hold(106);page.locator('#consent').check();page.locator('#publish').click();expect(page.locator('#operation')).to_contain_text('published');scene('consent','Only now does the owner consent. The host rereads the source before publishing; model text is never executed as code.')
   hold(114);page.locator('#test').scroll_into_view_if_needed();page.locator('#test').click();expect(page.locator('#output')).to_contain_text('rssi_dbm');scene('http-read','The authenticated local API returns signal strength, source, observation time and evidence. The response explicitly says simulation=true. No temperature or battery measurement is invented.')
   hold(120);page.locator('#documents').click();expect(page.locator('#output')).to_contain_text('3.1.0');scene('contract','A deterministic compiler emits OpenAPI 3.1, standalone schemas and a fixed Python client. This service uses approved read primitives only.')
   hold(131);page.locator('#remove').scroll_into_view_if_needed();page.locator('#remove').click();expect(page.locator('#operation')).to_contain_text('Stopped and removed')
   check=page.evaluate("""async()=>{const session=await(await fetch('/api/session')).json();const headers={Authorization:'Bearer '+session.token};const catalog=await(await fetch('/api/catalog',{headers})).json();const r=await fetch(catalog.observation_path,{headers});return {verification_probe:true,http_status:r.status,response:await r.json()};}""");assert check['http_status']==404;page.locator('#output').evaluate('(e,v)=>e.textContent=JSON.stringify(v,null,2)',check);page.locator('#output').scroll_into_view_if_needed();scene('revoked','A real authenticated verification probe now returns HTTP 404: SERVICE_REMOVED. Removing this virtual service does not alter the runtime relay or a phone setting.')
   hold(145);page.locator('#performance').scroll_into_view_if_needed();scene('limits','The unfavorable v1 benchmark is retained. This constrained v2 development success is not an intelligence-advantage claim. Physical phone-relay snapshots are separate runtime-owner evidence; this recording stays synthetic.')
   hold(160);scene('closing','github.com/toskaman/openbridge · feat/capability-forge · Meta Muse Glimmer actually used locally. Provider cost: $0. Validated proposal, owner consent, local API, and clean revocation.')
   hold(170);video=page.video;ctx.close();raw=video.path();b.close()
 finally:s.shutdown();s.server_close();worker.join()
 manifest={'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'mode':'SIMULATED','model_calls':1,'hardware_calls':0,'cloud_calls':0,'model_trace':trace,'revocation_probe':check,'scenes':scenes,'raw_video':str(raw),'audio':'intentionally silent, English captions'}
 (out/'capture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print('Capture complete:',raw,flush=True)
if __name__=='__main__':main()
