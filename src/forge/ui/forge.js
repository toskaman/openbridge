'use strict';
let token,busy=false,planned=false,published=false,available=false,simulation=true,fixtureReset=false,observationPath=null,modelControls=false,removing=false,contextVersion=0;
const $=s=>document.querySelector(s);
function updateJourney(){const step=published?2:planned?1:0;document.querySelectorAll('[data-flow-step]').forEach((item,index)=>{item.classList.toggle('is-current',index===step);item.classList.toggle('is-complete',index<step);if(index===step)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');});}
function controls(){updateJourney(); $('#model-memory-controls').hidden=!modelControls;$('#model-prepare').disabled=busy;$('#model-release').disabled=busy; $('#refresh-main').hidden=available;$('#refresh-main').disabled=busy;$('#refresh-main').textContent=fixtureReset?'Refresh demo evidence':'Refresh source availability'; $('#planner').disabled=busy;$('#refresh-fixture').hidden=!fixtureReset;$('#refresh-fixture').disabled=busy;$('#refresh-source').disabled=busy;$('#plan').disabled=busy||!available;$('#publish').disabled=busy||!available||!planned||!$('#consent').checked||published;$('#remove').disabled=removing||!published;$('#test').disabled=busy||!published||!available;$('#documents').disabled=busy||!published||!available; }
async function api(path,body){const headers={'Authorization':'Bearer '+token};if(body!==undefined)headers['Content-Type']='application/json';const r=await fetch(path,{method:body===undefined?'GET':'POST',headers,body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});const v=await r.json();if(!r.ok)throw Error(v.error||'Request failed');return v;}
async function requestForContext(path,body,version){
 try{const result=await api(path,body);return version===contextVersion?result:null;}
 catch(error){if(version===contextVersion)throw error;return null;}
}
function sourceLabels(v){
 simulation=v.mode==='SIMULATED';document.body.dataset.sourceMode=simulation?'simulated':'physical';fixtureReset=v.fixture_reset_enabled===true;
 $('#source-pill').textContent=simulation?'SIMULATED FIXTURE':'PHYSICAL / READ-ONLY';
 $('#source-mode').textContent=simulation?'SIMULATED / CONTRACT DEMO':'TRUSTED RUNTIME / READ-ONLY';
 $('#source-description').textContent=simulation?'This walkthrough uses synthetic observations. It does not discover, scan or change physical devices.':'Observations come from the trusted runtime provider. Every read rechecks provenance, permissions and freshness. No scan or device change is started here.';
 $('#consent-description').textContent=simulation?'I approve publishing this simulated read-only service.':'I approve publishing these verified read-only observations on this PC.';
 if(!fixtureReset){
  $('#capability-path').setAttribute('aria-label',simulation?'Simulated provider capability path':'Trusted runtime capability path');
  $('#relay-label').textContent=simulation?'SIMULATED RELAY':'VERIFIED RELAY';$('#relay-title').textContent=simulation?'Fixture relay':'Authorized relay';$('#relay-detail').textContent='Current relay permissions required · no beacon control';
  $('#target-label').textContent=simulation?'SIMULATED OBSERVATION':'PHYSICAL OBSERVATION';$('#target-title').textContent=simulation?'Simulated signal source':'Observed signal source';$('#target-detail').textContent='Verified signal strength only; no inferred measurements.';
  $('#workspace-detail').textContent='This service reads the observation through the bound relay.';
  $('#twin-label').textContent=simulation?'RELAY / SIMULATED PROVIDER':'RELAY / TRUSTED RUNTIME';$('#twin-title').textContent=simulation?'Fixture relay':'Authorized relay';$('#target-twin-label').textContent=simulation?'OBSERVATION / SIMULATED PROVIDER':'OBSERVATION / TRUSTED RUNTIME';
  $('#supported-facts').textContent='Signal strength from the bound relay. No device name, battery, temperature or manufacturer measurement is inferred.';
  $('#source-footer').textContent=simulation?'Injected simulated provider · no hardware proof':'Trusted runtime provider · physical observations · read-only';
 }
 if(v.manifest)$('#twin-identity').textContent=fixtureReset?'tv-demo · fixture-only pseudonym':v.manifest.relay_id+(simulation?' · simulated provider':' · private identifier hidden');
}
async function catalog(){
 const v=await api('/api/catalog');sourceLabels(v);modelControls=v.model_controls_available===true;available=v.available===true;published=v.services.length>0;observationPath=v.observation_path;
 $('#history').textContent=JSON.stringify(v.history,null,2);
 $('#freshness').textContent=v.manifest?'Observed: '+new Date(v.manifest.observed_at*1000).toISOString()+'. Maximum age: '+v.manifest.max_age_seconds+' seconds.':'Unavailable: '+v.error+'. Publication and reads are blocked; an existing service can still be removed.';
 if(!available){planned=false;$('#plan-result').textContent=(v.error==='OBSERVATION_EXPIRED'?'These observations have expired. ':'Current observations are unavailable. ')+(fixtureReset?'Refresh demo evidence before planning.':'Refresh source availability to check current permissions and observations.');$('#path-state').textContent='UNAVAILABLE · '+v.error;$('#twin-identity').textContent='Current source unavailable';}
 if(v.error==='WORKSPACE_CLOSED')$('#plan-result').textContent='This bound workspace is closed. Return to relay selection to create another; late requests cannot republish it.';
 $('#planner-state').textContent=v.glimmer_configured?'Local Muse Glimmer configured. Requests still require an explicit click.':'Local Muse Glimmer unavailable. You may explicitly select the rules baseline; no automatic fallback occurs.';controls();
}
async function perform(fn,refreshSource=true){if(busy)return;busy=true;controls();$('#operation').textContent='Working…';try{await fn();}catch(e){$('#operation').textContent='Blocked: '+e.message;if(!planned)$('#plan-result').textContent='No accepted plan. Review the error or explicitly choose another planning method.';}finally{busy=false;if(refreshSource)await catalog().catch(()=>{});controls();}}
function modelMemory(operation){return perform(async()=>{
 const version=contextVersion;
 const status=$('#local-model-status');status.textContent=operation==='prepare'?'Preparing the local planner. No observations are being sent.':'Releasing local planner memory…';
 try{
  await api('/api/model-'+operation,{});
  if(version!==contextVersion){status.textContent=operation==='prepare'?'Local planner prepared. The service remains removed.':'Local planner memory released. The service remains removed.';return;}
  if(operation==='prepare'){
   status.textContent='Local planner prepared. Memory is retained for up to five idle minutes.';
   planned=false;available=false;$('#plan-result').textContent='Planner prepared. Refresh current evidence before planning.';$('#path-state').textContent='Refresh evidence to begin a new plan';
  }else status.textContent='Local planner memory released. Device permissions and services were not changed.';
  $('#operation').textContent='Local model memory '+(operation==='prepare'?'prepared':'released')+'. No device evidence was read or sent by this operation.';
 }catch(error){status.textContent='Local planner '+(operation==='prepare'?'preparation':'memory release')+' not confirmed. '+error.message;if(version!==contextVersion)return;throw error;}
},false);}
$('#model-prepare').addEventListener('click',()=>modelMemory('prepare'));
$('#model-release').addEventListener('click',()=>modelMemory('release'));
$('#refresh-source').addEventListener('click',()=>perform(async()=>{await catalog();$('#operation').textContent=available?'Availability refreshed. No scan or device change performed.':'Source remains unavailable. You can remove an existing service.';}));
function refreshFixture(){return perform(async()=>{contextVersion++;await api('/api/reset-fixture',{});planned=false;published=false;$('#consent').checked=false;$('#plan-result').textContent='Fixture refreshed. Run a new plan.';$('#output').textContent='Synthetic fixture refreshed; no physical reading occurred.';$('#operation').textContent='SIMULATED fixture refreshed; previous service revoked.';});}
$('#refresh-fixture').addEventListener('click',refreshFixture);
$('#refresh-main').addEventListener('click',()=>{if(fixtureReset)return refreshFixture();return perform(async()=>{await catalog();$('#operation').textContent=available?'Current source is available. No scan or device change performed.':'Source remains unavailable; existing services can still be removed.';});});
$('#consent').addEventListener('change',controls);
$('#planner').addEventListener('change',()=>{planned=false;$('#plan-result').textContent='Planning method changed. Run a new plan.';controls();});
$('#plan').addEventListener('click',()=>perform(async()=>{const version=contextVersion;planned=false;$('#plan-result').textContent='Checking the capability path…';const v=await requestForContext('/api/plan',{planner:$('#planner').value},version);if(!v)return;planned=v.plan.decision==='propose';$('#plan-result').textContent=planned?'Path proposed by '+(v.source==='LOCAL_META'?v.model_id:'deterministic rules')+'. Read relay observations → publish a read-only service. Your consent is still required.':'No safe path is currently available.';$('#path-state').textContent=planned?(fixtureReset?'Selected: workspace → simulated TV → simulated beacon':simulation?'Selected: workspace → fixture relay → simulated signal':'Selected: workspace → authorized relay → verified signal observation'):'Unavailable: requirements are not satisfied';$('#output').textContent=JSON.stringify(v,null,2);$('#operation').textContent='Planning complete. No device action performed.';}));
$('#publish').addEventListener('click',()=>perform(async()=>{
 if(!planned||!$('#consent').checked)return;
 let v;
 try{v=await api('/api/publish',{consent:true});}
 catch(error){
  if(error.message==='PUBLICATION_VERIFICATION_FAILED'){
   published=false;planned=false;$('#consent').checked=false;
   $('#output').textContent='First observation verification failed. The newly created service was removed. Refresh source availability and create a new plan before granting consent again.';
  }
  throw error;
 }
 published=true;$('#output').textContent=JSON.stringify(v.verification,null,2);
 $('#operation').textContent=(simulation?'SIMULATED service':'Read-only observation service')+' published on this PC. First observation read verified; evidence shown below.';
}));
$('#test').addEventListener('click',()=>perform(async()=>{const v=await requestForContext(observationPath,undefined,contextVersion);if(!v)return;$('#output').textContent=JSON.stringify(v,null,2);$('#operation').textContent='Local read succeeded. '+(simulation?'Synthetic':'Trusted runtime')+' relay provenance and freshness checked.';}));
$('#documents').addEventListener('click',()=>perform(async()=>{const v=await requestForContext('/api/documents',undefined,contextVersion);if(!v)return;$('#output').textContent=JSON.stringify(v,null,2);}));
$('#remove').addEventListener('click',async()=>{
 if(removing||!published)return;
 removing=true;contextVersion++;planned=false;controls();
 try{
  await api('/api/remove',{});published=false;$('#consent').checked=false;
  $('#output').textContent='Service removed. Its observation route now returns SERVICE_REMOVED.';
  $('#operation').textContent='Stopped and removed. Pending proposals are ignored. The runtime relay and device settings were not changed.';
  $('#plan-result').textContent='Service removed. Start a new plan when ready.';
  $('#path-state').textContent='REVOKED · observation route disabled';
 }catch(error){$('#operation').textContent='Removal not confirmed: '+error.message;}
 finally{removing=false;await catalog().catch(()=>{});controls();}
});
(async()=>{try{token=(await (await fetch('/api/session',{cache:'no-store'})).json()).token;await catalog();}catch(e){$('#operation').textContent='Workspace unavailable: '+e.message;}})();
