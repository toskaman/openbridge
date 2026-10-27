'use strict';
let token,busy=false,planned=false,published=false,available=false,simulation=true,fixtureReset=false,observationPath=null;
const $=s=>document.querySelector(s);
function controls(){ $('#planner').disabled=busy;$('#refresh-fixture').hidden=!fixtureReset;$('#refresh-fixture').disabled=busy;$('#refresh-source').disabled=busy;$('#plan').disabled=busy||!available;$('#publish').disabled=busy||!available||!planned||!$('#consent').checked||published;$('#remove').disabled=busy||!published;$('#test').disabled=busy||!published||!available;$('#documents').disabled=busy||!published||!available; }
async function api(path,body){const headers={'Authorization':'Bearer '+token};if(body!==undefined)headers['Content-Type']='application/json';const r=await fetch(path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});const v=await r.json();if(!r.ok)throw Error(v.error||'Request failed');return v;}
function sourceLabels(v){
 simulation=v.mode==='SIMULATED';fixtureReset=v.fixture_reset_enabled===true;
 $('#source-pill').textContent=simulation?'SIMULATED FIXTURE':'PHYSICAL / READ-ONLY';
 $('#source-mode').textContent=simulation?'SIMULATED / CONTRACT DEMO':'TRUSTED RUNTIME / READ-ONLY';
 $('#source-description').textContent=simulation?'This walkthrough uses synthetic observations. It does not discover, scan or change physical devices.':'Observations come from the trusted runtime provider. Every read rechecks provenance, permissions and freshness. No scan or device change is started here.';
 $('#consent-description').textContent=simulation?'I approve publishing this simulated read-only service.':'I approve publishing these verified read-only observations on this PC.';
 if(!simulation){
  $('#capability-path').setAttribute('aria-label','Trusted runtime capability path');
  $('#relay-label').textContent='VERIFIED RELAY';$('#relay-title').textContent='Authorized relay';$('#relay-detail').textContent='Current relay permissions required · no beacon control';
  $('#target-label').textContent='PHYSICAL OBSERVATION';$('#target-title').textContent='Observed signal source';$('#target-detail').textContent='Verified signal strength only; no inferred measurements.';
  $('#workspace-detail').textContent='This service reads the observation through the bound relay.';
  $('#twin-label').textContent='RELAY / TRUSTED RUNTIME';$('#twin-title').textContent='Authorized relay';$('#target-twin-label').textContent='OBSERVATION / TRUSTED RUNTIME';
  $('#supported-facts').textContent='Signal strength from the bound relay. No device name, battery, temperature or manufacturer measurement is inferred.';
  $('#source-footer').textContent='Trusted runtime provider · physical observations · read-only';
 }
 if(v.manifest)$('#twin-identity').textContent=simulation?'tv-demo · fixture-only pseudonym':v.manifest.relay_id+' · private identifier hidden';
}
async function catalog(){
 const v=await api('/api/catalog');sourceLabels(v);available=v.available===true;published=v.services.length>0;observationPath=v.observation_path;
 $('#history').textContent=JSON.stringify(v.history,null,2);
 $('#freshness').textContent=v.manifest?'Observed: '+new Date(v.manifest.observed_at*1000).toISOString()+'. Maximum age: '+v.manifest.max_age_seconds+' seconds.':'Unavailable: '+v.error+'. Publication and reads are blocked; an existing service can still be removed.';
 if(!available){planned=false;$('#path-state').textContent='UNAVAILABLE · '+v.error;$('#twin-identity').textContent='Current source unavailable';}
 $('#planner-state').textContent=v.glimmer_configured?'Local Muse Glimmer configured. Requests still require an explicit click.':'Local Muse Glimmer unavailable. You may explicitly select the rules baseline; no automatic fallback occurs.';controls();
}
async function perform(fn){if(busy)return;busy=true;controls();$('#operation').textContent='Working…';try{await fn();}catch(e){$('#operation').textContent='Blocked: '+e.message;if(!planned)$('#plan-result').textContent='No accepted plan. Review the error or explicitly choose another planning method.';}finally{busy=false;await catalog().catch(()=>{});controls();}}
$('#refresh-source').addEventListener('click',()=>perform(async()=>{await catalog();$('#operation').textContent=available?'Availability refreshed. No scan or device change performed.':'Source remains unavailable. You can remove an existing service.';}));
$('#refresh-fixture').addEventListener('click',()=>perform(async()=>{await api('/api/reset-fixture',{});planned=false;published=false;$('#consent').checked=false;$('#plan-result').textContent='Fixture refreshed. Run a new plan.';$('#output').textContent='Synthetic fixture refreshed; no physical reading occurred.';$('#operation').textContent='SIMULATED fixture refreshed; previous service revoked.';}));
$('#consent').addEventListener('change',controls);
$('#planner').addEventListener('change',()=>{planned=false;$('#plan-result').textContent='Planning method changed. Run a new plan.';controls();});
$('#plan').addEventListener('click',()=>perform(async()=>{planned=false;$('#plan-result').textContent='Checking the capability path…';const v=await api('/api/plan',{planner:$('#planner').value});planned=v.plan.decision==='propose';$('#plan-result').textContent=planned?'Path proposed by '+(v.source==='LOCAL_META'?v.model_id:'deterministic rules')+'. Read relay observations → publish a read-only service. Your consent is still required.':'No safe path is currently available.';$('#path-state').textContent=planned?(simulation?'Selected: workspace → simulated TV → simulated beacon':'Selected: workspace → authorized relay → verified signal observation'):'Unavailable: requirements are not satisfied';$('#output').textContent=JSON.stringify(v,null,2);$('#operation').textContent='Planning complete. No device action performed.';}));
$('#publish').addEventListener('click',()=>perform(async()=>{if(!planned||!$('#consent').checked)return;await api('/api/publish',{consent:true});published=true;$('#operation').textContent=(simulation?'SIMULATED service':'Read-only observation service')+' published on this PC. Test it below.';}));
$('#test').addEventListener('click',()=>perform(async()=>{const v=await api(observationPath);$('#output').textContent=JSON.stringify(v,null,2);$('#operation').textContent='Local read succeeded. '+(simulation?'Synthetic':'Trusted runtime')+' relay provenance and freshness checked.';}));
$('#documents').addEventListener('click',()=>perform(async()=>{$('#output').textContent=JSON.stringify(await api('/api/documents'),null,2);}));
$('#remove').addEventListener('click',()=>perform(async()=>{await api('/api/remove',{});published=false;planned=false;$('#consent').checked=false;$('#output').textContent='Service removed. Its observation route now returns SERVICE_REMOVED.';$('#operation').textContent='Stopped and removed. The runtime relay remains under its existing owner permissions; this service does not revoke or alter it.';$('#path-state').textContent='REVOKED · observation route disabled';}));
(async()=>{try{token=(await (await fetch('/api/session',{cache:'no-store'})).json()).token;await catalog();}catch(e){$('#operation').textContent='Workspace unavailable: '+e.message;}})();
