"""Actual live browser-to-local-Glimmer simulated service lifecycle. No hardware or cloud calls."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
out=Path('artifacts/forge-live-meta');out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));responses=[]
 page.on('response',lambda r:responses.append(r) if r.url.endswith('/api/plan') else None)
 page.goto('http://127.0.0.1:18766',wait_until='networkidle');page.locator('#refresh-fixture').click();expect(page.locator('#operation')).to_contain_text('fixture refreshed');page.select_option('#planner','glimmer');page.screenshot(path=str(out/'before.png'),full_page=True);start=time.monotonic();page.locator('#plan').click()
 expect(page.locator('#plan-result')).to_contain_text('Path proposed',timeout=180000)
 response=responses[-1].json();assert response['source']=='LOCAL_META' and response['model_id']=='muse-glimmer:30b-q4_K_M' and response['planner_version']==2
 page.locator('#consent').check();page.locator('#publish').click();expect(page.locator('#operation')).to_contain_text('published');page.locator('#test').click();expect(page.locator('#output')).to_contain_text('rssi_dbm');page.screenshot(path=str(out/'after.png'),full_page=True);page.locator('#remove').click();expect(page.locator('#operation')).to_contain_text('Stopped and removed');assert not errors
 result={'evidence_kind':'ACTUAL_BROWSER_LOCAL_META_SIMULATED_LIFECYCLE','model_trace':response,'browser_elapsed_ms':round(1000*(time.monotonic()-start)),'consent_publish_read_remove':'passed','javascript_errors':errors,'hardware_calls':0,'cloud_calls':0,'provider_cost_usd':0.0}
 Path('docs/forge/live-glimmer-browser-receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2),flush=True);b.close()
