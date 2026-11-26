'use strict';
/* Custom controls (UI V2): build your own buttons for each paired screen (TV, watch, phone),
   keep several profiles per screen and switch between them.

   Data: screens from GET /api/v2/routes + /api/fabric, actions from GET /api/v2/skills,
   profiles from GET /api/v2/control_profiles. Every edit is saved at once with
   POST /api/v2/control_profiles/save (nothing is installed by saving). "Send to …" asks for
   confirmation, then POST /api/v2/control_profiles/apply {consent: true}; the server re-checks every
   button and installs through the same owner path as the Studio. The view never runs an action itself.

   Demo mode (no paired screen needed): same editor on a simulated watch, kept in memory only,
   labelled SIMULATED, nothing reaches the runtime. */
(function (global) {
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
  const svgNS = 'http://www.w3.org/2000/svg';
  function icon(name) { const sv = document.createElementNS(svgNS, 'svg'); sv.setAttribute('aria-hidden', 'true'); sv.setAttribute('class', 'ic'); const u = document.createElementNS(svgNS, 'use'); u.setAttribute('href', '#i-' + name); sv.append(u); return sv; }
  const get = path => request(path);                       // eslint-disable-line no-undef
  const post = (path, body) => postJson(path, body);        // eslint-disable-line no-undef
  const devName = d => (typeof displayLabel === 'function' ? displayLabel(d) : d.label) || d.label || d.key;   // eslint-disable-line no-undef

  const ANDROID = ['tv', 'phone', 'watch', 'android', 'tablet'];
  const CAT_ICON = { tv: 'tv', phone: 'phone', watch: 'watch', android: 'phone', tablet: 'phone', vacuum: 'vacuum', computer: 'pc', pc: 'pc', router: 'router', this_pc: 'pc' };
  const SCREEN_WORD = { tv: 'TV', watch: 'watch', phone: 'phone', tablet: 'tablet' };
  const APPS = [['com.google.android.youtube.tv', 'YouTube (TV)'], ['com.google.android.youtube', 'YouTube (phone)'], ['com.netflix.ninja', 'Netflix (TV)'], ['com.spotify.tv.android', 'Spotify (TV)'], ['com.spotify.music', 'Spotify (phone)']];
  /* Plain-language catalog over the typed skills. Anything the server offers that is not listed here
     still appears under "More actions" with fields built from its schema. */
  const ACTIONS = [
    { id: 'tv_volume_step', name: 'Volume up or down', group: 'Sound', for: ANDROID,
      fields: { direction: { label: 'Direction', options: [['up', 'Louder'], ['down', 'Quieter']], def: 'up' } },
      suggest: p => (p.direction === 'down' ? 'Volume −' : 'Volume +'), say: p => (p.direction === 'down' ? 'Turn the volume down' : 'Turn the volume up') },
    { id: 'tv_volume_set', name: 'Set the volume to a level', group: 'Sound', for: ANDROID,
      fields: { value: { label: 'Volume level', range: [0, 100], def: 15 } }, suggest: p => `Volume ${p.value}`, say: p => `Set the volume to ${p.value}` },
    { id: 'tv_wake', name: 'Turn the screen on', group: 'Screen', for: ['tv'], suggest: () => 'Screen on' },
    { id: 'tv_sleep', name: 'Turn the screen off', group: 'Screen', for: ['tv'], suggest: () => 'Screen off' },
    { id: 'app_launch', name: 'Open an app', group: 'Apps', for: ANDROID,
      fields: { package: { label: 'App', app: true, def: APPS[0][0] } },
      suggest: p => { const a = APPS.find(x => x[0] === p.package); return a ? a[1].replace(/ \(.*\)$/, '') : 'Open app'; },
      say: p => { const a = APPS.find(x => x[0] === p.package); return 'Open ' + (a ? a[1] : p.package || 'an app'); } },
    { id: 'companion_foreground', name: 'Show OpenBridge on this screen', group: 'Screen', for: ANDROID, suggest: () => 'OpenBridge' },
    { id: 'screen_capture', name: 'Take a screenshot', group: 'Screen', for: ANDROID, suggest: () => 'Screenshot' },
    { id: 'vacuum_command', name: 'Send a cleaning command', group: 'Cleaning', for: ['vacuum'],
      fields: { command: { label: 'What should it do?', options: [['start', 'Start cleaning'], ['pause', 'Pause'], ['dock', 'Go back to the dock'], ['seek', 'Find the robot (it beeps)'], ['empty_dust', 'Empty the dustbin']], def: 'start' } },
      suggest: p => ({ start: 'Start cleaning', pause: 'Pause', dock: 'Back to dock', seek: 'Find robot', empty_dust: 'Empty bin' }[p.command] || 'Vacuum'),
      say: p => ({ start: 'Start cleaning', pause: 'Pause cleaning', dock: 'Go back to the dock', seek: 'Beep so you can find it', empty_dust: 'Empty the dustbin' }[p.command] || 'Cleaning command') },
    { id: 'device_facts', name: 'Show the device status', group: 'Info', for: '*', suggest: () => 'Status' },
    { id: 'pc_open_url', name: 'Open a web page', group: 'Computer', for: ['computer', 'pc'],
      fields: { url: { label: 'Web address', text: true, placeholder: 'https://', def: 'https://' } }, suggest: () => 'Open page' },
    { id: 'retro_command', name: 'RetroArch on this PC', group: 'Games', for: ['this_pc'],
      fields: { command: { label: 'Command', options: [['PAUSE_TOGGLE', 'Pause / resume'], ['VOLUME_UP', 'Volume up'], ['VOLUME_DOWN', 'Volume down']], def: 'PAUSE_TOGGLE' } },
      suggest: p => ({ PAUSE_TOGGLE: 'Pause game', VOLUME_UP: 'Game vol +', VOLUME_DOWN: 'Game vol −' }[p.command]) },
    { id: 'ble_scan_room', name: 'Look for Bluetooth devices nearby', group: 'Info', for: ['this_pc'],
      fields: { seconds: { label: 'Scan time (seconds)', range: [1, 15], def: 8 } }, suggest: () => 'Bluetooth scan' },
  ];
  const HIDDEN = new Set(['pc_run', 'capture_send', 'capture_montage', 'file_pull', 'file_push', 'view_image', 'pc_place_file', 'pc_wallpaper', 'capability_probe']);
  const THIS_PC = { key: '__this_pc__', label: 'This PC (OpenBridge)', category: 'this_pc' };
  const TEMPLATES = [
    { id: 'tv', name: 'TV remote', needs: 'tv', make: tv => [['Volume +', 'tv_volume_step', { direction: 'up' }], ['Volume −', 'tv_volume_step', { direction: 'down' }], ['Screen off', 'tv_sleep', {}], ['YouTube', 'app_launch', { package: 'com.google.android.youtube.tv' }]].map(([label, skill_id, params]) => ({ label, skill_id, device: tv.label, device_key: tv.key, params })) },
    { id: 'vacuum', name: 'Robot vacuum', needs: 'vacuum', make: v => [['Start cleaning', 'start'], ['Pause', 'pause'], ['Back to dock', 'dock'], ['Find robot', 'seek']].map(([label, command]) => ({ label, skill_id: 'vacuum_command', device: v.label, device_key: v.key, params: { command } })) },
  ];

  const C = {
    loading: false, error: '', demo: false, screens: [], devices: [], skills: {}, data: { max_buttons: 12 }, sdata: new Map(),
    screen: '', profile: '', saving: 0, savedAt: 0, dragFrom: null,
  };
  let root, ctx = {};

  // ---------- data ----------
  function actionOf(id) { return ACTIONS.find(a => a.id === id) || null; }
  function actionsAvailable() {
    const known = ACTIONS.filter(a => C.skills[a.id]);
    const extra = Object.values(C.skills).filter(s => !HIDDEN.has(s.skill_id) && !actionOf(s.skill_id))
      .map(s => ({ id: s.skill_id, name: s.plain || s.skill_id, group: 'More actions', for: s.targeted ? '*' : ['this_pc'], generic: true, schema: s.input }));
    return known.concat(extra);
  }
  function needsDevice(skillId) { const s = C.skills[skillId]; return s ? !!s.targeted : true; }
  function screenOf(id) { return C.screens.find(s => s.relay_id === id); }
  /* Screen ids come from the server and the URL: keep them in a Map, never as object keys. */
  function screenData(id) { return C.sdata.get(id) || { profiles: [], live: [], active: null, applied: null }; }
  function ensureScreen(id) { if (!C.sdata.has(id)) C.sdata.set(id, { profiles: [], live: [], active: null, applied: null }); return C.sdata.get(id); }
  function setScreens(obj) { C.sdata = new Map(Object.entries(obj || {}).filter(([, v]) => v && typeof v === 'object')); }
  function profileOf() { return screenData(C.screen).profiles.find(p => p.id === C.profile) || null; }
  function word(scr) { return (scr && SCREEN_WORD[scr.category]) || 'screen'; }

  async function load() {
    C.loading = true; C.error = ''; paint();
    if (C.demo) { C.loading = false; pickDefaults(); paint(); return; }
    try {
      const [fab, routes, skills, prof] = await Promise.all([get('/api/fabric').catch(() => ({ devices: [] })), get('/api/v2/routes'), get('/api/v2/skills'), get('/api/v2/control_profiles')]);
      C.devices = (fab.devices || []).filter(d => d.category !== 'ble');
      const byKey = Object.fromEntries(C.devices.map(d => [d.key, d]));
      const seen = new Set();
      C.screens = (routes.routes || []).filter(r => r.relay_id && !seen.has(r.relay_id) && seen.add(r.relay_id)).map(r => {
        const d = byKey[r.target_device] || byKey[r.relay_device] || {};
        return { relay_id: r.relay_id, label: d.key ? devName(d) : r.relay_id, category: d.category || '', online: !!r.online };
      });
      for (const rid of Object.keys(prof.screens || {})) if (!seen.has(rid)) C.screens.push({ relay_id: rid, label: rid, category: '', online: false, unpaired: true });
      C.skills = Object.fromEntries((skills.skills || []).filter(k => (prof.bindable_skills || []).includes(k.skill_id)).map(k => [k.skill_id, k]));
      C.data = { max_buttons: prof.max_buttons || 12, max_profiles: prof.max_profiles || 16 };
      setScreens(prof.screens);
      C.modules = await get('/api/v2/companion_modules').catch(() => null);
    } catch (e) { C.error = 'Could not load your controls: ' + e.message; }
    C.loading = false; pickDefaults(); paint();
  }
  function pickDefaults() {
    if (!C.screens.some(s => s.relay_id === C.screen)) C.screen = (C.screens.find(s => s.online) || C.screens[0] || {}).relay_id || '';
    const sd = screenData(C.screen);
    if (!sd.profiles.some(p => p.id === C.profile)) C.profile = sd.active && sd.profiles.some(p => p.id === sd.active) ? sd.active : (sd.profiles[0] || {}).id || '';
  }
  function startDemo() {
    C.demo = true;
    C.devices = [{ key: 'demo-tv', label: 'Living room TV', category: 'tv' }, { key: 'demo-vac', label: 'Robot vacuum', category: 'vacuum' }];
    C.screens = [{ relay_id: 'demo-watch', label: 'Galaxy Watch', category: 'watch', online: true }, { relay_id: 'demo-tvc', label: 'Living room TV', category: 'tv', online: true }];
    C.skills = Object.fromEntries(['tv_volume_step', 'tv_volume_set', 'tv_wake', 'tv_sleep', 'app_launch', 'vacuum_command', 'device_facts'].map(id => [id, { skill_id: id, targeted: true }]));
    const p = { id: 'demo-1', name: 'Movie night', buttons: TEMPLATES[0].make(C.devices[0]).slice(0, 3) };
    C.data = { max_buttons: 12 };
    setScreens({ 'demo-watch': { profiles: [p], live: [], active: null, applied: null } });
    C.screen = 'demo-watch'; C.profile = 'demo-1';
    paint();
  }
  function leaveDemo() { C.demo = false; C.screen = ''; C.profile = ''; load(); }

  // ---------- saving ----------
  function digestOf(buttons) { return JSON.stringify(buttons.map(b => [b.label, b.skill_id, b.device || null, b.params || {}])); }
  let saveTimer = null;
  function queueSave() {
    const p = profileOf(); if (!p) return;
    p._dirty = true; C.saving = 1; paintStatus();
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveNow(p), 350);
  }
  async function saveNow(p) {
    if (C.demo) { p._dirty = false; C.saving = 0; C.savedAt = Date.now(); paintStatus(); return; }
    try {
      const r = await post('/api/v2/control_profiles/save', { relay_id: C.screen, profile_id: p.id, name: p.name, buttons: p.buttons.map(clean) });
      Object.assign(p, r.profile, { _dirty: false }); C.saving = 0; C.savedAt = Date.now(); C.error = '';
    } catch (e) { C.saving = 0; C.error = 'Not saved: ' + e.message; paint(); return; }
    paintStatus();
  }
  function clean(b) { return { label: b.label, skill_id: b.skill_id, device: b.device || null, device_key: b.device_key || null, params: b.params || {} }; }

  async function newProfile(seed, name) {
    const sd = screenData(C.screen);
    const max = C.data.max_profiles || 16;
    if (sd.profiles.length >= max) { flash(`A screen keeps at most ${max} profiles. Delete one first.`, 'bad'); return; }
    if (!name) {
      let n = sd.profiles.length + 1, base = 'Profile ';
      while (sd.profiles.some(p => p.name.toLowerCase() === (base + n).toLowerCase())) n++;
      name = await ask('Give this profile a name you will recognise, like "Movie night" or "Cleaning".', { title: 'New profile', input: base + n, ok: 'Create' });
      if (!name || !name.trim()) return;
    }
    const buttons = (seed || []).map(clean);
    if (C.demo) {
      const p = { id: 'demo-' + Math.random().toString(16).slice(2, 8), name: name.trim(), buttons };
      ensureScreen(C.screen).profiles.push(p);
      C.profile = p.id; paint(); return;
    }
    try {
      const r = await post('/api/v2/control_profiles/save', { relay_id: C.screen, name: name.trim(), buttons });
      const s = ensureScreen(C.screen);
      s.profiles.push(r.profile); C.profile = r.profile.id; C.error = '';
    } catch (e) { C.error = e.message; }
    paint();
  }
  async function renameProfile() {
    const p = profileOf(); if (!p) return;
    const v = await ask('New name for this profile.', { title: 'Rename profile', input: p.name, ok: 'Rename' });
    if (!v || !v.trim() || v.trim() === p.name) return;
    const old = p.name; p.name = v.trim(); paint();
    if (C.demo) return;
    try { const r = await post('/api/v2/control_profiles/save', { relay_id: C.screen, profile_id: p.id, name: p.name, buttons: p.buttons.map(clean) }); Object.assign(p, r.profile); }
    catch (e) { p.name = old; C.error = e.message; }
    paint();
  }
  async function duplicateProfile() {
    const p = profileOf(); if (!p) return;
    await newProfile(p.buttons, await ask('Name of the copy.', { title: 'Duplicate profile', input: p.name + ' (copy)', ok: 'Duplicate' }));
  }
  async function deleteProfile() {
    const p = profileOf(); if (!p) return;
    const ok = await ask(`Delete "${p.name}"? Buttons already on the ${word(screenOf(C.screen))} stay there until you send another profile or remove them.`, { title: 'Delete profile', ok: 'Delete', danger: true });
    if (!ok) return;
    const s = ensureScreen(C.screen);
    if (!C.demo) { try { await post('/api/v2/control_profiles/delete', { relay_id: C.screen, profile_id: p.id }); } catch (e) { C.error = e.message; paint(); return; } }
    s.profiles = s.profiles.filter(x => x.id !== p.id);
    if (s.active === p.id) s.active = null;
    C.profile = (s.profiles[0] || {}).id || ''; paint();
  }

  // ---------- send / clear ----------
  function describe(b) {
    const a = actionOf(b.skill_id);
    const what = a ? a.name : (C.skills[b.skill_id] || {}).plain || b.skill_id;
    if (a && a.say) return { what: a.say(b.params || {}), on: needsDevice(b.skill_id) ? (b.device || 'device') : 'this PC' };
    const opt = a && a.fields ? Object.entries(a.fields).map(([k, f]) => { const v = (b.params || {})[k]; if (v === undefined) return null; if (f.options) { const o = f.options.find(x => x[0] === v); return o ? o[1] : v; } if (f.app) { const o = APPS.find(x => x[0] === v); return o ? o[1] : v; } return String(v); }).filter(Boolean).join(', ') : '';
    return { what: opt ? `${what}: ${opt}` : what, on: needsDevice(b.skill_id) ? (b.device || 'device') : 'this PC' };
  }
  async function send() {
    const p = profileOf(), scr = screenOf(C.screen); if (!p) return;
    if (p._dirty) await saveNow(p);
    const list = h('ul', { class: 'cx-confirm-list' }, p.buttons.map(b => { const d = describe(b); return h('li', {}, h('strong', { text: b.label }), h('span', { text: `${d.what} · ${d.on}` })); }));
    const ok = await ask(p.buttons.length ? `These ${p.buttons.length} button${p.buttons.length > 1 ? 's' : ''} will appear on ${scr ? scr.label : 'the screen'}. Each press runs its action once. You can change or remove them at any time.` : `This removes every button from ${scr ? scr.label : 'the screen'}.`, { title: `Send "${p.name}" to the ${word(scr)}?`, ok: 'Send', body: p.buttons.length ? list : null });
    if (!ok) return;
    if (C.demo) { const s = ensureScreen(C.screen); s.active = p.id; s.applied = { profile_id: p.id, digest: digestOf(p.buttons) }; s.live = p.buttons.map(b => ({ label: b.label, editable: true })); flash('Sent to the simulated watch (SIMULATED).', 'ok'); paint(); return; }
    C.busy = true; paint();
    try {
      await post('/api/v2/control_profiles/apply', { relay_id: C.screen, profile_id: p.id, consent: true });
      flash(`"${p.name}" is on the ${word(scr)}.`, 'ok');
      await load();
    } catch (e) { C.error = e.message; C.busy = false; paint(); }
    C.busy = false;
  }
  async function clearScreen() {
    const scr = screenOf(C.screen);
    const ok = await ask(`Remove every button from ${scr ? scr.label : 'this screen'}? Your saved profiles are kept.`, { title: 'Remove buttons from the screen', ok: 'Remove', danger: true });
    if (!ok) return;
    if (C.demo) { const s = ensureScreen(C.screen); s.live = []; s.active = null; s.applied = null; paint(); return; }
    try { await post('/api/v2/control_profiles/clear', { relay_id: C.screen, consent: true }); flash('Buttons removed.', 'ok'); await load(); }
    catch (e) { C.error = e.message; paint(); }
  }
  async function capture() {
    const name = await ask('Name for the new profile. You can edit every button afterwards.', { title: 'Copy what is on the screen', input: 'On screen now', ok: 'Copy' });
    if (!name || !name.trim()) return;
    try {
      const r = await post('/api/v2/control_profiles/capture', { relay_id: C.screen, name: name.trim() });
      await load(); C.profile = r.profile.id;
      if (r.skipped) flash(`${r.skipped} button(s) from an approved plan could not be copied.`, '');
      paint();
    } catch (e) { C.error = e.message; paint(); }
  }

  // ---------- dialogs ----------
  function ask(message, opts) {
    opts = opts || {};
    return new Promise(resolve => {
      const back = document.activeElement;
      const dlg = h('dialog', { class: 'modal cx-modal', 'aria-label': opts.title || 'Confirm' });
      const input = opts.input !== undefined ? h('input', { maxlength: '40', 'aria-label': opts.title || 'Name', class: 'cx-input' }) : null;
      if (input) input.value = opts.input;
      const done = v => { dlg.close(); dlg.remove(); if (back && back.focus) back.focus(); resolve(v); };
      const ok = h('button', { class: opts.danger ? 'danger' : 'primary', type: 'button', onclick: () => done(input ? input.value : true) }, opts.ok || 'OK');
      dlg.append(...[h('h2', { text: opts.title || 'Confirm' }), h('p', { class: 'muted', text: message }), opts.body, input,
        h('div', { class: 'cx-modal-actions' }, h('button', { class: 'ghost', type: 'button', onclick: () => done(input ? null : false) }, 'Cancel'), ok)].filter(Boolean));
      dlg.addEventListener('cancel', e => { e.preventDefault(); done(input ? null : false); });
      if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') done(input.value); });
      document.body.append(dlg); dlg.showModal(); if (input) { input.focus(); input.select(); } else ok.focus();
    });
  }
  function flash(text, cls) {
    const box = document.getElementById('toasts'); if (!box) return;
    const t = h('div', { class: 'toast ' + (cls || ''), role: 'status', text }); box.append(t); setTimeout(() => t.remove(), 4200);
  }

  /* Button editor: device → action → options → text. Returns the button or null. */
  function editButton(initial) {
    return new Promise(resolve => {
      const back = document.activeElement;
      const b = initial ? JSON.parse(JSON.stringify(initial)) : { label: '', skill_id: '', device: null, device_key: null, params: {} };
      let labelTouched = !!(initial && initial.label);
      const devices = [THIS_PC].concat(C.devices);
      let dev = b.skill_id && !needsDevice(b.skill_id) ? THIS_PC : (devices.find(d => d.key === b.device_key) || devices.find(d => devName(d) === b.device || d.label === b.device) || null);
      if (!dev && b.device) dev = { key: b.device_key || '', label: b.device, category: '' };
      const dlg = h('dialog', { class: 'modal cx-modal cx-editor', 'aria-label': initial ? 'Edit button' : 'Add a button' });
      const body = h('div', { class: 'cx-editor-body' });
      const err = h('p', { class: 'cx-error', role: 'alert' });
      const done = v => { dlg.close(); dlg.remove(); if (back && back.focus) back.focus(); resolve(v); };
      const fits = (a, d) => (a.for === '*' ? d.category !== 'this_pc' : a.for.includes(d.category) || (!d.category && !a.for.includes('this_pc')));
      function setAction(a) {
        b.skill_id = a.id; b.params = {};
        for (const [k, f] of Object.entries(a.fields || {})) if (f.def !== undefined) b.params[k] = f.def;
        if (a.generic) for (const [k, p] of Object.entries((a.schema || {}).properties || {})) if ((a.schema.required || []).includes(k)) b.params[k] = p.enum ? p.enum[0] : p.type === 'integer' || p.type === 'number' ? (p.minimum || 0) : '';
        suggest(); draw();
      }
      function suggest() { const a = actionOf(b.skill_id); if (!labelTouched && a && a.suggest) b.label = (a.suggest(b.params) || '').slice(0, 40); }
      function fieldRow(k, f, schemaProp) {
        const id = 'cx-f-' + k, v = b.params[k];
        const set = val => { b.params[k] = val; suggest(); const li = dlg.querySelector('#cx-label'); if (li && !labelTouched) li.value = b.label; drawPreview(); };
        if (f.options || (schemaProp && schemaProp.enum)) {
          const opts = f.options || schemaProp.enum.map(x => [x, x]);
          return h('fieldset', { class: 'cx-field' }, h('legend', { text: f.label || k }), h('div', { class: 'cx-choices' }, opts.map(([val, text]) => h('label', { class: 'cx-choice' + (v === val ? ' on' : '') },
            h('input', { type: 'radio', name: id, value: val, checked: v === val, onchange: () => { set(val); draw(); } }), h('span', { text })))));
        }
        if (f.range || (schemaProp && (schemaProp.type === 'integer' || schemaProp.type === 'number'))) {
          const [min, max] = f.range || [schemaProp.minimum ?? 0, schemaProp.maximum ?? 100];
          const out = h('output', { for: id, text: v ?? min });
          return h('div', { class: 'cx-field' }, h('label', { for: id, text: f.label || k }), h('div', { class: 'cx-range' },
            h('input', { id, type: 'range', min, max, step: 1, value: v ?? min, oninput: e => { out.textContent = e.target.value; set(+e.target.value); } }), out));
        }
        if (f.app) {
          const known = APPS.some(a => a[0] === v);
          const custom = h('input', { id: id + '-pkg', class: 'cx-input', placeholder: 'App package, e.g. com.example.app', value: known ? '' : (v || ''), hidden: known, oninput: e => set(e.target.value.trim()) });
          return h('div', { class: 'cx-field' }, h('label', { for: id, text: f.label }), h('select', { id, class: 'cx-input', onchange: e => { if (e.target.value === '__other') { custom.hidden = false; custom.focus(); set(custom.value.trim()); } else { custom.hidden = true; set(e.target.value); } } },
            APPS.map(([pkg, name]) => h('option', { value: pkg, selected: v === pkg, text: name })), h('option', { value: '__other', selected: !known, text: 'Another app…' })), custom);
        }
        return h('div', { class: 'cx-field' }, h('label', { for: id, text: f.label || k }), h('input', { id, class: 'cx-input', value: v ?? '', placeholder: f.placeholder || '', maxlength: (schemaProp && schemaProp.maxLength) || 300, oninput: e => set(e.target.value) }));
      }
      const previewBtn = h('span', { class: 'cx-pill' });
      function drawPreview() { previewBtn.textContent = b.label || 'Button'; }
      function draw() {
        const actions = dev ? actionsAvailable().filter(a => fits(a, dev)) : [];
        const a = actionOf(b.skill_id) || actionsAvailable().find(x => x.id === b.skill_id);
        const groups = {};
        for (const x of actions) (groups[x.group] = groups[x.group] || []).push(x);
        body.replaceChildren(
          h('section', { class: 'cx-step' }, h('h3', {}, h('b', { text: '1' }), 'Which device does it control?'),
            h('div', { class: 'cx-devices' }, devices.map(d => h('button', { type: 'button', class: 'cx-device' + (dev && dev.key === d.key ? ' on' : ''), 'aria-pressed': String(!!(dev && dev.key === d.key)),
              onclick: () => { dev = d; if (b.skill_id && !actionsAvailable().some(x => x.id === b.skill_id && fits(x, d))) { b.skill_id = ''; b.params = {}; } b.device = d.category === 'this_pc' ? null : devName(d); b.device_key = d.category === 'this_pc' ? null : d.key; draw(); } },
            icon(CAT_ICON[d.category] || 'unknown'), h('span', { text: d.category === 'this_pc' ? d.label : devName(d) }))),
              C.devices.length ? null : h('p', { class: 'muted small', text: 'No device discovered yet. Run Discover on the Devices page to see your TV, vacuum or phone here.' }))),
          dev ? h('section', { class: 'cx-step' }, h('h3', {}, h('b', { text: '2' }), 'What should the button do?'),
            actions.length ? Object.entries(groups).map(([g, list]) => h('div', { class: 'cx-group' }, h('h4', { text: g }), h('div', { class: 'cx-actions' }, list.map(x => h('button', { type: 'button', class: 'cx-action' + (b.skill_id === x.id ? ' on' : ''), 'aria-pressed': String(b.skill_id === x.id), onclick: () => setAction(x) }, x.name)))))
              : h('p', { class: 'muted small', text: 'OpenBridge has no action for this device yet.' })) : null,
          a && (Object.keys(a.fields || {}).length || (a.generic && Object.keys((a.schema || {}).properties || {}).length)) ? h('section', { class: 'cx-step' }, h('h3', {}, h('b', { text: '3' }), 'Options'),
            a.generic ? Object.entries(a.schema.properties).map(([k, p]) => fieldRow(k, { label: k }, p)) : Object.entries(a.fields).map(([k, f]) => fieldRow(k, f))) : null,
          a ? h('section', { class: 'cx-step' }, h('h3', {}, h('b', { text: a.fields || a.generic ? '4' : '3' }), 'Text on the button'),
            h('div', { class: 'cx-label-row' }, h('input', { id: 'cx-label', class: 'cx-input', maxlength: '40', value: b.label, 'aria-label': 'Text on the button', oninput: e => { b.label = e.target.value; labelTouched = true; drawPreview(); count.textContent = `${b.label.length}/40`; } }), previewBtn),
            h('p', { class: 'muted small' }, count)) : null);
        count.textContent = `${b.label.length}/40`; drawPreview();
      }
      const count = h('span');
      const save = h('button', { class: 'primary', type: 'button', onclick: () => {
        b.label = (b.label || '').trim();
        if (!dev) return (err.textContent = 'Choose a device first.');
        if (!b.skill_id) return (err.textContent = 'Choose what the button does.');
        if (!b.label) return (err.textContent = 'Give the button a short text.');
        const p = profileOf();
        if (p && p.buttons.some(x => x !== initial && x.label.toLowerCase() === b.label.toLowerCase())) return (err.textContent = 'Another button already has this text.');
        if (b.skill_id === 'app_launch' && !b.params.package) return (err.textContent = 'Choose an app.');
        if (!needsDevice(b.skill_id)) { b.device = null; b.device_key = null; }
        done(b);
      } }, initial ? 'Save button' : 'Add button');
      dlg.append(h('div', { class: 'cx-editor-head' }, h('h2', { text: initial ? 'Edit button' : 'Add a button' }), h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close', onclick: () => done(null) }, icon('close'))),
        body, err, h('div', { class: 'cx-modal-actions' }, h('button', { class: 'ghost', type: 'button', onclick: () => done(null) }, 'Cancel'), save));
      dlg.addEventListener('cancel', e => { e.preventDefault(); done(null); });
      draw();
      document.body.append(dlg); dlg.showModal();
      const first = dlg.querySelector('.cx-device.on, .cx-device'); if (first) first.focus();
    });
  }

  // ---------- button list ----------
  async function addButton() {
    const p = profileOf(); if (!p) return;
    if (p.buttons.length >= (C.data.max_buttons || 12)) { flash(`A screen shows at most ${C.data.max_buttons || 12} buttons.`, 'bad'); return; }
    const b = await editButton(null);
    if (!b) return;
    p.buttons.push(b); paint(); queueSave();
  }
  async function editAt(i) {
    const p = profileOf(); const b = await editButton(p.buttons[i]);
    if (!b) return;
    p.buttons[i] = b; paint(); queueSave();
  }
  function removeAt(i) {
    const p = profileOf(); const [gone] = p.buttons.splice(i, 1); paint(); queueSave();
    undoToast(`Removed "${gone.label}".`, () => { p.buttons.splice(i, 0, gone); paint(); queueSave(); });
  }
  function move(i, j) { const p = profileOf(); if (j < 0 || j >= p.buttons.length) return; const [b] = p.buttons.splice(i, 1); p.buttons.splice(j, 0, b); paint(); queueSave(); const el = root.querySelector(`[data-row="${j}"] .cx-row-main`); if (el) el.focus(); }
  function undoToast(text, undo) {
    const box = document.getElementById('toasts'); if (!box) return;
    const t = h('div', { class: 'toast', role: 'status' }, text, ' ', h('button', { class: 'link-btn', type: 'button', onclick: () => { t.remove(); undo(); } }, 'Undo'));
    box.append(t); setTimeout(() => t.remove(), 6000);
  }

  // ---------- painting ----------
  function screenList() {
    return h('nav', { class: 'cx-screens', 'aria-label': 'Screens' }, h('h2', { class: 'cx-side-title', text: 'Screens' }),
      C.screens.map(s => {
        const sd = screenData(s.relay_id), n = sd.profiles.length;
        return h('button', { type: 'button', class: 'cx-screen' + (s.relay_id === C.screen ? ' on' : ''), 'aria-current': s.relay_id === C.screen ? 'true' : null,
          onclick: () => { C.screen = s.relay_id; C.profile = ''; pickDefaults(); paint(); } },
        h('span', { class: 'cx-screen-ico' }, icon(CAT_ICON[s.category] || 'unknown')),
        h('span', { class: 'cx-screen-text' }, h('strong', { text: s.label }), h('small', { text: (s.unpaired ? 'Not paired' : s.online ? 'Online' : 'Offline') + ' · ' + (n ? `${n} profile${n > 1 ? 's' : ''}` : 'no profile yet') })),
        h('i', { class: 'cx-dot ' + (s.online ? 'on' : 'off'), 'aria-hidden': 'true' }));
      }),
      C.demo ? h('button', { type: 'button', class: 'ghost small cx-demo-btn', onclick: leaveDemo }, 'Leave the demo') : null);
  }
  function statusOf(p) {
    const sd = screenData(C.screen);
    if (!p) return null;
    if (p._dirty || C.saving) return ['Saving…', 'muted'];
    const applied = sd.applied && sd.applied.profile_id === p.id;
    const same = applied && (C.demo ? sd.applied.digest === digestOf(p.buttons) : sd.applied.digest === p.digest);
    const liveMatch = sd.live && sd.live.length === p.buttons.length && sd.live.every((l, i) => l.label === p.buttons[i].label);
    if (applied && same && liveMatch) return [`On the ${word(screenOf(C.screen))} now`, 'ok'];
    if (applied) return ['Changed since you sent it', 'warn'];
    return [`Not on the ${word(screenOf(C.screen))}`, 'muted'];
  }
  let statusEl = null;
  function paintStatus() {
    if (!statusEl) return;
    const s = statusOf(profileOf());
    statusEl.replaceChildren(...(s ? [h('i', { class: 'cx-dot ' + s[1], 'aria-hidden': 'true' }), s[0]] : []));
    statusEl.className = 'cx-status ' + (s ? s[1] : '');
  }
  function profileBar() {
    const sd = screenData(C.screen), scr = screenOf(C.screen);
    return h('div', { class: 'cx-profiles' },
      h('div', { class: 'cx-tabs', role: 'tablist', 'aria-label': 'Profiles' },
        sd.profiles.map(p => h('button', { type: 'button', role: 'tab', class: 'cx-tab' + (p.id === C.profile ? ' on' : ''), 'aria-selected': String(p.id === C.profile),
          onclick: () => { C.profile = p.id; paint(); } }, p.name, sd.active === p.id ? h('i', { class: 'cx-dot ok', title: `Last sent to the ${word(scr)}`, 'aria-label': '(on screen)' }) : null)),
        h('button', { type: 'button', class: 'cx-tab cx-tab-new', onclick: () => newProfile() }, icon('plus'), 'New profile')));
  }
  function editor() {
    const p = profileOf(), scr = screenOf(C.screen), sd = screenData(C.screen);
    if (!p) {
      const tvs = C.devices.filter(d => d.category === 'tv'), vacs = C.devices.filter(d => d.category === 'vacuum');
      return h('section', { class: 'cx-empty panel' }, h('h2', { text: `Create your first profile for ${scr ? scr.label : 'this screen'}` }),
        h('p', { class: 'muted', text: 'A profile is a set of buttons. Make one for each moment ("Movie night", "Cleaning") and switch in one click.' }),
        h('div', { class: 'cx-starts' },
          h('button', { type: 'button', class: 'cx-start', onclick: () => newProfile([]) }, icon('plus'), h('strong', { text: 'Start empty' }), h('small', { text: 'Add your buttons one by one' })),
          TEMPLATES.map(t => { const d = (t.needs === 'tv' ? tvs : vacs)[0]; return h('button', { type: 'button', class: 'cx-start', disabled: !d, title: d ? null : `No ${t.needs === 'tv' ? 'TV' : 'robot vacuum'} discovered yet`, onclick: () => newProfile(t.make(d), t.name) }, icon(t.needs), h('strong', { text: t.name }), h('small', { text: d ? `Ready-made buttons for ${devName(d)}` : 'Discover the device first' })); }),
          sd.live && sd.live.some(l => l.editable) ? h('button', { type: 'button', class: 'cx-start', onclick: capture }, icon('watch'), h('strong', { text: 'Copy what is on the screen' }), h('small', { text: 'Edit the buttons OpenBridge made for you' })) : null));
    }
    const max = C.data.max_buttons || 12;
    statusEl = h('span', { class: 'cx-status' });
    const list = h('ol', { class: 'cx-list', 'aria-label': 'Buttons, in screen order' }, p.buttons.map((b, i) => {
      const d = describe(b);
      return h('li', { class: 'cx-row', 'data-row': i, draggable: 'true',
        ondragstart: e => { C.dragFrom = i; e.dataTransfer.effectAllowed = 'move'; e.currentTarget.classList.add('dragging'); },
        ondragend: e => e.currentTarget.classList.remove('dragging'),
        ondragover: e => { e.preventDefault(); e.currentTarget.classList.add('over'); },
        ondragleave: e => e.currentTarget.classList.remove('over'),
        ondrop: e => { e.preventDefault(); e.currentTarget.classList.remove('over'); if (C.dragFrom !== null && C.dragFrom !== i) move(C.dragFrom, i); C.dragFrom = null; } },
      h('span', { class: 'cx-grip', 'aria-hidden': 'true', title: 'Drag to reorder' }, '⋮⋮'),
      h('button', { type: 'button', class: 'cx-row-main', onclick: () => editAt(i), 'aria-label': `Edit ${b.label}` },
        h('strong', { text: b.label }), h('small', { text: `${d.what} · ${d.on}` })),
      h('span', { class: 'cx-row-tools' },
        h('button', { type: 'button', class: 'icon-btn tiny', 'aria-label': `Move ${b.label} up`, disabled: i === 0, onclick: () => move(i, i - 1) }, '↑'),
        h('button', { type: 'button', class: 'icon-btn tiny', 'aria-label': `Move ${b.label} down`, disabled: i === p.buttons.length - 1, onclick: () => move(i, i + 1) }, '↓'),
        h('button', { type: 'button', class: 'icon-btn tiny cx-del', 'aria-label': `Remove ${b.label}`, onclick: () => removeAt(i) }, icon('close'))));
    }));
    const head = h('div', { class: 'cx-edit-head' },
      h('div', {}, h('h2', { text: p.name }), statusEl),
      h('div', { class: 'cx-edit-tools' },
        h('button', { type: 'button', class: 'ghost small', onclick: renameProfile }, 'Rename'),
        h('button', { type: 'button', class: 'ghost small', onclick: duplicateProfile }, 'Duplicate'),
        h('button', { type: 'button', class: 'ghost small cx-danger', onclick: deleteProfile }, 'Delete')));
    const panel = h('section', { class: 'panel cx-editor-panel', 'aria-label': 'Profile buttons' }, head,
      p.buttons.length ? list : h('p', { class: 'cx-none muted', text: 'No buttons yet. Add the first one: pick a device, pick what it does, done.' }),
      h('div', { class: 'cx-add-row' },
        h('button', { type: 'button', class: 'cx-add', disabled: p.buttons.length >= max, onclick: addButton }, icon('plus'), 'Add a button'),
        h('span', { class: 'muted small', text: `${p.buttons.length} of ${max} buttons` })));
    setTimeout(paintStatus);
    return panel;
  }
  function preview() {
    const p = profileOf(), scr = screenOf(C.screen), sd = screenData(C.screen);
    const cat = scr && ['tv', 'phone', 'tablet'].includes(scr.category) ? (scr.category === 'tablet' ? 'phone' : scr.category) : 'watch';
    const face = h('div', { class: 'watch-face cx-face' });
    const buttons = p ? p.buttons : [];
    face.append(...buttons.map((b, i) => h('button', { type: 'button', class: 'watch-btn', title: 'Edit this button', onclick: () => editAt(i) }, b.label)));
    if (!buttons.length) face.append(h('span', { class: 'muted small', text: 'Your buttons appear here' }));
    const live = (sd.live || []).filter(Boolean);
    const differs = p && live.length && !(live.length === buttons.length && live.every((l, i) => l.label === buttons[i].label));
    return h('aside', { class: 'panel cx-preview', 'aria-label': 'Preview' },
      h('div', { class: 'cx-preview-head' }, h('h2', { text: 'Preview' }), h('span', { class: 'muted small', text: scr ? scr.label : '' })),
      h('div', { class: 'target-device ' + cat }, face),
      p ? h('button', { type: 'button', class: 'primary cx-send', disabled: C.busy || C.saving || (scr && scr.unpaired) || null, onclick: send }, icon('verified'), `Send to the ${word(scr)}`) : null,
      scr && scr.unpaired ? h('p', { class: 'muted small', text: 'This screen is not paired right now. Pair it again to send buttons.' }) : null,
      scr && !scr.online && !scr.unpaired && !C.demo ? h('p', { class: 'muted small', text: `The ${word(scr)} is offline. Sending needs it switched on, with the OpenBridge Companion open.` }) : null,
      live.length ? h('div', { class: 'cx-live' }, h('h3', { text: `On the ${word(scr)} now` }),
        h('p', { class: 'cx-live-list' }, live.map(l => h('span', { class: 'cx-chip' + (l.editable ? '' : ' locked'), title: l.editable ? null : 'From an approved plan or a saved skill', text: l.label }))),
        h('div', { class: 'row wrap' },
          differs && live.some(l => l.editable) && !C.demo ? h('button', { type: 'button', class: 'ghost small', onclick: capture }, 'Copy into a new profile') : null,
          h('button', { type: 'button', class: 'ghost small cx-danger', onclick: clearScreen }, 'Remove from screen'))) : null,
      modulesPanel(),
      h('p', { class: 'muted small cx-note', text: 'Saving never changes the screen. Buttons appear only when you press Send, and each press runs its action once.' }));
  }
  // ---------- optional modules (Oracle...) per screen ----------
  async function setModule(name, on) {
    try {
      await post('/api/v2/companion_modules', { relay_id: C.screen, module: name, enabled: on, consent: true });
      const s = ((C.modules || {}).screens || {})[C.screen];
      if (s) s.modules = Object.assign({}, s.modules || {}, { [name]: on });
      flash(on ? 'Module turned on.' : 'Module turned off.', 'ok');
    } catch (e) { C.error = 'Could not change the module: ' + e.message; }
    paint();
  }
  function modulesPanel() {
    if (C.demo || !C.modules) return null;
    const s = (C.modules.screens || {})[C.screen];
    const defs = C.modules.modules || {};
    if (!s) return null;
    return h('div', { class: 'cx-live cx-modules' }, h('h3', { text: 'Modules' }),
      !s.modules ? h('p', { class: 'muted small', text: s.online ? 'This Companion is too old for modules: update it to 0.14.0 or later.' : 'Offline: open the OpenBridge Companion to change its modules.' }) : null,
      s.modules ? Object.keys(defs).map(name => h('label', { class: 'row wrap cx-module' },
        h('input', { type: 'checkbox', checked: !!s.modules[name] || null, onchange: e => setModule(name, e.target.checked) }),
        h('span', { text: defs[name] }))) : null);
  }
  function emptyState() {
    return h('section', { class: 'cx-empty panel cx-noscreen' },
      h('span', { class: 'cx-big-ico' }, icon('watch')),
      h('h2', { text: 'Pair a screen to put your own buttons on it' }),
      h('p', { class: 'muted', text: 'Install the OpenBridge Companion on your TV, watch or phone and pair it with this PC. Then come back here to build its buttons.' }),
      h('div', { class: 'row wrap cx-center' },
        h('button', { type: 'button', class: 'primary', 'data-action': 'connect' }, icon('plus'), 'Connect a screen'),
        h('button', { type: 'button', class: 'ghost', onclick: startDemo }, 'Try the editor with a demo watch')),
      h('p', { class: 'muted small', text: 'The demo is SIMULATED: nothing is saved or sent to a device.' }));
  }
  function paint() {
    if (!root) return;
    const focusId = document.activeElement && document.activeElement.id;
    statusEl = null;
    const banner = C.demo ? h('p', { class: 'mode-banner sim', role: 'status' }, h('strong', { text: 'SIMULATED DEMO' }), ' A demo watch and TV. Nothing is saved or sent to a real device.') : null;
    const error = C.error ? h('p', { class: 'mode-banner bad', role: 'alert' }, C.error, ' ', h('button', { type: 'button', class: 'link-btn', onclick: () => { C.error = ''; paint(); } }, 'Dismiss')) : null;
    if (C.loading && !C.screens.length) { root.replaceChildren(h('p', { class: 'muted', text: 'Loading your screens…' })); return; }
    if (!C.screens.length) { root.replaceChildren(...[banner, error, emptyState()].filter(Boolean)); return; }
    root.replaceChildren(...[banner, error,
      h('div', { class: 'cx-layout' }, screenList(),
        h('div', { class: 'cx-main' }, profileBar(), h('div', { class: 'cx-work' }, editor(), preview())))].filter(Boolean));
    if (focusId) { const f = document.getElementById(focusId); if (f) f.focus({ preventScroll: true }); }
  }

  function render(arg, context) {
    ctx = context || {};
    root = document.getElementById('controls-root');
    if (arg) C.screen = decodeURIComponent(arg);
    if (C.demo) { paint(); return; }
    load();
  }
  global.OBViews = global.OBViews || {};
  global.OBViews.controls = { render, _state: C, _actions: ACTIONS };
})(window);
