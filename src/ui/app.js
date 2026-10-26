'use strict';
const discoverButton = document.querySelector('#discover');
const statusLine = document.querySelector('#status');
const devicePanel = document.querySelector('#device');
let csrfToken;

async function request(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}

function element(tag, content, className) {
  const item = document.createElement(tag);
  if (content !== undefined) item.textContent = String(content);
  if (className) item.className = className;
  return item;
}

async function inspect(device, button) {
  button.disabled = true;
  statusLine.textContent = 'Inspecting simulated facts…';
  try {
    if (!csrfToken) csrfToken = (await request('/api/session')).csrf_token;
    const result = await request('/api/inspect', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Origin: location.origin, 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ device_id: device.id }),
    });
    const report = document.querySelector('#report');
    report.replaceChildren(element('strong', result.summary), element('p', `SIMULATED · ${result.observed_at}`));
    const facts = element('div', undefined, 'evidence-facts');
    for (const evidence of result.evidence) facts.append(element('span', `${evidence.key}: ${evidence.value} · ${evidence.source}`));
    report.append(facts);
    for (const check of result.checks) {
      const row = element('div', undefined, 'check');
      const detail = element('div');
      detail.append(element('strong', check.name), element('p', check.detail));
      row.append(element('span', check.status, 'badge'), detail);
      report.append(row);
    }
    statusLine.textContent = 'Inspection complete. Synthetic evidence only; no device was changed.';
  } catch (error) {
    statusLine.textContent = `Inspection failed: ${error.message}. Retry the inspection.`;
    csrfToken = undefined;
  } finally { button.disabled = false; }
}

discoverButton.addEventListener('click', async () => {
  discoverButton.disabled = true;
  statusLine.textContent = 'Loading the simulated device…';
  try {
    const { devices } = await request('/api/devices');
    const device = devices[0];
    if (!device) throw new Error('No device available');
    document.querySelector('#device-count').textContent = `${String(devices.length).padStart(2, '0')} DEVICE`;
    const top = element('div', undefined, 'device-top');
    top.append(element('span', '◈  ANDROID / FIXTURE', 'eyebrow'), element('span', 'SIMULATED', 'badge'));
    devicePanel.replaceChildren(top, element('h3', device.name, 'device-name'), element('p', `${device.platform} · Read-only fixture`));
    const facts = element('div', undefined, 'facts');
    for (const [value, label] of [[`${device.facts.battery_percent}%`, 'Battery'], [`${device.facts.storage_free_gb} GB`, 'Free storage'], [`${device.facts.screen_timeout_seconds}s`, 'Screen timeout']]) {
      const fact = element('div'); fact.append(element('strong', value), element('span', label)); facts.append(fact);
    }
    const button = element('button', 'Inspect device evidence →', 'secondary');
    button.addEventListener('click', () => inspect(device, button));
    devicePanel.append(facts, button);
    statusLine.textContent = 'Demo device loaded. Inspect its evidence to continue.';
    button.focus();
  } catch (error) { statusLine.textContent = `Discovery failed: ${error.message}. Retry discovery.`; }
  finally { discoverButton.disabled = false; }
});
