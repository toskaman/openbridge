'use strict';
/* Capability Creation Studio (UI V2) — put a control for one device on another device's screen.

   Contractual stepper, not a timed animation: each step advances only on its stated condition.
   REQUEST → DISCOVER → PROPOSE → VALIDATE → PREVIEW → CONSENT → PUBLISH → DISPATCH → VERIFY → REVOKE

   Real path (live): devices from GET /api/fabric, paired Companions from GET /api/v2/routes, skill schemas from
   GET /api/v2/skills; installation through POST /api/v2/remote_controls {relay_id, controls, consent:true}
   (owner path: CSRF + Origin enforced by the server, which re-validates every control); presses arrive as
   runtime `remote_request` events with the Executor outcome; revocation = the same endpoint with no controls.
   The Studio never authorizes anything itself and never calls a press "verified" unless the receipt says so.

   Rehearsal path: the same steps with SIMULATED source/target, no request to the runtime, every surface
   labelled SIMULATED, nothing written to Activity. */
(function (global) {
  const STEPS = [
    ['REQUEST', 'What do I want?', 'Intent understood, or one clarifying question'],
    ['DISCOVER', 'Which devices really exist?', 'Source device and paired Companion found'],
    ['PROPOSE', 'What is proposed?', 'Typed controls from the skill catalog, no free text executed'],
    ['VALIDATE', 'Is it allowed and does it match?', 'Deterministic checks pass; the server checks again at install'],
    ['PREVIEW', 'What will it look like?', 'Rendered, not executable — nothing installed'],
    ['CONSENT', 'What do I authorize?', 'You approve these exact effects'],
    ['PUBLISH', 'Is the interface on the device?', 'Companion acknowledged — not a physical effect yet'],
    ['DISPATCH', 'Was a control pressed?', 'A real press (or a run from this PC) was admitted'],
    ['VERIFY', 'Was the effect observed?', 'Receipt state: verified, sent-but-unconfirmed, or refused'],
    ['REVOKE', 'Can I turn it off?', 'Revoked: new presses are refused'],
  ];
  const DEFAULT_REQUEST = 'Put my TV volume controls on my watch';
  const S = {
    sim: false, text: DEFAULT_REQUEST, step: 0, error: '', question: null,
    devices: [], relays: [], skills: {}, source: '', relay: '', proposal: null, origin: 'template',
    checks: [], consent: false, published: null, presses: [], revoked: false, busy: false,
  };
  let root;
  /* Accessible in-page dialog (no native confirm/prompt): focus moves in, Esc cancels, focus returns. */
  function ask(message, opts) {
    opts = opts || {};
    return new Promise(resolve => {
      const back = document.activeElement;
      const dlg = h('dialog', { class: 'modal', 'aria-label': opts.title || 'Confirm' });
      const input = opts.input !== undefined ? h('input', { maxlength: '40', 'aria-label': opts.title || 'Value' }) : null;
      if (input) input.value = opts.input;
      const done = v => { dlg.close(); dlg.remove(); if (back && back.focus) back.focus(); resolve(v); };
      const ok = h('button', { class: 'primary', type: 'button', onclick: () => done(input ? input.value : true) }, opts.ok || 'Confirm');
      dlg.append(h('h2', { text: opts.title || 'Confirm' }), h('p', { text: message }), input, h('div', { class: 'transaction-actions' }, ok, h('button', { class: 'secondary', type: 'button', onclick: () => done(input ? null : false) }, 'Cancel')));
      dlg.addEventListener('cancel', e => { e.preventDefault(); done(input ? null : false); });
      if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') done(input.value); });
      document.body.append(dlg); dlg.showModal(); (input || ok).focus();
    });
  }

  function h(tag, props, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = String(v);
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    return n;
  }
  const M = () => global.OBMotion;
  const devLabel = d => (typeof displayLabel === 'function' ? displayLabel(d) : d.label) || d.key;   // eslint-disable-line no-undef
  async function get(path) { return request(path); }                                                // eslint-disable-line no-undef
  async function post(path, body) { return postJson(path, body); }                                  // eslint-disable-line no-undef

  // ---------- proposal templates (deterministic, typed) ----------
  const TEMPLATES = [
    { id: 'volume', test: /volume|louder|quieter|son\b|plus fort|moins fort/i, source: 'tv',
      make: tv => [{ label: 'Volume −', skill_id: 'tv_volume_step', target: tv, params: { direction: 'down' } }, { label: 'Volume +', skill_id: 'tv_volume_step', target: tv, params: { direction: 'up' } }],
      words: 'volume → tv_volume_step (one press up or down)' },
    { id: 'setvol', test: /volume\s*(to|à|a)\s*(\d{1,3})/i, source: 'tv',
      make: (tv, m) => [{ label: `Volume ${Math.min(100, +m[2])}`, skill_id: 'tv_volume_set', target: tv, params: { value: Math.min(100, +m[2]) } }],
      words: 'volume to N → tv_volume_set (exact, read back, exact Undo)' },
    { id: 'ble', test: /bluetooth|ble\b/i, source: null,
      make: () => [{ label: 'Scan Bluetooth', skill_id: 'ble_scan_room', params: { seconds: 8 } }],
      words: 'Bluetooth → ble_scan_room (scan only)' },
    { id: 'facts', test: /status|facts|état|info/i, source: 'any',
      make: d => [{ label: 'Device status', skill_id: 'device_facts', target: d, params: {} }],
      words: 'status → device_facts (read-only)' },
  ];
  TEMPLATES.push({ id: 'vacuum', test: /vacuum|aspirateur|robot/i, source: 'vacuum',
    make: v => [{ label: 'Start cleaning', skill_id: 'vacuum_command', target: v, params: { command: 'start' } },
      { label: 'Pause', skill_id: 'vacuum_command', target: v, params: { command: 'pause' } },
      { label: 'Back to dock', skill_id: 'vacuum_command', target: v, params: { command: 'dock' } }],
    words: 'robot vacuum → vacuum_command (start / pause / dock, one typed command per press)' });
  function pickTemplate(text) {
    const vac = TEMPLATES[4];
    if (vac.test.test(text)) return { t: vac, m: null };     // "…on my TV so I can operate my robot vacuum": the vacuum is the device controlled
    const exact = TEMPLATES[1].test.exec(text);
    if (exact) return { t: TEMPLATES[1], m: exact };
    for (const t of [TEMPLATES[0], TEMPLATES[2], TEMPLATES[3]]) if (t.test.test(text)) return { t, m: null };
    return null;
  }
  /* Destination named in the request ("on my TV", "sur ma montre"): prefer a paired Companion running on that kind of device. */
  const DEST_WORDS = [['tv', /\b(tv|t[ée]l[ée]|television)\b/i], ['watch', /\b(watch|montre)\b/i], ['phone', /\b(phone|t[ée]l[ée]phone|mobile)\b/i]];
  function preferRelay(text) {
    const byKey = Object.fromEntries(S.devices.map(d => [d.key, d]));
    for (const [cat, rx] of DEST_WORDS) {
      const m = text.match(new RegExp('\\b(on|sur)\\s+(my|ma|mon)\\s+' + rx.source.replace(/^\\b|\\b$/g, ''), 'i'));
      if (!m) continue;
      const r = S.relays.find(x => x.category === cat && x.online) || S.relays.find(x => x.category === cat);
      if (r) return r.relay_id;
    }
    return null;
  }

  // ---------- validation (mirrors the server; the server re-checks at install) ----------
  function validParams(schema, params) {
    if (!schema || schema.type !== 'object') return 'no input schema';
    const props = schema.properties || {};
    for (const r of schema.required || []) if (!(r in params)) return `missing ${r}`;
    for (const [k, v] of Object.entries(params)) {
      const p = props[k];
      if (!p) { if (schema.additionalProperties === false) return `unexpected ${k}`; continue; }
      if (p.enum && !p.enum.includes(v)) return `${k} must be one of ${p.enum.join(', ')}`;
      if (p.type === 'integer' && (!Number.isInteger(v) || (p.minimum !== undefined && v < p.minimum) || (p.maximum !== undefined && v > p.maximum))) return `${k} out of range`;
      if (p.type === 'string' && (typeof v !== 'string' || (p.maxLength && v.length > p.maxLength))) return `${k} invalid`;
    }
    return null;
  }
  function validate() {
    const c = [], p = S.proposal;
    const add = (ok, text) => c.push({ ok, text });
    if (!p) return [{ ok: false, text: 'No proposal' }];
    add(p.controls.length > 0 && p.controls.length <= 12, `${p.controls.length} control(s) — at most 12 per Companion`);
    for (const k of p.controls) {
      const sk = S.skills[k.skill_id];
      add(!!sk, `${k.label}: skill ${k.skill_id} ${sk ? 'exists in the catalog' : 'is unknown'}`);
      if (!sk) continue;
      add(typeof k.label === 'string' && k.label.length > 0 && k.label.length <= 40, `${k.label}: label is 1–40 characters`);
      add(!sk.targeted || !!k.target, `${k.label}: ${sk.targeted ? 'target device set' : 'no target needed'}`);
      const err = validParams(sk.input, k.params);
      add(!err, `${k.label}: parameters ${err ? '— ' + err : 'match the schema'}`);
    }
    add(!!S.relay || S.sim, S.relay || S.sim ? 'A paired Companion is selected as destination' : 'No paired Companion selected');
    add(true, `Intent ↔ effect: ${p.words}`);
    return c;
  }

  // ---------- data ----------
  async function discover() {
    S.busy = true; S.error = ''; paint();
    if (S.sim) {
      S.devices = [{ key: 'sim-tv', label: 'Living room TV (SIMULATED)', category: 'tv' }, { key: 'sim-vacuum', label: 'Robot vacuum (SIMULATED)', category: 'vacuum' }];
      S.relays = [{ relay_id: 'sim-watch', label: 'Watch (SIMULATED)', category: 'watch', online: true }, { relay_id: 'sim-tv-companion', label: 'TV Companion (SIMULATED)', category: 'tv', online: true }];
      S.skills = { tv_volume_step: { targeted: true, reversibility: 'IRREVERSIBLE', input: { type: 'object', properties: { direction: { type: 'string', enum: ['up', 'down'] } }, required: ['direction'], additionalProperties: false } },
        tv_volume_set: { targeted: true, reversibility: 'EXACT', input: { type: 'object', properties: { value: { type: 'integer', minimum: 0, maximum: 100 } }, required: ['value'], additionalProperties: false } },
        ble_scan_room: { targeted: false, reversibility: 'SESSION_CLEANUP', input: { type: 'object', properties: { seconds: { type: 'integer', minimum: 1, maximum: 15 } }, additionalProperties: false } },
        device_facts: { targeted: true, reversibility: 'NONE', input: { type: 'object', properties: {}, additionalProperties: false } },
        vacuum_command: { targeted: true, reversibility: 'IRREVERSIBLE', input: { type: 'object', properties: { command: { type: 'string', enum: ['start', 'pause', 'mode', 'dock', 'move', 'seek', 'empty_dust', 'reset_side_brush', 'reset_main_brush', 'reset_filter', 'water_level', 'work_mode'] }, value: { type: 'string', maxLength: 16 }, move_s: { type: 'number' } }, required: ['command'], additionalProperties: false } } };
    } else {
      try {
        const [fab, routes, skills] = await Promise.all([get('/api/fabric'), get('/api/v2/routes'), get('/api/v2/skills')]);
        S.devices = (fab.devices || []).filter(d => d.category !== 'ble');
        const byKey = Object.fromEntries(S.devices.map(d => [d.key, d]));
        S.relays = (routes.routes || []).map(r => ({ relay_id: r.relay_id, label: byKey[r.target_device] ? devLabel(byKey[r.target_device]) : r.relay_id, category: (byKey[r.target_device] || byKey[r.relay_device] || {}).category || '', online: !!r.online, status: r.status }));
        S.skills = Object.fromEntries((skills.skills || []).map(k => [k.skill_id, k]));
      } catch (e) { S.error = 'Discovery read failed: ' + e.message; }
    }
    const tv = S.devices.find(d => d.category === 'tv');
    if (!S.source || !S.devices.some(d => d.key === S.source)) S.source = tv ? tv.key : (S.devices[0] || {}).key || '';
    const named = preferRelay(S.text);
    if (named) S.relay = named;
    else if (!S.relay || !S.relays.some(r => r.relay_id === S.relay)) S.relay = (S.relays.find(r => r.online) || S.relays[0] || {}).relay_id || '';
    S.busy = false;
    S.step = Math.max(S.step, 1);
    propose();
  }
  function propose() {
    S.question = null; S.consent = false;
    const pick = pickTemplate(S.text);
    if (!pick) {
      S.proposal = null;
      S.question = 'Which action should the new control perform?';
      S.step = 2; paint(); return;
    }
    const { t, m } = pick;
    if (t.source && t.source !== 'any') {      // the template names the kind of device it controls
      const cur = S.devices.find(d => d.key === S.source);
      if (!cur || cur.category !== t.source) { const want = S.devices.find(d => d.category === t.source); S.source = want ? want.key : ''; }
    }
    const src = t.source === null ? null : S.source;
    if (t.source && t.source !== 'any' && !src) {
      S.proposal = null; S.question = `No ${t.source === 'tv' ? 'TV' : t.source} has been discovered yet. Discover it first (Devices → Discover), then come back.`;
      S.step = 2; paint(); return;
    }
    if (t.source && !src) { S.proposal = null; S.step = 1; paint(); return; }
    S.proposal = { template: t.id, words: t.words, controls: t.make(src, m) };
    S.checks = validate();
    S.step = S.checks.every(c => c.ok) ? 4 : 3;
    M() && M().signal('proposal_ready', { origin: S.sim ? 'simulated' : 'live', text: (S.sim ? 'SIM · ' : '') + 'Preview ready · nothing installed' });
    paint();
  }
  async function install() {
    if (!S.consent || S.busy) return;
    S.busy = true; S.error = ''; paint();
    const controls = S.proposal.controls.map(({ label, skill_id, target, params }) => (target ? { label, skill_id, target, params } : { label, skill_id, params }));
    if (S.sim) {
      const target = root.querySelector('.target-device');
      M() && M().signal('transport_outbound', { origin: 'simulated', label: 'set controls', bytes: JSON.stringify(controls).length, target, corr: 'sim-pub' });
      await new Promise(r => setTimeout(r, 900));
      M() && M().signal('transport_inbound', { origin: 'simulated', label: 'ack', bytes: 64, corr: 'sim-ack' });
      S.published = { controls: controls.map((c, i) => ({ control_id: 'sim-ctl-' + i, label: c.label, skill_id: c.skill_id })), at: new Date().toISOString() };
      M() && M().signal('companion_applied_revision', { text: 'SIM · interface shown on the simulated watch · no physical action' });
    } else {
      try {
        if (M()) M().hint = { path: '/api/v2/remote_controls', el: root.querySelector('.target-device'), until: performance.now() + 4000 };
        const st = await post('/api/v2/remote_controls', { relay_id: S.relay, controls, consent: true });
        S.published = { controls: (st.controls || []).filter(c => c.relay_id === S.relay), at: new Date().toISOString() };
        M() && M().signal('companion_applied_revision', { text: 'Companion acknowledged the controls · no physical action has run' });
      } catch (e) { S.error = 'Install refused: ' + e.message; S.busy = false; paint(); return; }
    }
    S.revoked = false; S.busy = false; S.step = 7; S.consent = false; paint();
  }
  async function runFromPc(c) {
    if (S.busy) return;
    if (!(await ask(`Run “${c.label}” once now? This sends one ${S.sim ? 'SIMULATED' : 'real'} ${c.skill_id} command to the device.`, { title: 'Run this control once', ok: 'Run once' }))) return;   // explicit, per run
    S.busy = true; paint();
    if (S.sim) {
      M() && M().signal('transport_outbound', { origin: 'simulated', label: c.label, bytes: 96, corr: 'sim-run' });
      await new Promise(r => setTimeout(r, 700));
      M() && M().signal('transport_inbound', { origin: 'simulated', label: 'receipt', bytes: 128, corr: 'sim-rc' });
      S.presses.unshift({ control_id: c.control_id, label: c.label, state: 'EXECUTED', reason: `${c.label}: done (SIMULATED · not verified)`, origin: 'simulated', at: new Date().toISOString() });
      M() && M().signal('outcome_uncertain', { origin: 'simulated', text: 'Sent · no read-back for a volume step' });
    } else {
      try {
        const e = await post('/api/v2/remote_controls/invoke', { relay_id: S.relay, control_id: c.control_id, consent: true });
        S.presses.unshift(Object.assign({ label: c.label }, e));
      } catch (err) { S.presses.unshift({ control_id: c.control_id, label: c.label, state: 'REFUSED', reason: err.message }); }
    }
    S.busy = false; S.step = Math.max(S.step, 8); paint();
  }
  async function revoke() {
    if (S.busy || !S.published) return;
    S.busy = true; paint();
    if (S.sim) { M() && M().signal('grant_revoked', { text: 'SIM · revoked · new presses are refused' }); }
    else {
      try { await post('/api/v2/remote_controls', { relay_id: S.relay, controls: [], consent: true }); M() && M().signal('grant_revoked'); }
      catch (e) { S.error = 'Revoke failed: ' + e.message + ' — the controls may still be active.'; S.busy = false; paint(); return; }
    }
    S.revoked = true; S.busy = false; S.step = 9; paint();
  }
  function onEvents(evs) {
    if (!S.published || S.sim) return;
    const ids = new Set(S.published.controls.map(c => c.control_id));
    let n = 0;
    for (const e of evs) if (e.kind === 'remote_request' && ids.has(e.control_id)) {
      const c = S.published.controls.find(x => x.control_id === e.control_id);
      S.presses.unshift(Object.assign({ label: c ? c.label : e.control_id }, e)); n++;
    }
    if (n) { S.step = Math.max(S.step, 8); paint(); }
  }

  // ---------- rendering ----------
  function stepState(i) {
    if (S.revoked && i === 9) return 'done';
    if (i < S.step) return 'done';
    if (i === S.step) return S.error || (i === 3 && S.checks.some(c => !c.ok)) || (i === 2 && S.question) ? 'blocked' : 'current';
    return 'pending';
  }
  function stepper() {
    const list = h('ol', { class: 'stepper', 'aria-label': 'Creation steps' }, ...STEPS.map(([k, q], i) => {
      const st = stepState(i);
      return h('li', { class: 'step ' + st, title: q, 'aria-current': st === 'current' || st === 'blocked' ? 'step' : null },
        h('span', { class: 'step-n', 'aria-hidden': 'true', text: st === 'done' ? '✓' : String(i + 1) }),
        h('strong', { text: k }), h('span', { class: 'sr-only', text: ` — ${q} — ${st}` }));
    }));
    const i = Math.min(S.step, STEPS.length - 1), [k, q, cond] = STEPS[i];
    const now = h('p', { class: 'step-now ' + stepState(i) }, h('strong', { text: `Step ${i + 1} · ${k}` }), ` — ${q} `, h('span', { class: 'muted', text: `Advances when: ${cond}.` }));
    return h('div', { class: 'stepper-wrap' }, list, now);
  }
  function requestPanel() {
    const ta = h('textarea', { id: 'studio-request', rows: '2', maxlength: '300', 'aria-label': 'What should the new capability do?' });
    ta.value = S.text;
    ta.addEventListener('input', () => { S.text = ta.value; });
    const go = h('button', { class: 'primary', type: 'button', disabled: S.busy, onclick: () => { S.text = ta.value.trim() || DEFAULT_REQUEST; S.step = 1; discover(); } }, S.step ? 'Update proposal' : 'Find devices & propose');
    return h('section', { class: 'panel studio-block' }, h('h2', { text: '1 · Request' }), ta,
      h('div', { class: 'row' }, go), h('p', { class: 'muted small', text: 'Examples: “TV volume on my watch”, “volume to 12 on my watch”, “Bluetooth scan button”.' }));
  }
  function devicesPanel() {
    if (S.step < 1) return null;
    const src = h('select', { id: 'studio-source', 'aria-label': 'Source device' }, ...S.devices.map(d => h('option', { value: d.key, text: `${devLabel(d)} · ${d.category}` })));
    src.value = S.source; src.addEventListener('change', () => { S.source = src.value; propose(); });
    const dst = h('select', { id: 'studio-target', 'aria-label': 'Destination Companion' }, ...S.relays.map(r => h('option', { value: r.relay_id, text: `${r.label} · ${r.online ? 'online' : 'offline'}` })));
    dst.value = S.relay; dst.addEventListener('change', () => { S.relay = dst.value; S.checks = validate(); paint(); });
    const box = h('section', { class: 'panel studio-block' }, h('h2', { text: '2 · Source → destination' }));
    if (S.busy && !S.devices.length) box.append(h('p', { class: 'muted', text: 'Reading the current discovery and paired Companions…' }));
    if (!S.devices.length && !S.busy) box.append(h('p', { class: 'warn', text: 'No device discovered yet.' }), h('a', { class: 'button ghost small', href: '#/devices' }, 'Discover devices'));
    else box.append(h('label', { class: 'field' }, 'Device to control', src));
    if (!S.relays.length && !S.busy) box.append(h('p', { class: 'warn', text: 'No paired Companion. Pair one first (Devices → a phone or watch → Use as relay), or rehearse without hardware.' }));
    else if (S.relays.length) box.append(h('label', { class: 'field' }, 'Show the controls on', dst));
    const r = S.relays.find(x => x.relay_id === S.relay);
    if (r && !r.online) box.append(h('p', { class: 'warn', text: 'This Companion is offline: installation would wait for it. Nothing is assumed installed.' }));
    return box;
  }
  function proposalPanel() {
    if (S.step < 2) return null;
    const box = h('section', { class: 'panel studio-block' }, h('h2', { text: '3 · Proposal & checks' }));
    if (S.question) {
      box.append(h('p', {}, h('strong', { text: 'Needs clarification: ' }), S.question));
      const opts = [['Volume up / down', 'TV volume on my watch'], ['Set an exact volume', 'TV volume to 10'], ['Robot vacuum', 'Robot vacuum controls on my TV'], ['Bluetooth scan', 'Bluetooth scan button'], ['Device status (read-only)', 'device status']];
      if (S.question.startsWith('Which')) box.append(h('div', { class: 'row wrap' }, ...opts.map(([t, q]) => h('button', { class: 'ghost small', type: 'button', onclick: () => { S.text = q; propose(); } }, t))));
      return box;
    }
    if (!S.proposal) { box.append(h('p', { class: 'muted', text: 'Choose a device to control to get a proposal.' })); return box; }
    box.append(h('p', { class: 'small muted', text: `Proposed by the OpenBridge typed template (${S.proposal.template}) — deterministic, from the skill catalog. Meta suggestions in Ask follow the same validation.` }));
    box.append(h('ul', { class: 'checks' }, ...S.checks.map(c => h('li', { class: c.ok ? 'ok' : 'bad' }, h('span', { 'aria-hidden': 'true', text: c.ok ? '✓ ' : '✗ ' }), h('span', { class: 'sr-only', text: c.ok ? 'Pass: ' : 'Fail: ' }), c.text))));
    if (S.checks.some(c => !c.ok)) box.append(h('p', { class: 'bad', text: 'Blocked: fix the failing check. Nothing can be installed.' }));
    return box;
  }
  function consentPanel() {
    if (S.step < 4 || !S.proposal || S.checks.some(c => !c.ok)) return null;
    const box = h('section', { class: 'panel studio-block consent-block' }, h('h2', { text: '4 · Review & approve' }));
    const r = S.relays.find(x => x.relay_id === S.relay), d = S.devices.find(x => x.key === S.source);
    const eff = h('ul', { class: 'effects' }, ...S.proposal.controls.map(c => {
      const sk = S.skills[c.skill_id] || {};
      return h('li', {}, h('strong', { text: c.label }), ` → each press asks this PC to run `, h('code', { text: `${c.skill_id} ${JSON.stringify(c.params)}` }), c.target ? ` on ${d ? devLabel(d) : c.target}` : '', ` once · reversibility: ${sk.reversibility || '?'}`);
    }));
    box.append(h('p', { text: `Install ${S.proposal.controls.length} control(s) on ${r ? r.label : 'the Companion'}.` }), eff,
      h('p', { class: 'small muted', text: 'A physical press on the paired device stands for consent to exactly one run. Revoking stops new runs; an already admitted run may finish. Volume steps cannot be undone.' }));
    if (S.published && !S.revoked) return box.append(h('p', { class: 'ok', text: 'Approved and installed. Edit the request to propose a new version (it needs a new approval).' })), box;
    const cb = h('input', { type: 'checkbox', id: 'studio-consent' }); cb.checked = S.consent;
    cb.addEventListener('change', () => { S.consent = cb.checked; S.step = cb.checked ? 5 : 4; paint(); });
    const blocked = !S.sim && !S.relay;
    box.append(h('label', { class: 'transaction-consent', for: 'studio-consent' }, cb, ' I approve installing exactly these controls.'),
      h('button', { class: 'primary', type: 'button', id: 'studio-install', disabled: !S.consent || S.busy || blocked, onclick: install }, S.busy ? 'Installing…' : 'Approve & install'),
      ...(blocked ? [h('p', { class: 'warn small', text: 'Installation needs a paired Companion.' })] : []));
    return box;
  }
  function resultPanel() {
    if (!S.published) return null;
    const box = h('section', { class: 'panel studio-block' }, h('h2', { text: '5 · Use, verify, revoke' }));
    box.append(h('p', { class: S.revoked ? 'muted' : 'ok', text: S.revoked ? 'Revoked. New presses are refused by this PC.' : `Installed ${S.published.controls.length} control(s) · Companion acknowledged at ${S.published.at.slice(11, 19)}. This is not a physical effect yet.` }));
    if (!S.revoked) box.append(h('div', { class: 'row wrap' }, ...S.published.controls.map(c => h('button', { class: 'ghost small', type: 'button', disabled: S.busy, onclick: () => runFromPc(c) }, `Run “${c.label}” from this PC`))));
    box.append(h('h3', { text: 'Presses and receipts' }));
    if (!S.presses.length) box.append(h('p', { class: 'muted', text: S.sim ? 'No simulated run yet.' : 'Waiting for a press on the device. Presses appear here with the outcome the PC recorded.' }));
    else box.append(h('ol', { class: 'timeline compact' }, ...S.presses.slice(0, 8).map(p => {
      const v = p.state === 'VERIFIED', bad = ['REVOKED', 'EXPIRED', 'BLOCKED', 'SUSPENDED', 'FAILED', 'REFUSED'].includes(p.state);
      const word = v ? 'Verified by read-back' : p.state === 'EXECUTED' ? 'Sent · effect not verified' : p.state === 'UNCERTAIN' ? 'Result not confirmed · not retried' : bad ? 'Refused' : p.state;
      return h('li', { class: 'tl ' + (v ? 'ok' : bad ? 'bad' : 'warn') }, h('span', { class: 'tl-dot', 'aria-hidden': 'true' }), h('div', {}, h('strong', { text: `${p.label}: ${word}` }), h('small', { text: `${p.reason || ''}${p.origin === 'simulated' ? ' · SIMULATED' : ''}${p.transaction_id ? ' · ' + p.transaction_id : ''}` })));
    })));
    if (!S.revoked) box.append(h('button', { class: 'secondary', type: 'button', id: 'studio-revoke', disabled: S.busy, onclick: revoke }, 'Revoke these controls'));
    return box;
  }
  function targetPreview() {
    const r = S.relays.find(x => x.relay_id === S.relay);
    const installed = S.published && !S.revoked;
    const controls = installed ? S.published.controls : S.proposal ? S.proposal.controls : [];
    const face = h('div', { class: 'watch-face' + (installed ? ' installed' : '') }, ...controls.map((c, i) => {
      const b = h('span', { class: 'watch-btn', role: 'img', 'aria-label': `${c.label} (${installed ? 'installed' : 'preview'})` }, c.label);
      if (!installed && S.proposal && !S.published) {
        const up = h('button', { class: 'icon-btn tiny', type: 'button', 'aria-label': `Move ${c.label} up`, disabled: i === 0, onclick: () => { const a = S.proposal.controls; [a[i - 1], a[i]] = [a[i], a[i - 1]]; paint(); } }, '↑');
        const ren = h('button', { class: 'icon-btn tiny', type: 'button', 'aria-label': `Rename ${c.label}`, onclick: async () => { const v = await ask('Label shown on the device (1–40 characters). The action does not change.', { title: 'Rename control', input: c.label, ok: 'Rename' }); if (v && v.trim()) { c.label = v.trim().slice(0, 40); S.consent = false; S.checks = validate(); S.step = Math.min(S.step, 4); paint(); } } }, '✎');
        return h('span', { class: 'watch-row' }, b, up, ren);
      }
      return b;
    }));
    if (!controls.length) face.append(h('span', { class: 'muted small', text: 'No controls yet' }));
    const badge = S.revoked ? h('p', { class: 'tag', text: 'REVOKED · drawn controls no longer run' }) : installed ? h('p', { class: 'tag ok', text: S.sim ? 'SIMULATED · installed on a simulated watch' : 'INSTALLED · acknowledged by the Companion' }) : h('p', { class: 'tag warn', text: 'PREVIEW ONLY — nothing installed' });
    return h('section', { class: 'panel target-panel', 'aria-label': 'Destination preview' }, h('h2', { text: 'Destination' }), h('p', { class: 'muted small', text: r ? r.label : S.sim ? 'Watch (SIMULATED)' : 'No Companion selected' }),
      h('div', { class: 'target-device ' + ((r && r.category) || (S.sim && S.relay === 'sim-tv-companion' ? 'tv' : 'watch')) }, face), badge);
  }
  function paint() {
    if (!root) return;
    const focusId = document.activeElement && document.activeElement.id;
    const stage = h('aside', { class: 'orb-stage studio-orb', id: 'studio-orb', 'aria-label': 'OpenBridge activity' },
      h('div', { class: 'orb-canvas-host' }),
      h('div', { class: 'orb-status', 'data-orb-status': '' }, h('strong', { class: 'orb-state' }), h('span', { class: 'orb-note' })),
      h('p', { class: 'orb-legend' }, h('span', { class: 'lg-out', text: '↑ sent' }), h('span', { class: 'flow-counts', 'data-flow-counts': '' }), h('span', { class: 'lg-in', text: '↓ received' })),
      h('p', { class: 'muted small', text: 'Comets show real messages only. A comet is never proof of a physical effect.' }));
    const banner = S.sim ? h('p', { class: 'mode-banner sim', role: 'status' }, h('strong', { text: 'SIMULATED REHEARSAL' }), ' No request reaches the runtime or a device. Nothing is written to Activity.') : null;
    const modeBtn = h('button', { class: 'ghost small', type: 'button', onclick: () => { Object.assign(S, { sim: !S.sim, step: 0, proposal: null, published: null, presses: [], revoked: false, consent: false, error: '', question: null, source: '', relay: '' }); paint(); } }, S.sim ? 'Leave rehearsal' : 'Rehearse without hardware (SIMULATED)');
    root.replaceChildren(...[
      h('div', { class: 'studio-top' }, stepper(), modeBtn),
      banner,
      S.error ? h('p', { class: 'mode-banner bad', role: 'alert', text: S.error }) : null,
      h('div', { class: 'studio-grid' },
        h('div', { class: 'studio-col' }, requestPanel(), devicesPanel(), proposalPanel(), consentPanel(), resultPanel()),
        stage, targetPreview())].filter(Boolean));
    if (M()) M().mount(stage, { sector: [-Math.PI, Math.PI] });
    if (focusId) { const f = document.getElementById(focusId); if (f) f.focus({ preventScroll: true }); }
  }

  function render(arg) {
    root = document.getElementById('studio-root');
    if (arg) S.text = decodeURIComponent(arg);
    paint();
  }
  global.OBViews = global.OBViews || {};
  global.OBViews.studio = { render, onEvents, _state: S };
})(window);
