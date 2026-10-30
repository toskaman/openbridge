/* §6 Capability Explorer: live capabilities + saved layouts. Every tap executes
   through /api/v2/execute with an explicit confirmation for effects; reads run
   directly and show their value. Nothing here invents capabilities: all data
   comes from /api/v2/capabilities/*, and a revoked grant disables the button. */
const ex = { explore: null, layouts: [], active: null, rendered: null, filter: 'all', version: 0 };

async function renderExplore() {
  const root = document.querySelector('[data-view="explore"] .explore-body');
  if (!root) return;
  if (!root.dataset.built) {
    root.dataset.built = '1';
    root.append(exToolbar(), exDialog(), element('p', '', 'muted ex-status'),
      element('div', undefined, 'explore-content'));
  }
  await exRefresh(root, true);
}

function exToolbar() {
  const bar = element('div', undefined, 'explore-bar');
  const refresh = element('button', 'Refresh', 'secondary');
  refresh.addEventListener('click', () => exRefresh(null, true));
  const filter = document.createElement('select');
  filter.setAttribute('aria-label', 'Capability filter');
  for (const [v, t] of [['all', 'Everything'], ['ready', 'Working now'],
      ['needs', 'Needs permission'], ['rest', 'Not available']]) {
    const o = document.createElement('option'); o.value = v; o.textContent = t; filter.append(o);
  }
  filter.addEventListener('change', () => { ex.filter = filter.value; exPaint(); });
  const layouts = document.createElement('select');
  layouts.id = 'ex-layouts'; layouts.setAttribute('aria-label', 'Saved layout');
  layouts.addEventListener('change', () => exSelectLayout(layouts.value));
  const name = document.createElement('input');
  name.id = 'ex-name'; name.placeholder = 'Layout name'; name.maxLength = 80;
  name.setAttribute('aria-label', 'Layout name');
  const save = element('button', 'Save these controls', 'secondary');
  save.addEventListener('click', exSaveVisible);
  const follow = document.createElement('input');
  follow.id = 'ex-follow'; follow.placeholder = 'e.g. remove everything except volume';
  follow.setAttribute('aria-label', 'Modify the layout');
  follow.addEventListener('keydown', (e) => { if (e.key === 'Enter') exFollow(follow.value); });
  const apply = element('button', 'Apply', 'secondary');
  apply.addEventListener('click', () => exFollow(follow.value));
  bar.append(refresh, filter, layouts, name, save, follow, apply);
  return bar;
}

function exDialog() {
  const d = document.createElement('dialog');
  d.id = 'ex-dialog'; d.className = 'ex-dialog';
  return d;
}

function exStatus(text) {
  const s = document.querySelector('[data-view="explore"] .ex-status');
  if (s) s.textContent = text;
}

async function exRefresh(root, full) {
  exStatus('Loading live capabilities…');
  try {
    if (full || !ex.explore) ex.explore = await request('/api/v2/capabilities/explore');
    ex.layouts = (await request('/api/v2/capabilities/layouts')).layouts || [];
    const sel = document.querySelector('#ex-layouts');
    if (sel) {
      sel.replaceChildren();
      const none = document.createElement('option'); none.value = ''; none.textContent = 'Browse everything';
      sel.append(none);
      for (const l of ex.layouts) {
        const o = document.createElement('option'); o.value = l.layout_id;
        o.textContent = `${l.name} (v${l.version})`; sel.append(o);
      }
      sel.value = ex.active || '';
    }
    if (ex.active) await exSelectLayout(ex.active, true);
    else exPaint();
    exStatus('');
  } catch (e) { exStatus('Explore failed: ' + (e.message || e)); }
}

async function exSelectLayout(id, silent) {
  ex.active = id || null;
  if (!ex.active) { ex.rendered = null; exPaint(); return; }
  try {
    ex.rendered = await request('/api/v2/capabilities/render?layout=' + encodeURIComponent(id));
    ex.version = ex.rendered.version;
    exPaint();
  } catch (e) { exStatus('Render failed: ' + (e.message || e)); if (!silent) ex.active = null; }
}

function exVisibleCaps() {
  const out = [];
  for (const d of (ex.explore || {}).devices || []) {
    const caps = d.capabilities.filter((c) => exFilter(c.status));
    if (caps.length) out.push({ device: d, caps });
  }
  return out;
}

function exFilter(status) {
  if (ex.filter === 'all') return true;
  if (ex.filter === 'ready') return status === 'READY';
  if (ex.filter === 'needs') return status === 'REQUIRES_PERMISSION';
  return !['READY', 'REQUIRES_PERMISSION'].includes(status);
}

function exPaint() {
  const box = document.querySelector('[data-view="explore"] .explore-content');
  if (!box) return;
  box.replaceChildren();
  if (ex.rendered) {
    let card = null;
    for (const w of ex.rendered.widgets) {
      if (w.kind === 'card') { card = exCard(w.label); box.append(card); continue; }
      (card || box).append(exWidget(w, w.device_key));
    }
    if (!ex.rendered.widgets.length) box.append(element('p', 'Empty layout. Browse everything, or type a follow-up like “add TV mute”.', 'muted'));
    return;
  }
  for (const { device, caps } of exVisibleCaps()) {
    const card = exCard(`${device.label} · ${device.category}${device.online ? '' : ' · offline'}`);
    for (const c of caps) card.append(exWidget({ ...c, enabled: c.status === 'READY' }, device.key));
    box.append(card);
  }
  if (!box.children.length) box.append(element('p', 'Nothing matches. Run discovery first, or change the filter.', 'muted'));
}

function exCard(title) {
  const det = document.createElement('details');
  det.className = 'panel ex-device'; det.open = true;
  const sum = document.createElement('summary'); sum.textContent = title;
  det.append(sum);
  return det;
}

function exPill(status) {
  const cls = { READY: 'available', REQUIRES_PERMISSION: 'permission', DISCOVERABLE: 'detected',
    UNSUPPORTED: 'unsupported', OFFLINE: 'offline', ERROR: 'error' }[status] || 'detected';
  return element('span', status, 'pill ' + cls);
}

function exWidget(w, deviceKey) {
  const row = element('div', undefined, 'ex-widget');
  row.append(exPill(w.status || 'DISCOVERABLE'));
  const label = element('span', w.label, 'ex-label');
  if (w.reason) label.title = w.reason;
  row.append(label);
  const out = element('span', '', 'muted ex-result');
  out.setAttribute('role', 'status');
  if (w.kind === 'slider') {
    const r = document.createElement('input');
    r.type = 'range'; r.min = w.range[0]; r.max = w.range[1]; r.step = w.step || 1;
    r.value = w.range[0]; r.disabled = !w.enabled; r.setAttribute('aria-label', w.label);
    const val = element('span', String(r.value), 'ex-val');
    r.addEventListener('input', () => { val.textContent = r.value; });
    const set = element('button', 'Set', 'secondary');
    set.disabled = !w.enabled; set.title = w.reason || '';
    set.addEventListener('click', () => exTap(w, deviceKey, { value: Number(r.value) }, out));
    row.append(r, val, set);
  } else {
    const b = element('button', w.kind === 'status' ? 'Read' : 'Run', w.kind === 'status' ? 'ghost' : 'secondary');
    b.disabled = !w.enabled; b.title = w.enabled ? '' : (w.reason || 'Not available');
    b.addEventListener('click', () => exTap(w, deviceKey, {}, out));
    row.append(b);
  }
  if (!w.enabled && w.reason) row.append(element('span', w.reason, 'muted ex-why'));
  row.append(out);
  return row;
}

async function exTap(w, deviceKey, extra, out) {
  if (!w.enabled) return;
  let args = { ...(w.args || {}), ...extra };
  if (w.prompt) {
    const v = await exPrompt(w.label, w.prompt);
    if (v === null) return;
    args[w.prompt.name] = v;
  }
  if (w.effect && !(await exConfirm(`Run “${w.label}”?`, w))) return;
  out.textContent = '…';
  try {
    const r = await postJson('/api/v2/execute', {
      primitive_id: w.primitive_id, device_key: deviceKey,
      params: exParams(w.primitive_id, w.action, args), consent: true });
    out.textContent = exSummarize(r);
  } catch (e) {
    out.textContent = 'Failed: ' + (e.message || e);
    if (/unknown|stale|graph|DEVICE_UNKNOWN/i.test(e.message || '')) exRefresh(null, true);
  }
}

function exParams(primitive, action, args) {
  if (primitive === 'device_action' || primitive === 'device_macro') return { action, args };
  if (primitive === 'device_capabilities') return {};
  return { ...args };
}

function exSummarize(r) {
  const res = r.result || {};
  const v = res.value ?? res.state ?? res.setting ?? '';
  return `${r.state || 'done'}${v === '' ? '' : ' · ' + v}`;
}

function exConfirm(message, w) {
  return new Promise((resolve) => {
    const d = document.querySelector('#ex-dialog');
    d.replaceChildren();
    d.append(element('p', message), element('p', `${w.primitive_id} · ${w.action || ''}`, 'muted'));
    const run = element('button', 'Run it'); const cancel = element('button', 'Cancel', 'secondary');
    run.addEventListener('click', () => { d.close(); resolve(true); });
    cancel.addEventListener('click', () => { d.close(); resolve(false); });
    d.append(run, cancel);
    d.showModal();
  });
}

function exPrompt(label, spec) {
  return new Promise((resolve) => {
    const d = document.querySelector('#ex-dialog');
    d.replaceChildren();
    d.append(element('p', `${label}: enter ${spec.label || spec.name}`));
    let input;
    if (spec.type === 'enum') {
      input = document.createElement('select');
      for (const o of spec.options || []) {
        const e = document.createElement('option'); e.value = o; e.textContent = o; input.append(e);
      }
    } else {
      input = document.createElement('input');
      input.type = spec.type === 'number' ? 'number' : 'text';
      input.setAttribute('aria-label', spec.label || spec.name);
    }
    const run = element('button', 'Continue'); const cancel = element('button', 'Cancel', 'secondary');
    run.addEventListener('click', () => {
      d.close();
      resolve(spec.type === 'number' ? Number(input.value) : input.value);
    });
    cancel.addEventListener('click', () => { d.close(); resolve(null); });
    d.append(input, run, cancel);
    d.showModal();
  });
}

async function exSaveVisible() {
  const name = (document.querySelector('#ex-name').value || 'Untitled layout').slice(0, 80);
  const widgets = [];
  let i = 0;
  for (const { device, caps } of exVisibleCaps()) {
    widgets.push({ widget_id: `w-card-${Date.now().toString(36)}`, kind: 'card', label: device.label });
    for (const c of caps) {
      if (!['READY', 'REQUIRES_PERMISSION'].includes(c.status)) continue;
      i += 1;
      const w = { widget_id: `w-${Date.now().toString(36)}-${i}`, kind: c.widget, label: c.label,
        capability_id: c.capability_id, device_fingerprint: c.device_fingerprint,
        primitive_id: c.primitive_id, action: c.action, args: c.args };
      if (c.range) { w.range = c.range; w.step = c.step || 1; }
      if (c.prompt) w.prompt = c.prompt;
      widgets.push(w);
    }
  }
  try {
    const r = await postJson('/api/v2/capabilities/layouts', { name, widgets });
    exStatus(`Saved “${name}”.`);
    await exRefresh(null, true);
    document.querySelector('#ex-layouts').value = r.layout_id;
    await exSelectLayout(r.layout_id);
  } catch (e) { exStatus('Save failed: ' + (e.message || e)); }
}

async function exFollow(text) {
  text = (text || '').trim();
  if (!text) return;
  try {
    if (!ex.active) {
      const r = await postJson('/api/v2/capabilities/layouts', { draft: true, name: 'Follow-ups' });
      ex.active = r.layout_id;
      await exRefresh(null, false);
    }
    const r = await postJson('/api/v2/capabilities/followup',
      { layout_id: ex.active, text, expected_version: ex.version });
    ex.version = r.version;
    await exRefresh(null, false);
    exStatus('');
  } catch (e) { exStatus('Follow-up failed: ' + (e.message || e)); }
}
