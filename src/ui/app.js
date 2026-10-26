'use strict';
const discoverButton = document.querySelector('#discover');
const statusLine = document.querySelector('#status');
const devicePanel = document.querySelector('#device');
let csrfToken;
let generation = 0;
const source = () => document.querySelector('input[name="source"]:checked').value;
async function request(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request denied');
  return result;
}
function element(tag, content, className) {
  const item = document.createElement(tag);
  if (content !== undefined) item.textContent = String(content);
  if (className) item.className = className;
  return item;
}
function resetEvidence() { document.querySelector('#report').replaceChildren(element('p', 'No inspection for this source.')); }
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
    const report = document.querySelector('#report');
    report.replaceChildren(element('strong', result.summary), element('p', `${result.simulated ? 'SIMULATED / SYNTHETIC' : 'ADB / REAL READING'} · ${result.observed_at}`));
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
  top.append(element('span', device.transport || 'FIXTURE', 'eyebrow'), element('span', device.simulated ? 'SIMULATED' : (device.state === 'device' ? 'AUTHORIZED' : device.state.toUpperCase()), 'badge'));
  card.append(top, element('h3', device.name, 'device-name'));
  if (device.simulated) {
    card.append(element('p', `${device.platform} · Synthetic facts`));
    const facts = element('div', undefined, 'facts');
    for (const [value, label] of [[`${device.facts.battery_percent}%`, 'Synthetic battery'], [`${device.facts.storage_free_gb} GB`, 'Synthetic storage'], [`${device.facts.screen_timeout_seconds}s`, 'Synthetic timeout']]) {
      const fact = element('div'); fact.append(element('strong', value), element('span', label)); facts.append(fact);
    }
    card.append(facts);
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
  discoverButton.textContent = demo ? 'Refresh demo ↗' : 'List USB devices ↗';
  const banner = document.querySelector('#mode-banner'); banner.classList.toggle('usb', !demo);
  banner.replaceChildren(element('strong', demo ? 'SIMULATED / DEMO' : 'USB / READ-ONLY'), element('span', demo ? 'Synthetic data. No real measurements.' : 'Authorized ADB devices only. No writes.'));
  statusLine.textContent = 'Source selected. Inventory has not started.';
});
discoverButton.addEventListener('click', async () => {
  discoverButton.disabled = true;
  const selectedSource = source(); const version = ++generation;
  resetEvidence(); devicePanel.replaceChildren(element('p', 'Listing devices…')); statusLine.textContent = 'Listing devices…';
  try {
    const result = await request(`/api/devices?source=${selectedSource}`);
    if (version !== generation) return;
    const devices = result.devices;
    document.querySelector('#device-count').textContent = `${devices.length} ${selectedSource === 'demo' ? 'SIMULATED DEVICE' : 'ADB DEVICE(S)'}`;
    devicePanel.replaceChildren(...devices.map(device => renderDevice(device, selectedSource, version)));
    if (!devices.length) {
      const messages = { ADB_MISSING: 'ADB is missing. Install the official Android platform tools.', ADB_UNAVAILABLE: 'ADB is unavailable. Check the connection and retry.', WAITING_FOR_DEVICE: 'No device detected. Connect a phone and authorize USB debugging.' };
      devicePanel.append(element('p', messages[result.status] || 'No device available.'));
    }
    statusLine.textContent = selectedSource === 'demo' ? 'Demo loaded. No real measurements.' : `Inventory complete: ${devices.filter(d => d.state === 'device').length} authorized device(s).`;
  } catch (error) { if (version === generation) statusLine.textContent = `Inventory failed: ${error.message}. Try again.`; }
  finally { discoverButton.disabled = false; }
});
