'use strict';
const discoverButton = document.querySelector('#discover');
const statusLine = document.querySelector('#status');
const devicePanel = document.querySelector('#device');
let csrfToken;
let generation = 0;
let metaSessionConfigured = false;
let metaLocal = false;
let runtimeMetaModel = 'muse-spark-1.3';
let inspectedDevice = null;
let metaPending = false;
const metaButton = document.querySelector('#meta-advice');
const source = () => document.querySelector('input[name="source"]:checked').value;
async function request(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || 'Request denied'); error.guide = result.guide; throw error; }
  return result;
}
function element(tag, content, className) {
  const item = document.createElement(tag);
  if (content !== undefined) item.textContent = String(content);
  if (className) item.className = className;
  return item;
}
let agentEnabled = false;
let agentPlan = null;
function syncAgent() {
  const b = document.querySelector('#agent-plan');
  if (b) b.disabled = !(agentEnabled && source() === 'android' && inspectedDevice);
}
function syncMetaControl() {
  syncAgent();
  metaButton.disabled = !metaSessionConfigured || metaPending || !(source() === 'demo' || (metaLocal && source() === 'android' && inspectedDevice));
}
function resetEvidence() {
  inspectedDevice = null; syncMetaControl();
  document.querySelector('#report').replaceChildren(element('p', 'No inspection for this source.'));
}
async function inspect(device, button, selectedSource, version) {
  button.disabled = true;
  statusLine.textContent = 'Reading authorized device facts…';
  try {
    if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
    const result = await request('/api/inspect', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ device_id: device.id, source: selectedSource }),
    });
    if (version !== generation) return;
    inspectedDevice = device.id; syncMetaControl();
    const report = document.querySelector('#report');
    report.replaceChildren(element('strong', result.summary), element('p', `${result.simulated ? 'SIMULATED / SYNTHETIC' : `${result.source} / REAL READING`} · ${result.observed_at}`));
    const facts = element('div', undefined, 'evidence-facts');
    for (const evidence of result.evidence) facts.append(element('span', `${evidence.key}: ${evidence.value} · ${evidence.source}`));
    report.append(facts);
    for (const check of result.checks) {
      const row = element('div', undefined, 'check');
      const detail = element('div');
      detail.append(element('strong', check.name), element('p', check.detail));
      row.append(element('span', check.status, 'badge'), detail); report.append(row);
    }
    statusLine.textContent = result.simulated ? 'Inspection complete. Synthetic evidence only.' : 'Reading complete. No device was changed.';
  } catch (error) {
    if (version !== generation) return;
    resetEvidence(); statusLine.textContent = `Reading failed: ${error.message}. List devices again.`; csrfToken = undefined;
  } finally { button.disabled = false; }
}
function renderDevice(device, selectedSource, version) {
  const card = element('article', undefined, 'device-card');
  const top = element('div', undefined, 'device-top');
  top.append(element('span', device.transport || 'FIXTURE', 'eyebrow'), element('span', device.simulated ? 'SIMULATED' : selectedSource === 'freebox' ? 'PUBLIC IDENTITY' : (device.state === 'device' ? 'AUTHORIZED' : device.state.toUpperCase()), 'badge'));
  card.append(top, element('h3', device.name, 'device-name'));
  if (device.simulated) {
    card.append(element('p', `${device.platform} · Synthetic facts`));
    const facts = element('div', undefined, 'facts');
    for (const [value, label] of [[`${device.facts.battery_percent}%`, 'Synthetic battery'], [`${device.facts.storage_free_gb} GB`, 'Synthetic storage'], [`${device.facts.screen_timeout_seconds}s`, 'Synthetic timeout']]) {
      const fact = element('div'); fact.append(element('strong', value), element('span', label)); facts.append(fact);
    }
    card.append(facts);
  } else if (selectedSource === 'freebox') {
    card.append(element('p', 'Public gateway identity only. No pairing or access to router settings.'));
  } else card.append(element('p', device.state === 'unauthorized' ? 'Authorize USB debugging on your phone, then list devices again.' : device.state === 'offline' ? 'Device offline. Check the cable or start the emulator.' : 'Read access authorized · Private identifier hidden.'));
  if (device.capabilities.includes('inspect')) {
    const button = element('button', 'Inspect evidence →', 'secondary');
    button.addEventListener('click', () => inspect(device, button, selectedSource, version)); card.append(button);
  }
  return card;
}
for (const radio of document.querySelectorAll('input[name="source"]')) radio.addEventListener('change', () => {
  generation++; resetEvidence(); devicePanel.replaceChildren(element('p', 'Source changed. Start a new inventory.'));
  document.querySelector('#device-count').textContent = 'NOT LISTED';
  const demo = source() === 'demo';
  syncTransactionControls();
  syncMetaControl();
  document.querySelector('#meta-result').textContent = demo ? 'Synthetic facts only. Explicit request required.' : metaLocal && source() === 'android' ? 'Inspect a device first. Approved numeric facts stay on this PC for local Meta review.' : 'Model requests are unavailable for this source.';
  discoverButton.textContent = demo ? 'Refresh demo ↗' : source() === 'android' ? 'List USB devices ↗' : 'Identify local Freebox ↗';
  const banner = document.querySelector('#mode-banner'); banner.classList.toggle('usb', !demo);
  banner.replaceChildren(element('strong', demo ? 'SIMULATED / DEMO' : source() === 'android' ? 'USB / READ-ONLY' : 'FREEBOX / PUBLIC IDENTITY'), element('span', demo ? 'Synthetic data. No real measurements.' : source() === 'android' ? 'Authorized ADB devices only. No writes.' : 'Documented discovery endpoint only. No pairing or router changes.'));
  statusLine.textContent = 'Source selected. Inventory has not started.';
  updateAndroidStream();
  if (guide.open) guide.close();
});

let demoState = null;
let transactionPending = false;
const consentInput = document.querySelector('#demo-consent');
const changeButton = document.querySelector('#demo-change');
const undoButton = document.querySelector('#demo-undo');
function syncTransactionControls() {
  const available = source() === 'demo' && demoState !== null && !transactionPending;
  consentInput.disabled = source() !== 'demo' || transactionPending;
  changeButton.disabled = !available || !consentInput.checked || Boolean(demoState.active);
  undoButton.disabled = !available || !demoState.active;
}
async function loadDemoState() {
  try {
    demoState = await request('/api/demo-setting');
    document.querySelector('#demo-setting-state').textContent = `SIMULATED · Screen timeout: ${demoState.current_value}s. ${demoState.active ? `Journal state: ${demoState.active.state}.` : 'No active transaction.'}`;
  } catch (error) {
    demoState = null;
    document.querySelector('#demo-setting-state').textContent = `Simulated journal unavailable: ${error.message}`;
  }
  syncTransactionControls();
}
consentInput.addEventListener('change', syncTransactionControls);
async function runDemoTransaction(operation) {
  if (source() !== 'demo' || transactionPending || !demoState) return;
  if (operation === 'apply' && !consentInput.checked) return;
  transactionPending = true; syncTransactionControls();
  const target = document.querySelector('#transaction-result');
  target.textContent = 'SIMULATED transaction in progress…';
  const id = operation === 'undo' ? demoState.active?.id : `ui-${crypto.randomUUID()}`;
  try {
    if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
    const result = await request('/api/demo-transaction', {
      method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},
      body:JSON.stringify({source:'demo',device_id:'demo-android',operation,transaction_id:id,
        target:demoState.current_value === 60 ? 30 : 60,consent:consentInput.checked}),
    });
    target.textContent = `SIMULATED · ${result.state}. Original: ${result.before}s. Proposed: ${result.target}s. ${result.state === 'REVERTED' ? 'Undo verified against the saved snapshot.' : 'Synthetic read-back verified. Undo is available.'} No physical device was accessed.`;
    statusLine.textContent = `SIMULATED transaction ${result.state}. No physical device was accessed.`;
    if (result.state === 'REVERTED') consentInput.checked = false;
  } catch (error) { target.textContent = `SIMULATED operation blocked: ${error.message}. Check the saved journal state.`; }
  finally { transactionPending = false; await loadDemoState(); }
}
changeButton.addEventListener('click', () => runDemoTransaction('apply'));
undoButton.addEventListener('click', () => runDemoTransaction('undo'));
loadDemoState();

request('/api/model-status').then(state => {
  metaSessionConfigured = state.inference_available ?? state.supervised_session_configured;
  metaLocal = state.inference_mode === 'local';
  agentEnabled = state.agent_enabled === true;
  if (agentEnabled) document.querySelector('#agent-result').textContent = 'Agent ready. Inspect an authorized Android phone, choose a goal, then ask Meta for a plan.';
  runtimeMetaModel = state.model_id || 'muse-spark-1.3';
  syncMetaControl();
  document.querySelector('#model-state').textContent = metaSessionConfigured
    ? metaLocal ? (runtimeMetaModel.startsWith('muse-glimmer') ? 'Meta Muse Glimmer (open weights) · local GPU/CPU · $0 provider credits' : 'Built with Llama · local CPU · $0 provider credits') : 'Meta Muse Spark 1.3 · supervised requests only · credit checks enforced'
    : 'Runtime model: disabled · credit verification required';
}).catch(() => { document.querySelector('#model-state').textContent = 'Model state unavailable. Cloud requests blocked.'; });

document.querySelector('#recorded-meta-proof').addEventListener('click', async () => {
  const target=document.querySelector('#recorded-proof-result');
  try {
    const proof=await request('/api/model-proof');
    const receipt=proof.receipt;
    target.textContent=`RECORDED RUN — ${receipt.recorded_at_utc} · ${receipt.model_id}. ${receipt.proposal.summary} Limits: ${receipt.proposal.uncertainty} Estimated cost: $${receipt.estimated_cost_usd.toFixed(6)}. This displays a previous runtime-core call; no live request was made.`;
  } catch (error) { target.textContent=`Recorded proof unavailable: ${error.message}`; }
});

metaButton.addEventListener('click', async () => {
  syncMetaControl();
  if (metaButton.disabled) return;
  const selectedSource = source();
  const deviceId = selectedSource === 'demo' ? 'demo-android' : inspectedDevice;
  const version = generation;
  const resultPanel = document.querySelector('#meta-result');
  metaButton.disabled = true;
  metaPending = true;
  resultPanel.textContent = metaLocal ? `Requesting local Meta ${runtimeMetaModel} review… Numeric facts stay on this PC.` : 'Requesting Meta Muse Spark 1.3 advice on synthetic facts…';
  try {
    if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
    const result = await request('/api/recommend', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ source: selectedSource, device_id: deviceId }),
    });
    if (version !== generation) return;
    resultPanel.textContent = `${result.model_id}: ${result.proposal.summary} Evidence: ${result.proposal.evidence_refs.join(', ')}. Limits: ${result.proposal.uncertainty} Estimated cost: $${result.estimated_cost_usd.toFixed(6)}. No device action performed.`;
  } catch (error) {
    if (version === generation) resultPanel.textContent = `Meta request blocked or failed: ${error.message}`;
  } finally { metaPending = false; syncMetaControl(); }
});
function inventorySignature(result) {
  return JSON.stringify(result.devices.map(device => [device.id,device.state,device.capabilities]));
}
let androidStream = null;
let lastAndroidSignature = null;
const guide = document.querySelector('#guide');
const GUIDES = {
  REQUIRES_USER_ACTION: ['Approve USB debugging on your phone', ['Unlock the phone.', 'Accept the "Allow USB debugging?" prompt (tick "Always allow from this computer" only if this is your PC).', 'If no prompt appears, unplug and reconnect the cable.']],
  WAITING_FOR_DEVICE: ['Connect your Android phone', ['Plug the phone in with a data-capable USB cable.', 'Enable Developer options › USB debugging if not already on.', 'Approve the prompt on the phone.']],
};
function guideFor(result, selectedSource) {
  if (selectedSource !== 'android') return null;
  if (result.devices.some(d => d.state === 'device')) return 'COMPLETE';
  if (result.devices.some(d => d.state === 'unauthorized')) return 'REQUIRES_USER_ACTION';
  if (result.status === 'ADB_MISSING' || result.status === 'ADB_UNAVAILABLE') return 'BLOCKED';
  return 'WAITING_FOR_DEVICE';
}
function showGuide(state) {
  if (!GUIDES[state]) { if (guide.open) guide.close(); return; }
  const [title, steps] = GUIDES[state];
  document.querySelector('#guide-state').textContent = state.replaceAll('_', ' ');
  document.querySelector('#guide-title').textContent = title;
  document.querySelector('#guide-steps').replaceChildren(...steps.map(text => element('li', text)));
  if (!guide.open) guide.show();
}
function showGuideObject(g) {
  if (!g) return;
  document.querySelector('#guide-state').textContent = `${g.issue.replaceAll('_', ' ').toUpperCase()} · ${g.vendor}`;
  document.querySelector('#guide-title').textContent = g.title;
  const items = [element('li', `Why: ${g.why}`)];
  if (g.tried && g.tried.length) items.push(element('li', `Already tried automatically: ${g.tried.join('; ')}`));
  for (const step of g.steps) items.push(element('li', step));
  items.push(element('li', g.waiting));
  document.querySelector('#guide-steps').replaceChildren(...items);
  if (!guide.open) guide.show();
}
document.querySelector('#guide-close').addEventListener('click', () => guide.close());
document.querySelector('#guide-recheck').addEventListener('click', () => discoverButton.click());
function renderInventory(result, selectedSource, version) {
  if (version !== generation) return;
  const devices = result.devices;
  if (selectedSource === 'android') lastAndroidSignature = inventorySignature(result);
  document.querySelector('#device-count').textContent = `${devices.length} ${selectedSource === 'demo' ? 'SIMULATED DEVICE' : selectedSource === 'android' ? 'ADB DEVICE(S)' : 'LOCAL GATEWAY(S)'}`;
  devicePanel.replaceChildren(...devices.map(device => renderDevice(device, selectedSource, version)));
  if (!devices.length) {
    const messages = { ADB_MISSING:'ADB is missing. Install the official Android platform tools.', ADB_UNAVAILABLE:'ADB is unavailable. Check the connection and retry.', WAITING_FOR_DEVICE:'No device detected. Connect a phone and authorize USB debugging.', GATEWAY_UNAVAILABLE:'No compatible Freebox responded. Check your local connection; no network scan was performed.' };
    devicePanel.append(element('p', messages[result.status] || 'No device available.'));
  }
  showGuide(guideFor(result, selectedSource));
  statusLine.textContent = selectedSource === 'demo' ? 'Demo loaded. No real measurements.' : selectedSource === 'freebox' ? `Gateway identification complete: ${devices.length} public identity response(s).` : `Inventory complete: ${devices.filter(d => d.state === 'device').length} authorized device(s).`;
}
function updateAndroidStream() {
  if (androidStream) { androidStream.close(); androidStream = null; }
  lastAndroidSignature = null;
  if (source() !== 'android') return;
  const stream = new EventSource('/api/device-events?source=android');
  androidStream = stream;
  const unavailable = () => {
    if (androidStream !== stream) return;
    stream.close(); androidStream = null;
    statusLine.textContent = 'Live Android updates unavailable. Manual listing remains available.';
  };
  stream.onmessage = event => {
    if (source() !== 'android' || androidStream !== stream) return;
    try {
      const result = JSON.parse(event.data);
      if (!Array.isArray(result.devices)) throw new Error('Invalid inventory event');
      if (result.type === 'unavailable') {
        resetEvidence(); renderInventory(result,'android',++generation); unavailable(); return;
      }
      const signature = inventorySignature(result);
      if (signature === lastAndroidSignature) return;
      resetEvidence(); renderInventory(result,'android',++generation);
    } catch { unavailable(); }
  };
  stream.onerror = unavailable;
}
window.addEventListener('pagehide', () => { if (androidStream) androidStream.close(); });

discoverButton.addEventListener('click', async () => {
  discoverButton.disabled = true;
  const selectedSource = source(); const version = ++generation;
  resetEvidence(); devicePanel.replaceChildren(element('p', 'Listing devices…')); statusLine.textContent = 'Listing devices…';
  if (selectedSource === 'android' && !androidStream) updateAndroidStream();
  try {
    const result = await request(`/api/devices?source=${selectedSource}`);
    renderInventory(result,selectedSource,version);
  } catch (error) { if (version === generation) statusLine.textContent = `Inventory failed: ${error.message}. Try again.`; }
  finally { discoverButton.disabled = false; }
});

const agentSteps = document.querySelector('#agent-steps');
const agentResult = document.querySelector('#agent-result');
const agentExecute = document.querySelector('#agent-execute');
const agentUndo = document.querySelector('#agent-undo');
const agentConsent = document.querySelector('#agent-consent');
function agentStep(label, text, cls) {
  const li = element('li', undefined, cls); li.append(element('strong', label + ': '), document.createTextNode(text)); agentSteps.append(li);
}
async function agentPost(path, extra) {
  if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
  return request(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ source: 'android', device_id: inspectedDevice, ...extra }) });
}
document.querySelector('#agent-plan').addEventListener('click', async event => {
  const button = event.currentTarget; button.disabled = true; agentPlan = null;
  agentSteps.replaceChildren(); agentExecute.hidden = true; agentUndo.hidden = true;
  document.querySelector('#agent-consent-row').hidden = true; agentConsent.checked = false;
  const goal = document.querySelector('input[name="agent-goal"]:checked').value;
  agentResult.textContent = 'Observing the phone and asking the local Meta model for a plan… (about 10 s on CPU)';
  try {
    const plan = await agentPost('/api/agent-plan', { goal });
    agentStep('Observe', `ADB facts ${Object.entries(plan.facts).map(([k, v]) => k + '=' + v).join(', ')}; ${Object.keys(plan.candidates).length} allowlisted optional apps found`);
    agentStep('Meta plan', `${plan.model.model_id} (${plan.model.elapsed_ms} ms, $0): ${plan.model.proposal.summary}`);
    const allowed = plan.gate.decision === 'REVIEW_REQUIRED';
    agentStep('Policy gate', `${plan.gate.decision} — ${plan.gate.reasons.join(' ')}`, allowed ? 'ok' : (plan.gate.decision === 'DENY' ? 'deny' : ''));
    agentPlan = plan;
    if (allowed) {
      document.querySelector('#agent-consent-row').hidden = false; agentExecute.hidden = false; agentExecute.disabled = true;
      agentResult.textContent = 'Review the step. Execution requires your explicit consent.';
    } else agentResult.textContent = 'No action will run. The agent stops here safely.';
  } catch (error) {
    agentResult.textContent = `Agent stopped safely: ${error.message}`;
    if (error.message.includes('recover it')) document.querySelector('#agent-recover').hidden = false;
  }
  finally { syncAgent(); }
});
agentConsent.addEventListener('change', () => { agentExecute.disabled = !agentConsent.checked || !agentPlan; });
agentExecute.addEventListener('click', async () => {
  agentExecute.disabled = true; agentResult.textContent = 'Snapshotting exact state, executing, reading back…';
  try {
    const r = await agentPost('/api/agent-execute', { plan_id: agentPlan.plan_id, consent: agentConsent.checked });
    agentStep('Act + verify', `${r.package} is now disabled-user; independent read-back verified (Android state ${r.before_code - 1} → ${r.observed_code - 1})`, 'ok');
    agentExecute.hidden = true; document.querySelector('#agent-consent-row').hidden = true; agentUndo.hidden = false;
    agentResult.textContent = 'Change verified on the phone. Undo restores the exact original state.';
  } catch (error) { agentStep('Act', error.message, 'deny'); agentResult.textContent = 'Execution blocked; original state preserved.'; }
});
agentUndo.addEventListener('click', async () => {
  agentUndo.disabled = true;
  try {
    const r = await agentPost('/api/agent-undo', { plan_id: agentPlan.plan_id });
    agentStep('Undo', `exact original state restored and verified (Android state ${r.restored_code - 1})`, 'ok');
    agentUndo.hidden = true; agentResult.textContent = 'Loop complete: plan → gate → consent → act → verify → exact Undo.';
  } catch (error) { agentStep('Undo', error.message, 'deny'); }
  finally { agentUndo.disabled = false; }
});

document.querySelector('#agent-recover').addEventListener('click', async event => {
  const button = event.currentTarget; button.disabled = true;
  try {
    const r = await agentPost('/api/agent-recover', {});
    for (const item of r.recovered) agentStep('Recover', `${item.package}: exact original state restored from the journal (Android state ${item.restored_code - 1})`, 'ok');
    button.hidden = true; agentResult.textContent = 'Recovery complete. You can plan again.';
  } catch (error) { agentStep('Recover', error.message, 'deny'); }
  finally { button.disabled = false; }
});

// ---- Device Fabric ----
const fabricTree = document.querySelector('#fabric-tree');
const fabricDetail = document.querySelector('#fabric-detail');
let fabric = null;
function chip(text, cls) { return element('span', text, cls); }
function renderFabric(snap) {
  fabric = snap;
  const devices = new Map(snap.devices.map(d => [d.key, d]));
  document.querySelector('#fabric-meta').textContent = `${snap.devices.length} DEVICE(S) · ${snap.links.length} LINK(S)${snap.elapsed_ms !== undefined ? ' · ' + snap.elapsed_ms + ' MS' : ''}`;
  const providers = document.querySelector('#fabric-providers'); providers.replaceChildren();
  for (const [name, info] of Object.entries(snap.providers || {})) {
    const ok = ['OK', 'AUTHENTICATED'].includes(info.status);
    const extra = info.instances !== undefined ? ` · ${info.instances} services` : info.devices !== undefined ? ` · ${info.devices} devices` : info.lan_hosts !== undefined ? ` · ${info.lan_hosts} active LAN hosts${info.inactive_hidden ? ' (+' + info.inactive_hidden + ' inactive hidden)' : ''}` : '';
    providers.append(element('li', `${name.toUpperCase()}: ${info.status}${info.authorization ? ' (' + info.authorization + ')' : ''}${extra}`, ok ? 'ok' : (info.status || '').match(/UNAVAILABLE|NOT_SUPPORTED|BLOCKED|ERROR/) ? 'blocked' : ''));
  }
  const children = new Map();
  for (const link of snap.links) { if (!children.has(link.parent)) children.set(link.parent, []); children.get(link.parent).push(link); }
  const build = (parent, depth, seen) => {
    const list = element('ul');
    const groups = new Map();
    for (const link of children.get(parent) || []) { if (!groups.has(link.child)) groups.set(link.child, []); groups.get(link.child).push(link); }
    for (const [child, links] of groups) {
      const device = devices.get(child); if (!device || seen.has(child)) continue;
      const li = element('li');
      const node = element('button', undefined, 'fabric-node'); node.type = 'button'; node.setAttribute('aria-pressed', 'false');
      node.append(chip(device.category, 'cat'), element('span', device.label));
      if (device.possibly_same_as && device.possibly_same_as.length) node.append(chip('possible duplicate', 'grant observe'));
      const rank = { observe: 0, read: 1, control: 2 }; const perTransport = new Map();
      for (const link of links) {
        const best = link.grants.includes('control') ? 'control' : link.grants.includes('read') ? 'read' : 'observe';
        if (!perTransport.has(link.transport) || rank[best] > rank[perTransport.get(link.transport)]) perTransport.set(link.transport, best);
      }
      for (const [transport, best] of perTransport) node.append(chip(transport, 'via'), chip(best, 'grant ' + best));
      node.addEventListener('click', () => { for (const n of fabricTree.querySelectorAll('.fabric-node')) n.setAttribute('aria-pressed', 'false'); node.setAttribute('aria-pressed', 'true'); showDevice(device, links); });
      li.append(node);
      if (depth < 4) { const sub = build(child, depth + 1, new Set([...seen, child])); if (sub.childElementCount) li.append(sub); }
      list.append(li);
    }
    return list;
  };
  const root = element('li'); const pc = element('div', 'This PC (OpenBridge)', 'fabric-node'); root.append(pc, build('pc', 0, new Set()));
  fabricTree.replaceChildren(root);
  const box = snap.devices.find(d => d.category === 'router' && d.capabilities.some(c => c.name === 'lan_inventory' && c.status === 'BLOCKED'));
  document.querySelector('#freebox-authorize').hidden = !box;
}
function showDevice(device, links) {
  const table = element('table');
  const row = (k, v) => { const tr = element('tr'); tr.append(element('td', k), element('td', v)); table.append(tr); };
  row('Category', device.category);
  row('Identity', device.identifier_kinds.length ? `strong: ${device.identifier_kinds.join(', ')} (pseudonymized)` : 'no strong identifier: never merged automatically');
  if (device.possibly_same_as && device.possibly_same_as.length) row('Possibly the same device as', device.possibly_same_as.map(k => (fabric.devices.find(d => d.key === k) || {}).label || k).join(', ') + ' (weak signal such as a shared IP; not merged, no action can target both)');
  row('Reached via', links.map(l => `${l.transport} (${l.grants.join('/')}) from ${l.source}`).join('; '));
  for (const [k, f] of Object.entries(device.facts)) row(k, `${Array.isArray(f.value) ? f.value.join(', ') : f.value} · ${f.sources.join(' + ')}${f.verified ? '' : ' · reported, not verified'}`);
  const caps = element('div');
  for (const c of device.capabilities) { const p = element('p'); p.append(element('strong', c.name + ' '), chip(c.status, 'status ' + c.status), document.createTextNode(` ${c.level} via ${c.via}${c.evidence ? ' · ' + c.evidence : ''}`)); caps.append(p); }
  fabricDetail.replaceChildren(element('h3', device.label), table, element('h3', 'Capabilities'), caps.childElementCount ? caps : element('p', 'No verified capability. Observed only.'));
  const handle = (device.handles || {}).USB || (device.handles || {}).WIFI;
  if (handle && device.capabilities.some(c => c.name === 'ble_relay')) fabricDetail.append(relayPanel(device, handle));
}
async function postJson(path, body) {
  if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
  return request(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }, body: JSON.stringify(body) });
}
function relayPanel(device, handle) {
  const panel = element('div', undefined, 'relay-panel');
  const info = element('p', 'This device has Bluetooth LE. With the OpenBridge Companion app open on it, it can scan nearby Bluetooth devices for this PC.');
  const start = element('button', 'Use as Bluetooth relay', 'secondary');
  const codeRow = element('div', undefined, 'relay-code'); codeRow.hidden = true;
  const label = element('label', 'Code shown on the device'); const input = document.createElement('input');
  input.inputMode = 'numeric'; input.maxLength = 6; input.autocomplete = 'off'; input.id = 'relay-code'; label.htmlFor = 'relay-code';
  const confirm = element('button', 'Pair', 'secondary'); codeRow.append(label, input, confirm);
  const scan = element('button', 'Scan nearby Bluetooth (8 s)', 'secondary'); scan.hidden = true;
  const install = element('button', 'Install the OpenBridge Companion on this device', 'secondary'); install.hidden = true;
  const result = element('p', '', 'muted'); result.setAttribute('role', 'status');
  let relayId = null;
  start.addEventListener('click', async () => {
    start.disabled = true; result.textContent = 'Contacting the Companion over USB…';
    try { const r = await postJson('/api/relay-pair-start', { device_id: handle }); relayId = r.relay_id; codeRow.hidden = false; input.focus(); result.textContent = 'Enter the 6-digit code displayed by the Companion app.'; }
    catch (error) { result.textContent = `Companion not reachable: ${error.message}`; install.hidden = false; showGuideObject(error.guide); }
    finally { start.disabled = false; }
  });
  install.addEventListener('click', async () => {
    install.disabled = true; result.textContent = 'Installing the OpenBridge Companion over USB…';
    try {
      let st = await postJson('/api/companion-install', { device_id: handle });
      for (let i = 0; i < 300 && st.state === 'RETRYING'; i++) {
        if (st.guide) showGuideObject(st.guide);
        result.textContent = `Waiting for the device (attempt ${st.attempts || 1})…`;
        await new Promise(r => setTimeout(r, 2000)); st = await request('/api/companion-install');
      }
      if (st.state === 'INSTALLED') { if (guide.open) guide.close(); install.hidden = true; result.textContent = 'Companion installed and opened on the device. Select "Use as Bluetooth relay".'; }
      else result.textContent = `Installation not completed: ${st.code || st.state}.`;
    } catch (error) { result.textContent = `Installation not started: ${error.message}`; }
    finally { install.disabled = false; }
  });
  confirm.addEventListener('click', async () => {
    confirm.disabled = true;
    try {
      const r = await postJson('/api/relay-pair-confirm', { device_id: handle, code: input.value.trim() });
      codeRow.hidden = true; scan.hidden = false;
      const p = r.declared.permissions || {};
      result.textContent = r.eligible_for_ble ? 'Paired. Scans are allowed by the device owner.' : `Paired. Before scanning, on the device: ${p.bluetooth_on ? '' : 'turn Bluetooth on; '}${p.BLUETOOTH_SCAN ? '' : 'allow Bluetooth scanning; '}${p.owner_enabled ? '' : 'tap "Enable scans for OpenBridge".'}`;
    } catch (error) { result.textContent = `Pairing refused: ${error.message}`; showGuideObject(error.guide); }
    finally { confirm.disabled = false; }
  });
  scan.addEventListener('click', async () => {
    scan.disabled = true; result.textContent = 'The device is scanning (8 s)…';
    try { const snap = await postJson('/api/relay-scan', { device_id: handle, relay_id: relayId, seconds: 8 }); renderFabric(snap); result.textContent = `${snap.providers.relay.devices} Bluetooth advertiser(s) added under ${device.label} (observe only).`; }
    catch (error) { result.textContent = `Scan not performed: ${error.message}`; showGuideObject(error.guide); }
    finally { scan.disabled = false; }
  });
  panel.append(element('h3', 'Bluetooth relay'), info, start, install, codeRow, scan, result);
  return panel;
}
document.querySelector('#fabric-discover').addEventListener('click', async event => {
  const button = event.currentTarget; button.disabled = true;
  document.querySelector('#fabric-meta').textContent = 'DISCOVERING…';
  try {
    if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
    renderFabric(await request('/api/fabric-discover', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ device_id: 'fabric' }) }));
  } catch (error) { document.querySelector('#fabric-meta').textContent = 'DISCOVERY FAILED'; statusLine.textContent = `Discovery stopped: ${error.message}`; }
  finally { button.disabled = false; }
});
GUIDES.FREEBOX_PENDING = ['Approve OpenBridge on your Freebox', ['Look at the Freebox Server front-panel screen.', 'A request from "OpenBridge Device Fabric" is shown.', 'Press the right arrow to select ✓ (Yes) within a few minutes.']];
GUIDES.FREEBOX_DENIED = ['Freebox access was not granted', ['Nothing was changed. OpenBridge stays on public identity only.', 'You can retry at any time with "Authorize read-only Freebox inventory".']];
document.querySelector('#freebox-authorize').addEventListener('click', async event => {
  const button = event.currentTarget; button.disabled = true;
  try {
    if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
    let state = (await request('/api/freebox-authorize', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ device_id: 'freebox-local' }) })).state;
    showGuide('FREEBOX_PENDING');
    document.querySelector('#guide-steps').append(element('li', 'Read-only: LAN inventory only. Wi-Fi, DHCP, DNS and firewall stay blocked. The token is stored encrypted by Windows.'));
    for (let i = 0; i < 160 && state === 'PENDING'; i++) { await new Promise(r => setTimeout(r, 2000)); state = (await request('/api/freebox-authorization')).state; }
    if (state === 'GRANTED') { guide.close(); document.querySelector('#fabric-discover').click(); }
    else showGuide('FREEBOX_DENIED');
  } catch (error) { statusLine.textContent = `Freebox authorization stopped: ${error.message}`; }
  finally { button.disabled = false; }
});
request('/api/fabric').then(snap => { if (snap.status !== 'NOT_RUN') renderFabric(snap); }).catch(() => {});

document.querySelector('#fabric-advise').addEventListener('click', async event => {
  const button = event.currentTarget; button.disabled = true; const out = document.querySelector('#fabric-advice');
  out.textContent = 'Asking the local Meta model (it sees categories and counts only)…';
  try {
    const r = await postJson('/api/fabric-advise', { device_id: 'fabric', goal: document.querySelector('#fabric-goal').value });
    if (!r.step) { out.textContent = r.summary || 'No further step available.'; return; }
    const agree = r.rule_choice ? (r.rule_choice === r.step ? ' · same as the simple rule' : ` · simple rule would pick ${r.rule_choice}`) : '';
    out.textContent = `${r.source}: next step ${r.step}. ${r.summary || ''}${agree}`;
  } catch (error) { out.textContent = `Advice unavailable: ${error.message}`; }
  finally { button.disabled = false; }
});
