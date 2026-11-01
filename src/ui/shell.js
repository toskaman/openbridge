'use strict';
/* OpenBridge application shell (2026-10-28).
   Workspaces, navigation, device cards, skills, fabric graph, automations, activity, connect wizard, assistant,
   command palette and notifications. It reuses the existing app.js functions and DOM (renderFabric, showDevice,
   postJson, request, element, panels) so every existing action, consent rule and test hook keeps working.
   Everything rendered here comes from real API responses; nothing is simulated in the shell itself. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  function h(tag, props, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = String(v);
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.assign(n.dataset, v);
      else n.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    return n;
  }
  const SVGNS = 'http://www.w3.org/2000/svg';
  function s(tag, attrs, ...kids) { const n = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v); for (const kid of kids) n.append(kid); return n; }
  function icon(name, cls) { const sv = s('svg', { 'aria-hidden': 'true', class: cls || 'ic' }); sv.append(s('use', { href: '#i-' + name })); return sv; }
  const ICON = { phone: 'phone', tv: 'tv', watch: 'watch', computer: 'pc', router: 'router', vacuum: 'vacuum', ble: 'ble', media: 'media', apple: 'apple', android: 'phone', tablet: 'phone' };
  const CAT_LABEL = { phone: 'Android phone', tv: 'TV', watch: 'Wear OS watch', computer: 'Windows PC', router: 'Internet router', vacuum: 'Smart vacuum', ble: 'Bluetooth device', media: 'Media device', apple: 'Apple device', android: 'Android device', iot: 'Smart-home device', nas: 'Storage', printer: 'Printer', hub: 'Hub', network: 'Network device', unknown: 'Unknown device' };
  const catLabel = c => CAT_LABEL[c] || c;
  const api = (p, o) => request(p, o);
  const post = (p, b) => postJson(p, b);
  const store = { get(k) { try { return localStorage.getItem('ob.' + k); } catch { return null; } }, set(k, v) { try { localStorage.setItem('ob.' + k, v); } catch { /* storage unavailable */ } } };

  // ---------------- state ----------------
  const st = { snap: null, routes: [], events: [], seq: 0, recovery: null, model: null, diagnosis: [], selected: null, filter: '', group: 'all', layout: 'grid', graphSkill: 'all', graphView: 'graph', seenNotif: Number(store.get('notifSeen') || 0) };
  const linksOf = key => (st.snap ? st.snap.links.filter(l => l.child === key) : []);
  const grantOf = key => { const g = new Set(linksOf(key).flatMap(l => l.grants)); return g.has('control') ? 'control' : g.has('read') ? 'read' : g.size ? 'observe' : 'none'; };
  const capOf = (d, name) => (d.capabilities || []).find(c => c.name === name);
  const isAndroid = d => ['phone', 'tv', 'watch', 'android'].includes(d.category);
  const adbLinked = d => !!((d.handles || {}).USB || (d.handles || {}).WIFI);
  const label = d => (typeof displayLabel === 'function' ? displayLabel(d) : d.label);
  const relayParent = key => { const l = st.snap && st.snap.links.find(x => x.child === key && x.parent !== 'pc'); return l ? st.snap.devices.find(d => d.key === l.parent) : null; };

  // ---------------- capability model (plain language, honest states) ----------------
  // state: available · permission (needs a step/consent) · detected (hardware seen, no path) · unsupported · planned
  function deviceCaps(d) {
    const out = [], g = grantOf(d.key), linked = adbLinked(d);
    const add = (id, name, ic, state, plain, tech, extra) => out.push(Object.assign({ id, name, icon: ic, state, plain, tech }, extra || {}));
    if (isAndroid(d)) {
      if (linked && g === 'control') {
        add('remote', d.category === 'tv' ? 'TV remote control' : 'Remote control', 'media', 'available', d.category === 'tv' ? 'Power, volume, channels, arrows and OK, playback — like the physical remote.' : 'Keys, volume, navigation and touch, from this PC.', 'device_action key/tap/swipe over ADB; irreversible, consent per action', { verify: true });
        add('touch', 'Touchpad & text', 'devices', 'available', 'Click, drag and type on the device screen from this PC.', 'input tap/swipe/text over ADB');
        add('apps', 'Apps & web links', 'skills', 'available', 'Open an installed app or a web address on the device.', 'am start -n / VIEW intent (http/https only)');
        add('settings', 'Volume & brightness with Undo', 'gear', 'available', 'Change volume, brightness or screen timeout; OpenBridge reads the value back and can restore it exactly.', 'settings / media_session with independent read-back (EXACT)');
        add('diag', 'Health & diagnostics', 'activity', 'available', 'Battery, storage, Wi-Fi, temperature and power state, each with its source.', 'read_facts (allowlisted ADB reads)');
        if (['tv', 'phone'].includes(d.category)) add('visual', 'Screen check with Meta', 'meta', 'available', 'Takes one screenshot and asks local Muse Glimmer what is on screen, compared with what Android reports.', 'visual_readback · local only · consent');
      } else if (linked) add('remote', 'Remote control', 'media', 'permission', 'Connected, but this PC is only allowed to read. Approve control to use it.', 'link grant: ' + g);
      else if (d.category === 'tv' && !(d.handles || {}).WIFI) add('remote', 'TV remote control', 'media', 'permission', 'Seen on the network. Turn on network debugging on the TV to control it.', 'mDNS only; use “Connect over ADB Wi-Fi”', { action: 'connect', connectType: 'tv' });
      else add('remote', 'Remote control', 'media', 'permission', 'Seen on the network. Pair it once (USB or Wi-Fi code) to control it.', 'no ADB link yet', { action: 'connect', connectType: d.category === 'watch' ? 'watch' : 'phone' });
      const relay = capOf(d, 'ble_relay');
      if (relay) add('ble', 'Bluetooth for this PC', 'ble', relay.status === 'REAL_HARDWARE_VERIFIED' ? 'available' : relay.status === 'NOT_SUPPORTED' ? 'permission' : 'permission', relay.status === 'REAL_HARDWARE_VERIFIED' ? 'Finds nearby Bluetooth devices for this PC (scan only: it cannot connect to or control them).' : 'Can find nearby Bluetooth devices for this PC once the OpenBridge Companion app is installed and paired.', `ble_relay · ${relay.status} · ${relay.evidence || ''}`);
      if (d.category === 'phone') add('sms', 'Calls & SMS', 'phone', 'unsupported', 'The phone can do it, but Android does not let another computer send SMS or place calls silently. OpenBridge does not.', 'no adapter by design');
    } else if (d.category === 'vacuum') {
      add('vac-status', 'Robot status', 'activity', g === 'none' ? 'detected' : 'available', 'Battery, cleaning state, brush and filter wear.', 'Tuya local protocol 3.4, owner-linked key', g === 'none' ? { action: 'connect', connectType: 'vacuum' } : null);
      add('vac-settings', 'Suction & voice volume with Undo', 'gear', g === 'control' ? 'available' : 'permission', 'Change suction or volume; the robot reports the value back and OpenBridge can restore it exactly.', 'tuya_setting (EXACT)');
      add('vac-drive', 'Start, pause, dock & drive', 'vacuum', g === 'control' ? 'available' : 'permission', 'Start or pause cleaning, send it home, or drive it a short step (it stops by itself).', 'tuya_command · irreversible · consent per command');
    } else if (d.category === 'computer') {
      const diag = capOf(d, 'windows_diagnostics');
      add('pc-diag', 'PC health', 'activity', diag ? 'available' : 'detected', 'CPU, memory, disks and uptime from the OpenBridge agent on that PC.', 'allowlisted agent reads');
      add('pc-job', 'Run a command', 'pc', diag ? 'available' : 'permission', diag ? 'Run one command you type on that PC and see its output. It cannot be undone, so you approve each one.' : 'Seen on the network. Install the matching OpenBridge agent build to connect it.', diag ? 'pc_job via BridgeWindows exec.run · clear TCP on your LAN' : 'no agent link yet', diag ? null : { action: 'connect', connectType: 'pc' });
    } else if (d.category === 'router') {
      const r = capOf(d, 'lan_inventory') || capOf(d, 'igd_status') || capOf(d, 'freebox_api');
      const avail = g !== 'observe' && g !== 'none';
      add('router-diag', 'Internet & network diagnostics', 'router', avail ? 'available' : 'permission', 'Internet status, connected devices and Wi-Fi radios, read-only.', r ? `${r.name} · ${r.status}` : 'router API', avail ? null : { action: 'connect', connectType: 'router' });
      add('router-config', 'Change router settings', 'gear', 'unsupported', 'OpenBridge never changes router settings: there is no independent way to recover if something breaks.', 'BLOCKED by policy');
    } else if (d.category === 'ble') {
      const p = relayParent(d.key);
      add('ble-seen', 'Seen over Bluetooth', 'ble', 'detected', `Detected through ${p ? label(p) : 'a relay'}. OpenBridge can see it is nearby, not connect to it.`, 'BLE advertisement via relay · GATT/Classic not supported');
    } else if (d.category === 'apple') {
      add('ios', 'iPhone / Apple control', 'apple', 'planned', 'Seen on the network. There is no iOS Companion app yet, and iOS has no debugging bridge like Android.', 'mDNS only · iOS Companion planned', { action: 'connect', connectType: 'iphone' });
    } else {
      add('seen', 'On the network', 'unknown', 'detected', 'OpenBridge can see this device but has no adapter for it yet.', 'observe only · ' + linksOf(d.key).map(l => l.source).join(', '), { action: 'connect' });
    }
    return out;
  }
  const STATE_TXT = { available: 'Available', permission: 'Needs a step', detected: 'Detected only', unsupported: 'Not supported', planned: 'Planned' };

  // ---------------- skills (derived from real providers in the current graph) ----------------
  function skills() {
    const devs = st.snap ? st.snap.devices : [];
    const ctrl = d => grantOf(d.key) === 'control';
    const relays = devs.filter(d => capOf(d, 'ble_relay'));
    const fresh = st.routes.filter(r => r.status === 'FRESH').length;
    const glimmer = st.model && String(st.model.model_id || '').startsWith('muse-glimmer') && st.model.inference_available;
    const list = [
      { id: 'bluetooth', name: 'Bluetooth Bridge', icon: 'ble', plain: 'Lets this PC find Bluetooth devices through a phone or TV that has Bluetooth.', providers: relays, consumers: ['This PC'], evidence: 'Verified on hardware: relays through an Android phone and an Android TV.', verifiedEver: true, readyIf: relays.some(d => capOf(d, 'ble_relay').status === 'REAL_HARDWARE_VERIFIED'), limits: 'Scan only. Connecting to, pairing with or controlling Bluetooth devices (GATT, audio, file transfer) is not supported.', route: true },
      { id: 'tv-remote', name: 'TV Remote Control', icon: 'tv', plain: 'Control the TV from this PC: power, volume, channels, navigation, apps.', providers: devs.filter(d => d.category === 'tv' && ctrl(d) && adbLinked(d)), consumers: ['This PC', 'Galaxy Watch7 (planned)'], evidence: 'Verified on hardware: keys, channels, power off/on, YouTube launch, touchpad.', verifiedEver: true },
      { id: 'device-remote', name: 'Phone & Watch Remote', icon: 'watch', plain: 'Keys, touch, apps and exact volume on Android phones and Wear OS watches.', providers: devs.filter(d => ['phone', 'watch', 'android'].includes(d.category) && ctrl(d) && adbLinked(d)), consumers: ['This PC'], evidence: 'Verified on hardware: Blackview BV9300 Pro, Galaxy Watch7. Some vendors (MIUI) block input until a security option is enabled.', verifiedEver: true },
      { id: 'vacuum', name: 'Smart Vacuum Control', icon: 'vacuum', plain: 'Status, suction and volume with Undo, start/pause/dock and short manual drives.', providers: devs.filter(d => d.category === 'vacuum'), consumers: ['This PC'], evidence: 'Verified on hardware: reads, suction change + exact Undo, start, pause, moves, dock.', verifiedEver: true },
      { id: 'router', name: 'Router Diagnostics', icon: 'router', plain: 'Internet status, optical signal, connected devices — read-only.', providers: devs.filter(d => d.category === 'router' && grantOf(d.key) !== 'observe'), consumers: ['This PC', 'Meta diagnosis'], evidence: 'Verified on hardware: Freebox OS API and generic UPnP-IGD.', verifiedEver: true },
      { id: 'compute', name: 'Remote Commands', icon: 'pc', plain: 'Run a command you type on another Windows PC and get its output.', providers: devs.filter(d => d.category === 'computer' && capOf(d, 'windows_diagnostics')), consumers: ['This PC'], evidence: 'Verified on hardware: second PC ran hostname and system queries.', verifiedEver: true, limits: 'Irreversible; one PC at a time today.' },
      { id: 'visual', name: 'Visual Verification', icon: 'meta', plain: 'Meta Muse Glimmer looks at a screenshot and checks it against what the device reports.', providers: devs.filter(d => ['tv', 'phone'].includes(d.category) && ctrl(d) && adbLinked(d)), consumers: ['Diagnostics'], evidence: 'Verified on hardware (TV): reported INCONCLUSIVE when Glimmer disagreed — by design.', verifiedEver: true, needs: glimmer ? null : 'Start this PC with the local Muse Glimmer model to use it.' },
      { id: 'troubleshoot', name: 'Cross-device Troubleshooting', icon: 'activity', plain: 'Builds one timeline across TV, router and phone and lists competing explanations — correlations, not proofs.', providers: devs.filter(d => grantOf(d.key) === 'read' || grantOf(d.key) === 'control'), consumers: ['Meta diagnosis'], evidence: 'Verified on hardware: 10-minute timeline with an induced link drop.', verifiedEver: true },
      { id: 'identify', name: 'Device Identification', icon: 'unknown', plain: 'Recognises phones, tablets, watches and other hardware on your network and suggests the easiest way to connect them.', providers: devs.length ? [{ key: 'pc', label: 'This PC', category: 'computer' }] : [], consumers: ['Connect device'], evidence: 'Uses discovery results only; nothing is probed without your request.', verifiedEver: true, always: true },
      { id: 'voice', name: 'Voice Commands', icon: 'meta', plain: 'Push to talk; Meta Muse Voice Transcribe turns speech into a proposal you review before anything runs.', providers: [{ key: 'pc', label: 'This PC (Meta API key required)', category: 'computer' }], consumers: ['Assistant'], evidence: 'Verified live once with a synthetic speech clip.', verifiedEver: true, experimental: true, always: true }
    ];
    for (const k of list) {
      const n = k.providers.length;
      k.lifecycle = k.experimental ? 'Experimental' : k.verifiedEver ? 'Verified' : 'Discovered';
      k.availability = !st.snap && !k.always ? 'Not checked yet' : k.needs ? 'Needs a step' : k.route && n && !k.readyIf ? 'Needs a step' : n ? 'Ready' : 'Offline';
      if (k.route) k.routeNote = st.routes.length ? `${fresh} of ${st.routes.length} relay route(s) fresh` : n ? 'Pair a relay in this session to measure route health' : 'No relay-capable device found';
    }
    return list;
  }

  // ---------------- router ----------------
  const VIEWS = { home: 'Home', explore: 'Explore', devices: 'My Devices', skills: 'Learned Skills', fabric: 'Device Fabric', automations: 'Automations', activity: 'Activity & Recovery', replay: 'Demo replay', advanced: 'Advanced diagnostics' };
  let current = null;
  function route() {
    const m = location.hash.match(/^#\/([a-z]+)(?:\/(.+))?/);
    if (m && VIEWS[m[1]]) return show(m[1], m[2]);
    const legacy = /^#[a-z][a-z0-9-]*$/i.test(location.hash) ? $(location.hash) : null;   // old section anchors (#fabric, #evidence…)
    if (legacy && legacy.closest('[data-view]')) return show(viewOf(legacy));
    if (!current) show('home');
  }
  function viewOf(el) { const v = el && el.closest('[data-view]'); return v ? v.dataset.view : 'home'; }
  function show(view, arg) {
    for (const v of $$('.view')) v.hidden = v.dataset.view !== view;
    for (const a of $$('[data-nav]')) { const on = a.dataset.nav === view; a.classList.toggle('active', on); if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); }
    $('#crumb').textContent = VIEWS[view];
    document.title = `${VIEWS[view]} · OpenBridge`;
    closeMenu();
    if (current !== view) { current = view; $('#view').scrollTop = 0; window.scrollTo(0, 0); }
    render(view, arg);
  }
  function render(view, arg) {
    if (view === 'home') renderHome();
    if (view === 'explore' && typeof renderExplore === 'function') renderExplore();
    if (view === 'devices') { renderDevices(); if (arg) selectDevice(decodeURIComponent(arg)); }
    if (view === 'skills') renderSkills();
    if (view === 'fabric') renderGraph();
    if (view === 'automations') renderAutomations();
    if (view === 'activity') renderActivity();
    if (view === 'replay' && typeof renderReplay === 'function') renderReplay(arg);
  }
  const go = (view, arg) => { location.hash = '#/' + view + (arg ? '/' + encodeURIComponent(arg) : ''); };

  // ---------------- data ----------------
  async function refreshSide() {
    try { st.routes = (await api('/api/v2/routes')).routes || []; } catch { st.routes = []; }
    try { st.recovery = await api('/api/v2/recovery'); } catch { st.recovery = null; }
    if (st.snap) { try { st.diagnosis = (await api('/api/v2/diagnosis')).findings || []; } catch { st.diagnosis = []; } }
  }
  async function pollEvents() {
    if (document.hidden) return;
    try {
      const ev = (await api('/api/v2/events?since=' + st.seq)).events || [];
      if (ev.length) { st.events = st.events.concat(ev).slice(-300); st.seq = ev[ev.length - 1].seq; updateBadge(); if (current === 'activity') renderActivity(); if (current === 'home') renderHomeActivity(); }
    } catch { /* server unavailable: keep the last view */ }
  }
  function onSnapshot(snap) {
    st.snap = snap && snap.devices ? snap : null;
    const n = st.snap ? st.snap.devices.length : 0;
    $('#nav-count-devices').textContent = n ? String(n) : '';
    refreshSide().then(() => { if (current) render(current); });
    if (current) render(current);
  }

  // ---------------- home ----------------
  function stat(labelText, value, sub) { return h('div', { class: 'stat' }, h('span', { class: 'stat-label', text: labelText }), h('strong', { text: value }), h('small', { text: sub })); }
  function renderHome() {
    const sn = st.snap, sk = skills();
    const devices = sn ? sn.devices.filter(d => linksOf(d.key).length) : [];
    const verified = sn ? sn.devices.reduce((a, d) => a + (d.capabilities || []).filter(c => c.status === 'REAL_HARDWARE_VERIFIED').length, 0) : null;
    const ready = sk.filter(k => k.availability === 'Ready').length;
    const fresh = st.routes.filter(r => r.status === 'FRESH').length;
    $('#home-stats').replaceChildren(
      stat('Connected devices', sn ? devices.filter(d => grantOf(d.key) !== 'observe').length : '—', sn ? `${devices.length} seen on your network` : 'Run discovery to find them'),
      stat('Verified capabilities', sn ? verified : '—', 'proven on real hardware'),
      stat('Skills ready now', sn ? `${ready}/${sk.length}` : '—', 'providers online in this session'),
      stat('Live relay routes', st.routes.length ? `${fresh}/${st.routes.length}` : '—', st.routes.length ? 'fresh Bluetooth relays' : 'no relay paired this session'));
    const row = $('#home-devices'); row.replaceChildren();
    if (!sn) row.append(empty('No devices yet', 'OpenBridge only looks when you ask. Discovery is read-only and stays on your local network.', h('button', { class: 'primary', type: 'button', onclick: discoverAndOpen }, 'Discover devices')));
    else for (const d of sn.devices.filter(d => d.category !== 'ble').slice(0, 8)) row.append(deviceCard(d, true));
    renderHomeActions(); renderInsights(); renderHomeActivity(); miniGraph();
  }
  function renderHomeActions() {
    const list = $('#home-actions'); list.replaceChildren();
    const sn = st.snap, acts = [];
    if (!sn) acts.push(['devices', 'Discover nearby devices', 'Read-only scan of your local network and connected devices.', discoverAndOpen]);
    if (sn) {
      const unpaired = sn.devices.filter(d => isAndroid(d) && !adbLinked(d));
      if (unpaired.length) acts.push(['phone', `Connect ${label(unpaired[0])}`, 'It is on your network but not paired yet — pair it once with a code.', () => openConnect()]);
      const relay = sn.devices.find(d => capOf(d, 'ble_relay') && adbLinked(d));
      if (relay) acts.push(['ble', 'Reach Bluetooth devices', `This PC has no Bluetooth; scan through ${label(relay)}.`, () => go('devices', relay.key)]);
      const unknown = sn.devices.filter(d => ['unknown', 'iot', 'media', 'apple'].includes(d.category));
      if (unknown.length) acts.push(['unknown', 'Identify unknown devices', `${unknown.length} device(s) seen without an adapter.`, () => openConnect()]);
      const tv = sn.devices.find(d => d.category === 'tv' && grantOf(d.key) !== 'observe');
      if (tv) acts.push(['activity', 'Investigate a device problem', `Build a cross-device timeline for ${label(tv)}.`, () => { go('devices', tv.key); setTimeout(() => setTab('controls'), 60); }]);
    }
    acts.push(['skills', 'Teach a new skill', 'Describe what you want; OpenBridge checks what each device can really do.', openTeach]);
    for (const [ic, t, sub, fn] of acts.slice(0, 5)) list.append(h('button', { class: 'action-item', type: 'button', onclick: fn }, icon(ic), h('span', {}, h('strong', { text: t }), h('small', { text: sub })), h('span', { class: 'chev', 'aria-hidden': 'true', text: '›' })));
  }
  function renderInsights() {
    const box = $('#home-insights'); box.replaceChildren();
    if (!st.snap) { box.append(h('p', { class: 'muted', text: 'Insights appear after discovery. Each one states whether it is an observation or an inference, and what it rests on.' })); return; }
    const NICE = { ble_via_relay_possible: 'This PC has no Bluetooth, but relay-capable devices can scan for it.', ble_unreachable: 'No Bluetooth path: no local adapter and no relay-capable device.', relay_routes_degraded: 'A Bluetooth relay is offline or has not scanned recently.', blocked_capabilities: 'Some capabilities are blocked by policy or missing permission.', possible_duplicates: 'Some devices may be the same hardware seen twice (not merged).', pending_transactions: 'An operation ended without verification — check Recovery.', graph: 'The server has no discovery result to reason about yet — run discovery.' };
    const items = st.diagnosis.filter(f => f.kind === 'INFERRED' || f.level === 'warning').slice(0, 4);
    if (!items.length) box.append(h('p', { class: 'muted', text: 'No warnings from the current graph.' }));
    for (const f of items) box.append(h('div', { class: 'insight ' + (f.level === 'warning' ? 'warn' : '') }, h('span', { class: 'kind ' + f.kind.toLowerCase(), text: f.kind === 'INFERRED' ? 'Inference' : 'Observation' }), h('p', { text: NICE[f.name] || `${f.name.replace(/_/g, ' ')}: ${f.value}` }), f.basis ? h('small', { text: 'Based on: ' + f.basis }) : null));
    box.append(h('button', { class: 'ghost small', type: 'button', onclick: openAssistant }, icon('meta'), 'Ask Meta AI'));
  }
  const PRIM = { read_facts: 'Read device facts', bounded_discovery: 'Discovery', relay_ble_scan: 'Bluetooth scan via relay', relay_revoke: 'Revoke relay', android_optional_app_state: 'Disable optional app', undo_transaction: 'Undo', session_cleanup: 'Session restore', watch_start: 'Start watch', watch_stop: 'Stop watch', diagnostic_report: 'Diagnostic report', diagnostic_probe: 'Re-measure', visual_readback: 'Screen check', tuya_setting: 'Vacuum setting', tuya_undo: 'Vacuum Undo', tuya_command: 'Vacuum command', device_capabilities: 'Capability check', device_action: 'Device action', device_macro: 'Sequence', pc_job: 'PC command' };
  function timelineItem(e) {
    const ok = e.verified || ['VERIFIED', 'REVERTED', 'EXECUTED'].includes(e.state);
    const bad = ['FAILED', 'UNKNOWN_TIMEOUT', 'PARTIAL'].includes(e.state) || (e.kind === 'remote_request' && ['REVOKED', 'EXPIRED', 'BLOCKED', 'SUSPENDED'].includes(e.state));
    const title = e.kind === 'receipt' ? (PRIM[e.primitive_id] || e.primitive_id) : e.kind === 'remote_request' ? 'Remote press' : e.kind.replace(/_/g, ' ');
    const sub = e.kind === 'receipt' ? `${e.state}${e.verified ? ' · read back' : ''}` : e.kind === 'remote_request' ? `${e.state}${e.reason ? ' — ' + e.reason : ''}` : (e.finding ? `${e.finding} = ${e.value}` : '');
    return h('li', { class: 'tl ' + (bad ? 'bad' : ok ? 'ok' : '') }, h('span', { class: 'tl-dot', 'aria-hidden': 'true' }), h('div', {}, h('strong', { text: title }), h('small', { text: `${sub}${sub ? ' · ' : ''}${(e.at || '').replace('T', ' ').slice(0, 19)}` })), e.transaction_id ? h('code', { text: e.transaction_id.slice(0, 11), title: e.transaction_id }) : null);
  }
  function renderHomeActivity() {
    const ol = $('#home-activity'); if (!ol) return; ol.replaceChildren();
    const ev = st.events.filter(e => e.kind === 'receipt' || e.kind.startsWith('watch_') || e.kind === 'reattached' || e.kind === 'remote_request').slice(-6).reverse();
    if (!ev.length) ol.append(h('li', { class: 'muted', text: 'No operation yet in this session.' }));
    for (const e of ev) ol.append(timelineItem(e));
  }
  function miniGraph() {
    const box = $('#home-mini-graph'); box.replaceChildren();
    const devs = st.snap ? st.snap.devices.filter(d => d.category !== 'ble').slice(0, 7) : [];
    const sv = s('svg', { viewBox: '0 0 320 220', class: 'mini' });
    const cx = 70, cy = 110;
    const defs = s('defs'); const gr = s('linearGradient', { id: 'mg', x1: '0', x2: '1' }); gr.append(s('stop', { offset: '0', 'stop-color': '#22d3ee' }), s('stop', { offset: '1', 'stop-color': '#8b5cf6' })); defs.append(gr); sv.append(defs);
    const n = Math.max(devs.length, 4);
    for (let i = 0; i < n; i++) {
      const a = (-60 + (120 * i) / Math.max(n - 1, 1)) * Math.PI / 180, x = cx + 190 * Math.cos(a), y = cy + 95 * Math.sin(a);
      const d = devs[i];
      sv.append(s('path', { d: `M${cx} ${cy} C ${cx + 80} ${cy}, ${x - 70} ${y}, ${x} ${y}`, stroke: d ? 'url(#mg)' : '#2a3550', 'stroke-width': d ? '1.6' : '1', fill: 'none', 'stroke-dasharray': d && grantOf(d.key) === 'observe' ? '4 4' : '' }));
      const g = s('g', { transform: `translate(${x - 14} ${y - 14})` }); g.append(s('rect', { width: '28', height: '28', rx: '8', fill: '#121a2e', stroke: d ? '#2b7a8c' : '#243049' }));
      if (d) { const u = s('use', { href: '#i-' + (ICON[d.category] || 'unknown'), x: '5', y: '5', width: '18', height: '18', color: '#7dd3fc' }); g.append(u); }
      sv.append(g);
    }
    const pc = s('g', { transform: `translate(${cx - 22} ${cy - 22})` }); pc.append(s('rect', { width: '44', height: '44', rx: '12', fill: 'url(#mg)' }), s('use', { href: '#i-pc', x: '10', y: '10', width: '24', height: '24', color: '#04101f' })); sv.append(pc);
    box.append(sv);
  }
  function empty(title, text, action) { return h('div', { class: 'empty' }, h('strong', { text: title }), h('p', { text }), action || null); }
  function discoverAndOpen() { go('devices'); setTimeout(() => $('#fabric-discover').click(), 30); }

  // ---------------- devices ----------------
  function deviceCard(d, compact) {
    const g = grantOf(d.key), caps = deviceCaps(d), avail = caps.filter(c => c.state === 'available').length;
    const status = g === 'control' ? ['Connected', 'ok'] : g === 'read' ? ['Read-only', 'info'] : g === 'observe' ? ['Detected', 'muted'] : ['Offline', 'off'];
    const via = [...new Set(linksOf(d.key).map(l => l.transport))].join(' · ');
    const card = h('button', { class: 'dcard' + (st.selected === d.key ? ' selected' : ''), type: 'button', 'aria-pressed': st.selected === d.key ? 'true' : 'false', dataset: { key: d.key }, onclick: () => compact ? go('devices', d.key) : selectDevice(d.key) },
      h('span', { class: 'dicon cat-' + d.category }, icon(ICON[d.category] || 'unknown')),
      h('span', { class: 'dbody' }, h('strong', { text: label(d) }), h('small', { text: catLabel(d.category) })),
      h('span', { class: 'dstatus ' + status[1] }, h('i', { 'aria-hidden': 'true' }), status[0]),
      compact ? null : h('span', { class: 'dmeta' }, h('span', { text: via || '—' }), h('span', { text: avail ? `${avail} capabilit${avail > 1 ? 'ies' : 'y'} ready` : (caps[0] ? STATE_TXT[caps[0].state] : '') })));
    return card;
  }
  function renderDevices() {
    const grid = $('#device-grid'); grid.replaceChildren();
    const groups = $('#device-groups');
    const sn = st.snap;
    const counts = {};
    for (const d of sn ? sn.devices : []) { const k = groupOf(d); counts[k] = (counts[k] || 0) + 1; }
    groups.replaceChildren(...[['all', 'All'], ['connected', 'Connected'], ['phones', 'Phones & watches'], ['screens', 'TVs & media'], ['home', 'Home & network'], ['bluetooth', 'Bluetooth'], ['other', 'Other']].filter(([k]) => k === 'all' || k === 'connected' || counts[k]).map(([k, t]) => h('button', { type: 'button', class: 'seg-btn' + (st.group === k ? ' active' : ''), 'aria-pressed': st.group === k ? 'true' : 'false', onclick: () => { st.group = k; renderDevices(); } }, t)));
    if (!sn) { grid.append(empty('Nothing discovered yet', 'Press “Discover my environment”. OpenBridge does a bounded, read-only look at your network and connected devices.', null)); return; }
    const q = st.filter.toLowerCase();
    const shown = sn.devices.filter(d => (st.group === 'all' || (st.group === 'connected' ? grantOf(d.key) === 'control' || grantOf(d.key) === 'read' : groupOf(d) === st.group))
      && (!q || [label(d), catLabel(d.category), ...deviceCaps(d).map(c => c.name)].join(' ').toLowerCase().includes(q)));
    const order = { control: 0, read: 1, observe: 2, none: 3 };
    shown.sort((a, b) => order[grantOf(a.key)] - order[grantOf(b.key)] || label(a).localeCompare(label(b)));
    for (const d of shown) grid.append(deviceCard(d, false));
    if (!shown.length) grid.append(empty('No device matches', 'Clear the filter to see everything.', null));
    if (st.selected && !sn.devices.some(d => d.key === st.selected)) st.selected = null;
    if (st.selected) renderInspectorHead(sn.devices.find(d => d.key === st.selected));
  }
  function groupOf(d) { return d.category === 'ble' ? 'bluetooth' : ['phone', 'watch', 'android', 'apple'].includes(d.category) ? 'phones' : ['tv', 'media'].includes(d.category) ? 'screens' : ['router', 'vacuum', 'iot', 'hub', 'network'].includes(d.category) ? 'home' : 'other'; }
  function selectDevice(key) {
    if (!st.snap) return;
    const d = st.snap.devices.find(x => x.key === key); if (!d) return;
    st.selected = key;
    for (const c of $$('.dcard')) { const on = c.dataset.key === key; c.classList.toggle('selected', on); c.setAttribute('aria-pressed', on ? 'true' : 'false'); }
    inSelect = true; try { showDevice(d, linksOf(key)); } finally { inSelect = false; }
    renderInspectorHead(d);
    setTab('overview');
    $('#device-inspector').classList.add('open');
  }
  function renderInspectorHead(d) {
    if (!d) return;
    const g = grantOf(d.key);
    const head = h('div', { class: 'ihead' },
      h('button', { class: 'icon-btn back', type: 'button', 'aria-label': 'Back to devices', onclick: () => $('#device-inspector').classList.remove('open') }, '‹'),
      h('span', { class: 'dicon big cat-' + d.category }, icon(ICON[d.category] || 'unknown')),
      h('div', {}, h('h2', { text: label(d) }), h('p', { class: 'sub', text: `${catLabel(d.category)} · ${g === 'control' ? 'connected, consent-gated control' : g === 'read' ? 'connected, read-only' : 'detected only'}` })),
      h('div', { class: 'chips' }, ...[...new Set(linksOf(d.key).map(l => l.transport))].map(t => h('span', { class: 'chip', text: t }))));
    $('#device-head').replaceChildren(head);
    $('#device-tabs').hidden = false;
    const ov = $('#device-overview'); ov.replaceChildren();
    const caps = deviceCaps(d);
    const grid = h('div', { class: 'cap-grid' });
    for (const c of caps) {
      const card = h('div', { class: 'cap ' + c.state }, h('div', { class: 'cap-top' }, icon(c.icon), h('strong', { text: c.name }), h('span', { class: 'pill ' + c.state, text: STATE_TXT[c.state] })), h('p', { text: c.plain }), h('details', {}, h('summary', { text: 'Technical details' }), h('code', { text: c.tech })));
      if (c.state === 'available' && ['remote', 'touch', 'apps', 'settings', 'diag', 'visual', 'vac-status', 'vac-settings', 'vac-drive', 'pc-diag', 'pc-job', 'router-diag', 'ble'].includes(c.id)) card.append(h('button', { class: 'ghost small', type: 'button', onclick: () => setTab('controls') }, 'Use'));
      if (c.action === 'connect') card.append(h('button', { class: 'ghost small', type: 'button', onclick: () => openConnect(c.connectType) }, 'How to connect'));
      grid.append(card);
    }
    ov.append(grid);
    if (isAndroid(d) && adbLinked(d)) ov.append(h('button', { class: 'ghost small probe', type: 'button', onclick: e => probe(d, e.currentTarget) }, 'Check what this device supports now'));
  }
  async function probe(d, btn) {
    btn.disabled = true; btn.textContent = 'Checking (read-only)…';
    try {
      const r = await post('/api/v2/execute', { primitive_id: 'device_capabilities', device_key: d.key, params: {} });
      const a = (r.result || {}).actions || {};
      const out = h('div', { class: 'probe-out' }, h('strong', { text: `Measured now (${r.state})` }), h('ul', {}, ...Object.entries(a).map(([k, v]) => h('li', { text: `${k}: ${Array.isArray(v) ? v.length + ' keys' : v ? 'yes' : 'no'}` }))), r.result && r.result.launchable_apps !== undefined ? h('small', { text: `${r.result.launchable_apps} launchable apps · screen ${(r.result.screen_px || []).join('×')}` }) : null);
      btn.replaceWith(out);
    } catch (e) { btn.disabled = false; btn.textContent = 'Check failed: ' + e.message; }
  }
  function setTab(tab) {
    for (const b of $$('#device-tabs [role=tab]')) b.setAttribute('aria-selected', b.dataset.tab === tab ? 'true' : 'false');
    $('#device-overview').hidden = tab !== 'overview';
    $('#fabric-detail').hidden = tab !== 'controls';
  }

  // ---------------- skills ----------------
  function renderSkills() {
    const grid = $('#skill-grid'); grid.replaceChildren();
    $('#skill-legend').replaceChildren(h('span', { class: 'muted', text: 'Lifecycle (what was proven) and availability (what works right now) are shown separately.' }));
    for (const k of skills()) {
      const card = h('article', { class: 'skill' },
        h('div', { class: 'skill-top' }, h('span', { class: 'sicon' }, icon(k.icon)), h('div', {}, h('h3', { text: k.name }), h('p', { text: k.plain }))),
        h('div', { class: 'badges' }, h('span', { class: 'pill ' + (k.lifecycle === 'Verified' ? 'available' : 'planned'), text: k.lifecycle }), h('span', { class: 'pill ' + (k.availability === 'Ready' ? 'available' : (k.availability === 'Offline' || k.availability === 'Not checked yet') ? 'detected' : 'permission'), text: k.availability })),
        h('dl', {},
          h('dt', { text: 'Provided by' }), h('dd', {}, k.providers.length ? k.providers.map(p => h('button', { class: 'chip link', type: 'button', onclick: () => p.key === 'pc' ? null : go('devices', p.key) }, p.label === 'This PC' || p.key === 'pc' ? p.label : label(p))) : h('span', { class: 'muted', text: 'No provider in the current graph' })),
          h('dt', { text: 'Used by' }), h('dd', { text: k.consumers.join(', ') }),
          h('dt', { text: 'Evidence' }), h('dd', { text: k.evidence })),
        k.limits ? h('p', { class: 'limits', text: k.limits }) : null,
        k.needs ? h('p', { class: 'limits', text: k.needs }) : null,
        k.routeNote ? h('p', { class: 'route-note', text: k.routeNote }) : null,
        h('div', { class: 'skill-actions' },
          k.providers[0] && k.providers[0].key !== 'pc' ? h('button', { class: 'ghost small', type: 'button', onclick: () => { go('devices', k.providers[0].key); setTimeout(() => setTab('controls'), 60); } }, 'Use') : null,
          k.route ? h('button', { class: 'ghost small', type: 'button', onclick: () => { st.graphSkill = 'bluetooth'; go('fabric'); } }, 'See route') : null,
          k.id === 'identify' ? h('button', { class: 'ghost small', type: 'button', onclick: () => openConnect() }, 'Connect device') : null,
          k.id === 'voice' ? h('button', { class: 'ghost small', type: 'button', onclick: openAssistant }, 'Open assistant') : null));
      grid.append(card);
    }
  }

  // ---------------- teach a skill (honest wizard over real primitives) ----------------
  function openTeach() {
    const dlg = h('dialog', { class: 'modal wide', 'aria-labelledby': 'teach-title' });
    const body = h('div', { class: 'teach' });
    const steps = ['Device', 'Describe', 'Investigate', 'Compatibility', 'Test', 'Verify', 'Publish'];
    const rail = h('ol', { class: 'steps' }, ...steps.map((t, i) => h('li', { dataset: { i } }, h('b', { text: i + 1 }), t)));
    dlg.append(h('div', { class: 'modal-head' }, h('h2', { id: 'teach-title', text: 'Teach a new skill' }), h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Close', onclick: () => dlg.close() }, icon('close'))), rail, body);
    dlg.addEventListener('close', () => dlg.remove());
    document.body.append(dlg); dlg.showModal();
    const state = { device: null, text: '', probe: null, intent: null, action: null };
    const mark = i => { for (const li of $$('li', rail)) { li.classList.toggle('done', Number(li.dataset.i) < i); li.classList.toggle('on', Number(li.dataset.i) === i); } };
    const nav = (back, next, nextLabel, nextOk = true) => h('div', { class: 'wizard-nav' }, back ? h('button', { class: 'ghost', type: 'button', onclick: back }, 'Back') : h('span'), next ? h('button', { class: 'primary', type: 'button', disabled: !nextOk, onclick: next }, nextLabel || 'Continue') : null);
    const step1 = () => {
      mark(0);
      const devs = st.snap ? st.snap.devices.filter(d => grantOf(d.key) !== 'observe') : [];
      body.replaceChildren(h('h3', { text: 'Which device should learn?' }), devs.length ? h('div', { class: 'card-row' }, ...devs.map(d => { const c = deviceCard(d, true); c.onclick = () => { state.device = d; step2(); }; return c; })) : empty('No connected device', 'Discover or connect a device first.', h('button', { class: 'primary', type: 'button', onclick: () => { dlg.close(); openConnect(); } }, 'Connect device')));
    };
    const step2 = () => {
      mark(1);
      const ta = h('textarea', { rows: '3', maxlength: '300', placeholder: `e.g. “Turn the volume down on ${label(state.device)} when I say so”` });
      ta.value = state.text;
      body.replaceChildren(h('h3', { text: `What should ${label(state.device)} learn to do?` }), ta, nav(step1, () => { state.text = ta.value.trim(); if (state.text) step3(); }, 'Investigate'));
      ta.focus();
    };
    const step3 = async () => {
      mark(2);
      const log = h('ul', { class: 'checks' });
      body.replaceChildren(h('h3', { text: 'OpenBridge investigates' }), log);
      const line = (t, cls) => { const li = h('li', { class: cls || '', text: t }); log.append(li); return li; };
      line('Reading current device facts and grants…', 'run');
      line(`Grant: ${grantOf(state.device.key)} · transports: ${[...new Set(linksOf(state.device.key).map(l => l.transport))].join(', ') || 'none'}`, 'ok');
      if (isAndroid(state.device) && adbLinked(state.device)) {
        const li = line('Measuring supported actions on the device (read-only)…', 'run');
        try { const r = await post('/api/v2/execute', { primitive_id: 'device_capabilities', device_key: state.device.key, params: {} }); state.probe = (r.result || {}).actions || null; li.className = 'ok'; li.textContent = `Measured ${Object.keys(state.probe || {}).length} action families (${r.state}).`; } catch (e) { li.className = 'bad'; li.textContent = 'Measurement failed: ' + e.message; }
      } else line('No live measurement available for this device type; using its declared capabilities.', 'warn');
      const li2 = line('Matching your request to known, typed intents…', 'run');
      try { state.intent = await post('/api/v2/voice/intent', { text: state.text }); li2.className = state.intent.intent ? 'ok' : 'warn'; li2.textContent = state.intent.intent ? `Closest known intent: ${state.intent.says || state.intent.intent}` : `No typed intent matched: ${state.intent.reason}`; } catch (e) { li2.className = 'bad'; li2.textContent = e.message; }
      line('Searching manufacturer documentation: not available yet in OpenBridge (planned). Nothing was invented.', 'warn');
      body.append(nav(step2, step4, 'Review compatibility'));
    };
    const step4 = () => {
      mark(3);
      const caps = deviceCaps(state.device);
      const can = caps.filter(c => c.state === 'available'), cannot = caps.filter(c => c.state !== 'available');
      const pick = h('select', { 'aria-label': 'Action to test' });
      const opts = [];
      if (isAndroid(state.device) && adbLinked(state.device)) opts.push(['key:volume_down', 'Press volume down'], ['key:home', 'Press Home'], ['get:media_volume', 'Read media volume (read-only)'], ['screen_state', 'Read screen state (read-only)']);
      for (const [v, t] of opts) pick.append(h('option', { value: v, text: t }));
      body.replaceChildren(h('h3', { text: 'What is possible' }), h('div', { class: 'two-col' }, h('div', {}, h('h4', { text: 'Works with this device' }), h('ul', {}, ...can.map(c => h('li', { text: c.name })))), h('div', {}, h('h4', { text: 'Not possible or needs a step' }), h('ul', {}, ...cannot.map(c => h('li', { text: `${c.name} — ${STATE_TXT[c.state]}` }))))),
        opts.length ? h('label', { class: 'field' }, 'Safe first test', pick) : h('p', { class: 'muted', text: 'No safe test action is available for this device type yet; use its controls page.' }),
        nav(step3, opts.length ? () => { state.action = pick.value; step5(); } : null, 'Test it'));
    };
    const step5 = () => {
      mark(4);
      const [action, arg] = state.action.split(':');
      const args = action === 'key' ? { key: arg } : action === 'get' ? { setting: arg } : {};
      const consent = h('input', { type: 'checkbox', id: 'teach-consent' });
      const out = h('p', { role: 'status' });
      const run = h('button', { class: 'primary', type: 'button', disabled: true, onclick: async () => {
        run.disabled = true; consent.checked = false; consent.disabled = true;
        try { const r = await post('/api/v2/execute', { primitive_id: 'device_action', device_key: state.device.key, params: { action, args }, consent: true }); state.receipt = r; step6(); }
        catch (e) { out.textContent = 'Blocked: ' + e.message; consent.disabled = false; }
      } }, 'Run this one test');
      consent.addEventListener('change', () => { run.disabled = !consent.checked; });
      body.replaceChildren(h('h3', { text: 'Test safely' }), h('p', { text: `OpenBridge will run exactly one action on ${label(state.device)}: ${state.action.replace(':', ' ')}.` }), h('label', { class: 'transaction-consent' }, consent, ' I own this device and approve this single action.'), run, out, nav(step4, null));
    };
    const step6 = () => {
      mark(5);
      const r = state.receipt;
      body.replaceChildren(h('h3', { text: 'Verification' }), h('div', { class: 'receipt' }, h('p', {}, h('strong', { text: r.state }), r.verified ? ' · independently read back' : ' · momentary action: no lasting value to read back'), h('code', { text: `receipt ${r.transaction_id}` }), r.result && Object.keys(r.result).length ? h('pre', { text: JSON.stringify(r.result, null, 1).slice(0, 600) }) : null), nav(step5, step7, 'Publish'));
    };
    const step7 = () => {
      mark(6);
      body.replaceChildren(h('h3', { text: 'Publish & share' }), h('p', { text: 'Saving a learned skill and pushing its controls to other devices (Companions, watch) needs the routing contract (B2) and the Companion command path (B3). They are not implemented yet, so OpenBridge does not pretend to publish.' }),
        h('p', { text: 'What you can do today: turn the tested actions into a sequence on this device.' }),
        h('div', { class: 'wizard-nav' }, h('button', { class: 'ghost', type: 'button', onclick: () => dlg.close() }, 'Close'), h('button', { class: 'primary', type: 'button', onclick: () => { dlg.close(); st.macroDevice = state.device.key; go('automations'); } }, 'Build a sequence')));
    };
    step1();
  }

  // ---------------- fabric graph ----------------
  const view = { x: 0, y: 0, w: 1000, h: 600 };
  function graphModel() {
    const sn = st.snap; if (!sn) return { nodes: [], edges: [] };
    const nodes = [{ id: 'pc', label: 'This PC', kind: 'pc', cat: 'computer', x: 90, y: 300 }], edges = [];
    const skill = st.graphSkill;
    const direct = sn.devices.filter(d => sn.links.some(l => l.parent === 'pc' && l.child === d.key));
    const indirect = sn.devices.filter(d => !direct.includes(d));
    const relayDevs = direct.filter(d => capOf(d, 'ble_relay'));
    const focus = skill === 'bluetooth' ? new Set([...relayDevs.map(d => d.key), ...indirect.filter(d => d.category === 'ble').map(d => d.key)]) : null;
    const col1 = skill === 'bluetooth' ? 560 : 430, col2 = skill === 'bluetooth' ? 860 : 800;
    let order = direct;
    if (skill === 'bluetooth') { const rest = direct.filter(d => !relayDevs.includes(d)), half = Math.floor(rest.length / 2); order = [...rest.slice(0, half), ...relayDevs, ...rest.slice(half)]; }
    order.forEach((d, i) => nodes.push({ id: d.key, label: label(d), kind: 'device', cat: d.category, x: col1, y: 60 + i * (480 / Math.max(order.length - 1, 1)), dim: focus && !focus.has(d.key), grant: grantOf(d.key) }));
    indirect.forEach((d, i) => nodes.push({ id: d.key, label: label(d), kind: 'device', cat: d.category, x: col2, y: 120 + i * (360 / Math.max(indirect.length - 1, 1)), dim: focus && !focus.has(d.key), grant: grantOf(d.key) }));
    if (skill === 'bluetooth') {
      nodes.push({ id: 'skill:ble', label: 'Bluetooth Bridge', sub: 'skill · BLE scan', kind: 'skill', x: 300, y: 300 });
      edges.push({ from: 'pc', to: 'skill:ble', kind: 'skill' });
      for (const d of relayDevs) { const r = st.routes.find(x => x.relay_device === d.key || x.device_key === d.key); const cap = capOf(d, 'ble_relay'); const state = r ? r.status : cap.status === 'REAL_HARDWARE_VERIFIED' ? 'VERIFIED' : 'NOT_PAIRED'; edges.push({ from: 'skill:ble', to: d.key, kind: 'provider', state }); const nn = nodes.find(n => n.id === d.key); if (nn) nn.sub = 'BLE provider · ' + (ROUTE_TXT[state] || state).toLowerCase(); }
      for (const d of direct.filter(d => !relayDevs.includes(d))) edges.push({ from: 'pc', to: d.key, kind: 'link', grant: grantOf(d.key), dim: true });
    } else for (const d of direct) edges.push({ from: 'pc', to: d.key, kind: 'link', grant: grantOf(d.key), transport: [...new Set(linksOf(d.key).map(l => l.transport))].join('·') });
    for (const l of sn.links.filter(l => l.parent !== 'pc')) edges.push({ from: l.parent, to: l.child, kind: 'ble', grant: 'observe', transport: l.transport, dim: focus && !focus.has(l.child) });
    return { nodes, edges };
  }
  function renderGraph() {
    const sel = $('#graph-skill');
    if (sel.options.length < 2) sel.append(h('option', { value: 'bluetooth', text: 'Bluetooth Bridge' }));
    sel.value = st.graphSkill;
    const svg = $('#graph-svg'); svg.replaceChildren();
    const list = $('#graph-list');
    const { nodes, edges } = graphModel();
    const byId = new Map(nodes.map(n => [n.id, n]));
    if (!nodes.length) { svg.append(s('text', { x: '500', y: '300', 'text-anchor': 'middle', class: 'g-empty' }, 'Run discovery in My Devices to draw your device fabric')); }
    const defs = s('defs');
    const lg = s('linearGradient', { id: 'edge-skill', x1: '0', x2: '1' }); lg.append(s('stop', { offset: '0', 'stop-color': '#22d3ee' }), s('stop', { offset: '1', 'stop-color': '#a78bfa' })); defs.append(lg); svg.append(defs);
    const eg = s('g', { class: 'edges' }), ng = s('g', { class: 'nodes' });
    for (const e of edges) {
      const a = byId.get(e.from), b = byId.get(e.to); if (!a || !b) continue;
      const mx = (a.x + b.x) / 2;
      const p = s('path', { d: `M${a.x} ${a.y} C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x} ${b.y}`, class: `edge ${e.kind} g-${e.grant || ''} r-${(e.state || '').toLowerCase()}${e.dim ? ' dim' : ''}` });
      eg.append(p);
    }
    for (const n of nodes) {
      const g = s('g', { class: `node ${n.kind} cat-${n.cat || ''}${n.dim ? ' dim' : ''}${st.graphSel === n.id ? ' sel' : ''}`, transform: `translate(${n.x} ${n.y})`, tabindex: '0', role: 'button', 'aria-label': `${n.label}${n.kind === 'device' ? ', ' + catLabel(n.cat) : ''}` });
      const w = n.kind === 'skill' ? 190 : n.kind === 'pc' ? 120 : n.sub ? 230 : 190;
      g.append(s('rect', { x: String(-w / 2), y: '-22', width: String(w), height: '44', rx: '12' }));
      g.append(s('use', { href: '#i-' + (n.kind === 'skill' ? 'ble' : n.kind === 'pc' ? 'pc' : ICON[n.cat] || 'unknown'), x: String(-w / 2 + 10), y: '-10', width: '20', height: '20' }));
      g.append(s('text', { x: String(-w / 2 + 38), y: n.sub ? '-2' : '5' }, n.label.length > 20 ? n.label.slice(0, 19) + '…' : n.label));
      if (n.sub) g.append(s('text', { x: String(-w / 2 + 38), y: '13', class: 'node-sub' }, n.sub));
      if (n.grant) g.append(s('circle', { cx: String(w / 2 - 12), cy: '0', r: '4', class: 'gdot g-' + n.grant }));
      const pick = () => { st.graphSel = n.id; inspectNode(n); for (const x of $$('.node', svg)) x.classList.remove('sel'); g.classList.add('sel'); };
      g.addEventListener('click', pick); g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); } });
      ng.append(g);
    }
    svg.append(eg, ng);
    fitGraph(nodes);
    list.replaceChildren(h('table', { class: 'tbl' }, h('thead', {}, h('tr', {}, h('th', { text: 'From' }), h('th', { text: 'To' }), h('th', { text: 'Route' }), h('th', { text: 'Grant / state' }))), h('tbody', {}, ...edges.map(e => h('tr', {}, h('td', { text: (byId.get(e.from) || {}).label }), h('td', { text: (byId.get(e.to) || {}).label }), h('td', { text: e.kind === 'provider' ? 'skill provider' : e.transport || e.kind }), h('td', { text: e.state ? ROUTE_TXT[e.state] || e.state : e.grant || '' }))))));
    renderRoutePanel();
  }
  const ROUTE_TXT = { FRESH: 'Live · fresh', STALE: 'Stale', OFFLINE: 'Offline', NEVER_SUCCEEDED: 'Paired, no scan yet', VERIFIED: 'Verified provider', NOT_PAIRED: 'Needs Companion' };
  function fitGraph(nodes) {
    if (!nodes.length) { Object.assign(view, { x: 0, y: 0, w: 1000, h: 600 }); }
    else { const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y); const x0 = Math.min(...xs) - 120, x1 = Math.max(...xs) + 120, y0 = Math.min(...ys) - 60, y1 = Math.max(...ys) + 60; Object.assign(view, { x: x0, y: y0, w: x1 - x0, h: Math.max(y1 - y0, 300) }); }
    applyView();
  }
  function applyView() { $('#graph-svg').setAttribute('viewBox', `${view.x} ${view.y} ${view.w} ${view.h}`); }
  function zoom(f) { const cx = view.x + view.w / 2, cy = view.y + view.h / 2; view.w *= f; view.h *= f; view.x = cx - view.w / 2; view.y = cy - view.h / 2; applyView(); }
  function inspectNode(n) {
    const box = $('#graph-inspector'); box.replaceChildren();
    if (n.kind === 'pc') { box.append(h('h3', { text: 'This PC' }), h('p', { text: 'Runs OpenBridge, orchestrates every route and enforces consent. It has no Bluetooth radio of its own in the reference setup; Bluetooth comes from relays.' })); return; }
    if (n.kind === 'skill') { box.append(h('h3', { text: 'Bluetooth Bridge' }), h('p', { text: 'Skill provided by relay-capable Android devices. Each relay scans for this PC; scanning is not connecting.' }), h('p', { class: 'muted', text: 'Automatic / pinned provider selection arrives with the routing contract (B2). Today you choose the relay when you scan, on the device page.' })); return; }
    const d = st.snap.devices.find(x => x.key === n.id); if (!d) return;
    const caps = deviceCaps(d);
    box.append(h('div', { class: 'ihead small' }, h('span', { class: 'dicon cat-' + d.category }, icon(ICON[d.category] || 'unknown')), h('div', {}, h('h3', { text: label(d) }), h('p', { class: 'sub', text: catLabel(d.category) }))),
      h('dl', {}, h('dt', { text: 'Connection' }), h('dd', { text: linksOf(d.key).map(l => `${l.transport} (${l.grants.join('/')})`).join(', ') || '—' }), h('dt', { text: 'Grant' }), h('dd', { text: grantOf(d.key) })),
      h('ul', { class: 'mini-caps' }, ...caps.map(c => h('li', {}, h('span', { class: 'pill ' + c.state, text: STATE_TXT[c.state] }), ' ', c.name))),
      h('button', { class: 'ghost small', type: 'button', onclick: () => go('devices', d.key) }, 'Open device'));
  }
  function renderRoutePanel() {
    const box = $('#route-panel'); box.replaceChildren();
    if (st.graphSkill !== 'bluetooth' || !st.snap) return;
    const relays = st.snap.devices.filter(d => capOf(d, 'ble_relay'));
    box.append(h('h2', { text: 'Bluetooth providers' }), h('p', { class: 'sub', text: 'This PC uses a relay to find Bluetooth devices. A relay can only replace another for the same operation (BLE scan); scanning, connecting (GATT), audio and file transfer are different capabilities.' }));
    const grid = h('div', { class: 'route-grid' });
    for (const d of relays) {
      const r = st.routes.find(x => x.relay_device === d.key || x.device_key === d.key), c = capOf(d, 'ble_relay');
      const state = r ? r.status : c.status === 'REAL_HARDWARE_VERIFIED' ? 'VERIFIED' : 'NOT_PAIRED';
      grid.append(h('div', { class: 'route ' + state.toLowerCase() }, icon(ICON[d.category]), h('div', {}, h('strong', { text: label(d) }), h('small', { text: ROUTE_TXT[state] || state })), h('button', { class: 'ghost small', type: 'button', onclick: () => { go('devices', d.key); setTimeout(() => setTab('controls'), 60); } }, 'Scan with this relay')));
    }
    if (!relays.length) grid.append(empty('No relay-capable device', 'Install the OpenBridge Companion on an Android phone or TV to give this PC Bluetooth reach.', h('button', { class: 'ghost small', type: 'button', onclick: () => openConnect() }, 'Connect a phone')));
    const src = h('div', { class: 'seg', role: 'group', 'aria-label': 'Bluetooth source' }, h('button', { type: 'button', class: 'seg-btn', disabled: true, title: 'Needs the B2 route-truth contract (not implemented yet)' }, 'Automatic · planned'), ...relays.map(d => h('button', { type: 'button', class: 'seg-btn', onclick: () => { go('devices', d.key); setTimeout(() => setTab('controls'), 60); } }, 'Use ' + label(d))));
    box.append(h('div', { class: 'route-source' }, h('span', { class: 'sub', text: 'Source' }), src), grid, h('p', { class: 'muted', text: 'Today you pick the relay for each scan. Automatic selection and failover arrive with the B2 routing contract, and only between relays that support the same operation. Non-repeatable commands are never replayed on another route.' }));
  }

  // ---------------- automations ----------------
  function renderAutomations() {
    const mb = $('#macro-builder'); mb.replaceChildren();
    const devs = st.snap ? st.snap.devices.filter(d => isAndroid(d) && adbLinked(d) && grantOf(d.key) === 'control') : [];
    if (!devs.length) mb.append(empty('No controllable Android device', 'Connect a phone, TV or watch to build sequences.', h('button', { class: 'ghost small', type: 'button', onclick: () => openConnect() }, 'Connect device')));
    else {
      const sel = h('select', { 'aria-label': 'Device' }, ...devs.map(d => h('option', { value: d.key, text: label(d) })));
      if (st.macroDevice && devs.some(d => d.key === st.macroDevice)) sel.value = st.macroDevice;
      const rows = h('ol', { class: 'macro-steps' });
      const KEYS = ['home', 'back', 'ok', 'up', 'down', 'left', 'right', 'volume_up', 'volume_down', 'mute', 'play_pause', 'power', 'wakeup', 'sleep', 'channel_up', 'channel_down'];
      const addRow = (action = 'key', arg = 'home') => {
        const a = h('select', { 'aria-label': 'Action' }, ...[['key', 'Press key'], ['launch_app', 'Open app (package)'], ['open_url', 'Open web address'], ['text', 'Type text'], ['wait', 'Wait (ms)']].map(([v, t]) => h('option', { value: v, text: t })));
        a.value = action;
        const arg1 = h('input', { 'aria-label': 'Value', value: arg, list: 'macro-keys' });
        const del = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Remove step', onclick: () => { li.remove(); consent.checked = false; sync(); } }, '×');
        const li = h('li', {}, a, arg1, del); rows.append(li);
        for (const x of [a, arg1]) x.addEventListener('input', () => { consent.checked = false; sync(); });
      };
      const consent = h('input', { type: 'checkbox' });
      const summary = h('p', { class: 'muted' });
      const out = h('div', { role: 'status' });
      const steps = () => $$('li', rows).map(li => { const [a, v] = [$('select', li).value, $('input', li).value.trim()]; const args = a === 'key' ? { key: v } : a === 'launch_app' ? { package: v } : a === 'open_url' ? { url: v } : a === 'text' ? { text: v } : { ms: Math.min(10000, Math.max(0, parseInt(v, 10) || 0)) }; return { action: a, args }; });
      const run = h('button', { class: 'primary', type: 'button', disabled: true });
      const sync = () => { const n = $$('li', rows).length; summary.textContent = n ? `${n} step(s) on ${sel.selectedOptions[0].textContent}: ` + steps().map(x => `${x.action} ${Object.values(x.args)[0]}`).join(' → ') : 'Add at least one step.'; run.textContent = 'Run this sequence once'; run.disabled = !consent.checked || !n || n > 20; };
      consent.addEventListener('change', sync); sel.addEventListener('change', () => { consent.checked = false; sync(); });
      run.addEventListener('click', async () => {
        run.disabled = true; const plan = steps(); consent.checked = false;
        try { const r = await post('/api/v2/execute', { primitive_id: 'device_macro', device_key: sel.value, params: { steps: plan }, consent: true });
          out.replaceChildren(h('p', {}, h('strong', { text: r.state }), ` · receipt ${r.transaction_id}`), h('ol', {}, ...((r.result || {}).steps || []).map(x => h('li', { class: x.error ? 'bad' : 'ok', text: `${x.action}${x.error ? ' — ' + x.error : ''}` })))); }
        catch (e) { out.textContent = 'Blocked: ' + e.message; } finally { sync(); }
      });
      addRow('key', 'home'); addRow('wait', '800'); addRow('key', 'volume_down');
      mb.append(h('datalist', { id: 'macro-keys' }, ...KEYS.map(k => h('option', { value: k }))), h('label', { class: 'field' }, 'Device', sel), rows, h('button', { class: 'ghost small', type: 'button', onclick: () => { addRow(); sync(); } }, '+ Add step'), summary, h('label', { class: 'transaction-consent' }, consent, ' I approve exactly these steps, once. Key presses cannot be undone.'), run, out);
      sync();
    }
    const flows = $('#flows'); flows.replaceChildren();
    for (const [t, steps, why] of [['Watch button → TV remote', ['Watch button pressed', 'This PC authorizes', 'TV receives the key', 'TV state read back'], 'Needs the Companion command path on the watch (B3).'], ['Diagnose the TV', ['Collect TV + router facts', 'Build the timeline', 'Meta ranks explanations (optional, consented)', 'Suggest one read-only check'], 'Available manually today from the TV page (“Why did it disconnect?”).'], ['Low battery → dock the vacuum', ['Watch battery level', 'Threshold crossed', 'Ask before sending “dock”'], 'Watchers exist; chaining a watcher to an action is deliberately not allowed yet.']])
      flows.append(h('div', { class: 'flow' }, h('strong', { text: t }), h('ol', { class: 'flow-steps' }, ...steps.map(x => h('li', { text: x }))), h('small', { text: why })));
    const comp = $('#compute'); comp.replaceChildren();
    const m = st.model || {};
    comp.append(h('div', { class: 'node-row' }, icon('pc'), h('div', {}, h('strong', { text: 'This PC' }), h('small', { text: m.inference_available ? `${m.model_id} · ${m.inference_mode}` : 'Meta model not running (start with --local-meta)' })), h('span', { class: 'pill ' + (m.inference_available ? 'available' : 'detected'), text: m.inference_available ? 'Ready' : 'Idle' })));
    for (const d of (st.snap ? st.snap.devices.filter(d => d.category === 'computer') : [])) comp.append(h('div', { class: 'node-row' }, icon('pc'), h('div', {}, h('strong', { text: label(d) }), h('small', { text: capOf(d, 'windows_diagnostics') ? 'Agent connected · runs owner commands; not a model worker unless it serves Ollama' : 'Detected only' })), h('span', { class: 'pill ' + (capOf(d, 'windows_diagnostics') ? 'available' : 'detected'), text: capOf(d, 'windows_diagnostics') ? 'Commands' : 'Detected' })));
    comp.append(h('p', { class: 'muted', text: 'Work is assigned per task to one machine. Different CPUs and GPUs are not merged into one faster processor.' }));
  }

  // ---------------- activity ----------------
  function renderActivity() {
    const ol = $('#activity-timeline'); ol.replaceChildren();
    const ev = st.events.filter(e => e.kind !== 'started').slice(-80).reverse();
    if (!ev.length) ol.append(h('li', { class: 'muted', text: 'No operation in this session yet. Real operations appear here with their receipt; the simulated sandbox is labelled separately.' }));
    for (const e of ev) ol.append(timelineItem(e));
    const rec = st.recovery || {};
    const pend = (rec.pending_transactions || []).length, open = (rec.open_session_changes || []).length;
    $('#recovery-tag').textContent = pend ? `${pend} operation(s) need recovery` : open ? `${open} session change(s) to restore` : 'Nothing to recover';
    $('#recovery-tag').className = 'tag ' + (pend ? 'warn' : 'ok');
  }

  // ---------------- connect wizard ----------------
  const TYPES = [['phone', 'Phone or tablet', 'phone'], ['watch', 'Smartwatch', 'watch'], ['tv', 'TV', 'tv'], ['pc', 'Windows / Linux PC', 'pc'], ['router', 'Internet box / router', 'router'], ['vacuum', 'Robot vacuum', 'vacuum'], ['iphone', 'iPhone / iPad', 'apple'], ['unknown', 'Something else', 'unknown']];
  async function openConnect(type) {
    const dlg = $('#connect');
    if (!dlg.open) dlg.showModal();
    const nav = $('#connect-types');
    nav.replaceChildren(h('button', { type: 'button', class: 'ctype' + (!type ? ' on' : ''), onclick: () => openConnect() }, icon('search'), 'Found on my network'), ...TYPES.map(([k, t, ic]) => h('button', { type: 'button', class: 'ctype' + (type === k ? ' on' : ''), onclick: () => openConnect(k) }, icon(ic), t)));
    const main = $('#connect-main'); main.replaceChildren();
    if (!type) return renderCandidates(main);
    guideFor(type, main);
  }
  async function renderCandidates(main) {
    main.append(h('h3', { text: 'Devices OpenBridge can see' }), h('p', { class: 'sub', text: 'From your last discovery: phones on Wi-Fi (Android wireless debugging, Apple services), PCs from your router’s device list, Bluetooth seen by relays. Nothing new is probed until you press Scan.' }));
    const scan = h('button', { class: 'primary small', type: 'button', onclick: async () => { scan.disabled = true; scan.textContent = 'Scanning (read-only)…'; try { await post('/api/fabric-discover', { device_id: 'fabric', providers: ['mdns', 'ssdp', 'android', 'freebox'] }).then(s2 => { renderFabric(s2); }); } catch (e) { toast('Scan blocked: ' + e.message, 'bad'); } openConnect(); } }, 'Scan again');
    main.append(scan);
    let data;
    try { data = await api('/api/v2/onboarding'); } catch (e) { main.append(h('p', { class: 'bad', text: 'Onboarding view unavailable: ' + e.message })); return; }
    if (!data.candidates.length) { main.append(empty(data.discovered ? 'No phone, watch or PC found' : 'No discovery yet', data.discovered ? 'Turn on Wireless debugging on an Android phone or watch, or pick a device type on the left.' : 'Press Scan again, or pick the device type on the left.', null)); return; }
    const list = h('div', { class: 'cand-list' });
    for (const c of data.candidates) list.append(candidateCard(c, data.apk_portal, data.agent_matrix));
    main.append(list);
  }
  const MSTATE = { READY: ['Ready', 'available'], NEEDS_STEP: ['One step on the device', 'permission'], CONNECTED: ['Connected', 'available'], UNAVAILABLE: ['Not available', 'unsupported'] };
  function candidateCard(c, portal, matrix) {
    const ic = c.platform === 'ios/apple' ? 'apple' : ICON[c.kind] || (c.kind === 'phone_maybe' ? 'ble' : 'phone');
    const card = h('article', { class: 'cand' }, h('div', { class: 'cand-head' }, h('span', { class: 'dicon' }, icon(ic)), h('div', {}, h('strong', { text: c.model && c.model !== c.label ? `${c.label} · ${c.model}` : c.label }), h('small', { text: `${c.vendor ? c.vendor + ' · ' : ''}${c.evidence.join(' · ')}${c.confidence === 'weak' ? ' (weak signal)' : ''}` })), h('span', { class: 'pill ' + (c.state === 'CONNECTED' ? 'available' : c.state === 'READY' ? 'available' : 'permission'), text: { CONNECTED: 'Connected', READY: 'Ready to pair', ACTION_NEEDED: 'Needs a step', IDENTIFY: 'Identify' }[c.state] || c.state })));
    const ms = h('div', { class: 'methods' });
    for (const m of c.methods) {
      const [t, cls] = MSTATE[m.status] || [m.status, ''];
      const box = h('details', { class: 'method ' + cls, open: m.status === 'READY' }, h('summary', {}, h('strong', { text: m.title }), h('span', { class: 'pill ' + cls, text: t })), h('p', { class: 'sub', text: m.detail }), m.reason ? h('p', { class: 'bad', text: m.reason }) : null, m.steps.length ? h('ol', {}, ...m.steps.map(x => h('li', { text: x }))) : null);
      if (m.id === 'adb_wifi' && m.status !== 'CONNECTED') box.append(pairForm(c.kind === 'watch' ? 'watch' : 'android', m.pairing_address));
      if (m.id === 'companion_apk' && m.status === 'READY') box.append(h('button', { class: 'ghost small', type: 'button', onclick: async e => { e.currentTarget.disabled = true; try { const r = await post('/api/companion-install', { device_id: (st.snap.devices.find(d => d.key === c.device_key).handles || {}).USB || (st.snap.devices.find(d => d.key === c.device_key).handles || {}).WIFI }); toast(`Companion install: ${r.state || 'started'} — accept the prompt on the phone`); } catch (err) { toast('Install blocked: ' + err.message, 'bad'); } } }, 'Install from this PC'));
      if (m.id === 'companion_apk' && m.status !== 'UNAVAILABLE') box.append(apkPortal(portal));
      if (m.id === 'agent_lan' && m.needs_pick) box.append(agentPicker((matrix || []).filter(e => e.id !== 'android-apk')));
      ms.append(box);
    }
    card.append(ms);
    return card;
  }
  function pairForm(kind, address) {
    const addr = h('input', { 'aria-label': 'Pairing address (IP:port)', placeholder: 'IP:port, e.g. 192.168.1.23:37105', inputmode: 'decimal', value: address || '' });
    const code = h('input', { 'aria-label': '6-digit pairing code', placeholder: '6-digit code', inputmode: 'numeric', maxlength: '6' });
    const out = h('p', { role: 'status' });
    const btn = h('button', { class: 'primary small', type: 'button', onclick: async () => {
      if (!/^\d{6}$/.test(code.value.trim())) { out.textContent = 'Type the 6 digits shown on the device.'; return; }
      btn.disabled = true; out.textContent = 'Pairing with the official adb pairing…';
      try { const r = await post('/api/watch-pair', { device_id: kind, address: addr.value.trim(), code: code.value.trim() });
        out.textContent = r.state === 'AUTHORIZED' ? 'Paired and connected. Running discovery…' : `Result: ${r.state}`;
        if (r.guide) showGuideObject(r.guide);
        if (r.state === 'AUTHORIZED') { const s2 = await post('/api/fabric-discover', { device_id: 'fabric', providers: ['mdns', 'android'] }); renderFabric(s2); toast('Device connected'); }
      } catch (e) { out.textContent = 'Pairing blocked: ' + e.message; } finally { btn.disabled = false; code.value = ''; }
    } }, 'Pair');
    return h('div', { class: 'pair-form' }, addr, code, btn, out);
  }
  function apkPortal(state) {
    const out = h('p', { role: 'status' });
    const show = r => out.replaceChildren(r.running ? h('span', {}, 'On the phone, open ', h('code', { text: r.url }), ` (open for ${Math.round(r.expires_in_s / 60)} min, SHA-256 ${String(r.sha256).slice(0, 12)}…). Android will ask you to allow the install.`) : 'LAN download closed.');
    if (state && state.running) show(state);
    return h('div', { class: 'portal' }, h('button', { class: 'ghost small', type: 'button', onclick: async () => { try { show(await post('/api/v2/onboarding/apk-portal', { minutes: 10 })); } catch (e) { out.textContent = e.message; } } }, 'Open a 10-minute LAN download link'), out);
  }
  function agentPicker(entries) {
    const wrap = h('div', { class: 'agent-picker' });
    if (!entries.length) { wrap.append(h('p', { class: 'bad', text: 'No agent builds known.' })); return wrap; }
    for (const e of entries) {
      const [t, cls] = MSTATE[e.status] || [e.status, ''];
      const row = h('div', { class: 'agent-row' }, h('strong', { text: e.label }), h('span', { class: 'pill ' + cls, text: t }));
      if (e.reason) row.append(h('p', { class: e.sha256 ? 'sub' : 'bad', text: e.reason }));
      if (!e.run && e.install && e.install.length) row.append(h('ol', {}, ...e.install.map(x => h('li', { text: x }))));
      if (e.status === 'READY' || e.sha256) row.append(artifactPortal(e));
      wrap.append(row);
    }
    return wrap;
  }
  function artifactPortal(e) {
    const out = h('p', { role: 'status' });
    const btn = h('button', { class: 'ghost small', type: 'button', onclick: async () => {
      btn.disabled = true;
      try {
        const r = await post('/api/v2/onboarding/apk-portal', { minutes: 10, artifact: e.id });
        const host = new URL(r.url).hostname;
        out.replaceChildren(h('span', {}, 'On that computer, open ', h('code', { text: r.url }), ` (open for ${Math.round(r.expires_in_s / 60)} min, SHA-256 ${String(r.sha256).slice(0, 12)}…).`,
          e.run ? h('span', {}, ' Then run: ', h('code', { text: e.run.replace('{HOST}', host) })) : null,
          e.status !== 'READY' && e.reason ? h('span', { class: 'bad', text: ' ' + e.reason }) : null));
      } catch (err) { out.textContent = 'Download blocked: ' + err.message; } finally { btn.disabled = false; }
    } }, `Download ${e.filename}`);
    return h('div', { class: 'portal' }, btn, out);
  }
  const KIND_OF = { phone: c => (c.kind === 'phone' || c.kind === 'tablet' || c.kind === 'phone_maybe') && c.platform !== 'ios/apple', watch: c => c.kind === 'watch' && c.platform !== 'ios/apple', iphone: c => c.platform === 'ios/apple', tv: c => c.kind === 'tv', pc: c => c.kind === 'computer' };
  function methodCard(title, status, detail, steps, extra) {
    const [t, cls] = MSTATE[status] || [status, ''];
    return h('details', { class: 'method ' + cls, open: true }, h('summary', {}, h('strong', { text: title }), h('span', { class: 'pill ' + cls, text: t })), detail ? h('p', { class: 'sub', text: detail }) : null, steps ? h('ol', {}, ...steps.map(x => h('li', { text: x }))) : null, ...(extra || []));
  }
  function guideFor(type, main) {
    const G = {
      phone: ['Android phone or tablet', 'Pick the simplest way. Wi-Fi needs no cable; USB gives the most complete control; the Companion app adds Bluetooth reach.'],
      watch: ['Wear OS watch (e.g. Galaxy Watch7)', 'Watches connect over Wi-Fi debugging. Control actions stay consent-gated.'],
      tv: ['Android TV / Google TV', null, ['On the TV: Settings → Device preferences → About → press “Build” 7 times.', 'Developer options → Network debugging (or USB debugging): on.', 'Run discovery, open the TV in My Devices and press “Connect over ADB Wi-Fi”; accept the prompt on the TV.']],
      pc: ['Windows or Linux PC', 'Pick the build below that matches the other computer. The agent connects back to this PC with your pre-shared key; every command needs your approval.', ['Start OpenBridge with --windows-bridge so the agent can link.', 'Pick the matching build below, open the time-limited link on that computer, and run the agent as administrator.', 'It appears in My Devices as connected.']],
      router: ['Internet box / router (Freebox OS, UPnP-IGD)', null, ['Run discovery. A Freebox appears automatically; press “Authorize read-only Freebox inventory” and confirm on the box’s screen.', 'Other gateways: UPnP-IGD status is read automatically when the router allows it.', 'OpenBridge never changes router settings.']],
      vacuum: ['Tuya robot vacuum', null, ['Link it once with your own Tuya IoT project: python -m dev.tuya_link --config <your config.json>.', 'Run discovery: the robot appears with its status and controls.']],
      iphone: ['iPhone / iPad', 'OpenBridge can see Apple devices on your network and read the model identifier they publish.'],
      unknown: ['Something else', null, ['Run discovery: OpenBridge shows what it can identify (mDNS, UPnP, router inventory, Bluetooth via relays).', 'Open the device in My Devices: unsupported capabilities are listed honestly.', 'Use “Teach a new skill” to check what is actually possible.']]
    }[type];
    main.append(h('h3', { text: G[0] }));
    if (G[1]) main.append(h('p', { class: 'sub', text: G[1] }));
    const found = h('div', { class: 'cand-list' });
    if (KIND_OF[type]) { main.append(found); api('/api/v2/onboarding').then(data => { const m = data.candidates.filter(KIND_OF[type]); if (m.length) found.replaceChildren(h('h4', { text: 'Found on your network' }), ...m.map(c => candidateCard(c, data.apk_portal, data.agent_matrix))); }).catch(() => {}); }
    const ms = h('div', { class: 'methods' });
    if (type === 'phone' || type === 'watch') {
      if (type === 'phone') ms.append(methodCard('USB cable (ADB debugging)', 'NEEDS_STEP', 'Most complete control. Some vendors (e.g. Xiaomi MIUI) also need “USB debugging (Security settings)” for taps and settings.', ['Settings → About phone → tap “Build number” 7 times', 'Settings → Developer options → USB debugging: on', 'Plug the cable into this PC, accept “Allow USB debugging” on the phone, then run discovery'], [h('button', { class: 'ghost small', type: 'button', onclick: () => { $('#connect').close(); discoverAndOpen(); } }, 'Run discovery')]));
      ms.append(methodCard('Wi-Fi pairing (ADB wireless debugging)', 'NEEDS_STEP', 'No cable (Android 11+ and Wear OS). The device shows a 6-digit code; OpenBridge runs the official adb pairing with it.', ['Developer options → Wireless debugging: on', 'Tap “Pair device with pairing code”', 'Type the IP address:port and the code shown under it'], [pairForm(type === 'watch' ? 'watch' : 'android', '')]));
      if (type === 'phone') ms.append(methodCard('OpenBridge Companion app (APK)', 'NEEDS_STEP', 'Adds Bluetooth relay for this PC. Android always asks before installing; OpenBridge cannot install silently.', ['Open the time-limited link below on the phone (same Wi-Fi)', 'Allow the install when Android asks, then open the app and pair'], [apkPortal(null)]));
    } else if (type === 'iphone') {
      ms.append(methodCard('OpenBridge Companion for iOS', 'UNAVAILABLE', 'No iOS Companion app exists yet, and iOS has no debugging bridge like Android ADB, so OpenBridge cannot control an iPhone today. It stays visible as a detected device.', null));
    } else if (type === 'pc') {
      ms.append(h('ol', { class: 'guide-steps' }, ...G[2].map(x => h('li', { text: x }))));
      api('/api/v2/onboarding').then(data => { ms.append(methodCard('Agent build for that computer', 'NEEDS_STEP', 'One row per hardware. Open the time-limited link on that computer and run the agent as administrator with your pre-shared key.', null, [agentPicker((data.agent_matrix || []).filter(e => e.id !== 'android-apk'))])); }).catch(() => { ms.append(methodCard('Agent build for that computer', 'UNAVAILABLE', 'Onboarding data unavailable.', null)); });
    } else ms.append(h('ol', { class: 'guide-steps' }, ...G[2].map(x => h('li', { text: x }))));
    main.append(ms);
    if (type === 'router' || type === 'tv' || type === 'unknown') main.append(h('button', { class: 'ghost small', type: 'button', onclick: () => { $('#connect').close(); discoverAndOpen(); } }, 'Run discovery'));
  }


  // ---------------- assistant ----------------
  function openAssistant() {
    const d = $('#assistant'); d.hidden = false; d.classList.add('open');
    const voice = $('.voice-panel'); if (voice && voice.parentElement !== $('#assistant-voice')) $('#assistant-voice').append(voice);
    const chips = $('#assistant-chips');
    if (!chips.childElementCount) for (const q of ['Find my Bluetooth devices through the TV', 'Why does my TV disconnect?', 'Discover my devices', 'Run a diagnostic report']) chips.append(h('button', { class: 'chip link', type: 'button', onclick: () => { const inp = $('.voice-panel input:not([type])') || $('.voice-panel input'); if (inp) { inp.value = q; const b = $$('.voice-panel button').find(x => x.textContent === 'Propose'); if (b) b.click(); } } }, q));
    setTimeout(() => (($('.voice-panel input') || d).focus()), 30);
  }
  function closeAssistant() { const d = $('#assistant'); d.classList.remove('open'); d.hidden = true; }

  // ---------------- palette & notifications ----------------
  function openPalette() {
    const dlg = $('#palette'), inp = $('#palette-input'), list = $('#palette-list');
    const items = () => [
      ...Object.entries(VIEWS).map(([k, v]) => ({ t: v, sub: 'Go to', run: () => go(k) })),
      { t: 'Discover devices', sub: 'Action', run: discoverAndOpen }, { t: 'Connect a device', sub: 'Action', run: () => openConnect() }, { t: 'Teach a new skill', sub: 'Action', run: openTeach }, { t: 'Open Meta AI Assistant', sub: 'Action', run: openAssistant }, { t: 'Finish session (restore changes)', sub: 'Action', run: () => { go('activity'); setTimeout(() => $('#session-finish').click(), 50); } },
      ...(st.snap ? st.snap.devices.map(d => ({ t: label(d), sub: catLabel(d.category), run: () => go('devices', d.key) })) : []),
      ...skills().map(k => ({ t: k.name, sub: 'Skill · ' + k.availability, run: () => go('skills') }))];
    let idx = 0, shown = [];
    const draw = () => { const q = inp.value.toLowerCase(); shown = items().filter(i => !q || (i.t + ' ' + i.sub).toLowerCase().includes(q)).slice(0, 12); idx = Math.min(idx, Math.max(shown.length - 1, 0)); list.replaceChildren(...shown.map((i, n) => h('li', { role: 'option', 'aria-selected': n === idx ? 'true' : 'false', onclick: () => { dlg.close(); i.run(); } }, h('span', { text: i.t }), h('small', { text: i.sub })))); };
    inp.value = ''; inp.oninput = () => { idx = 0; draw(); };
    inp.onkeydown = e => { if (e.key === 'ArrowDown') { idx = Math.min(idx + 1, shown.length - 1); draw(); e.preventDefault(); } else if (e.key === 'ArrowUp') { idx = Math.max(idx - 1, 0); draw(); e.preventDefault(); } else if (e.key === 'Enter' && shown[idx]) { dlg.close(); shown[idx].run(); } };
    draw(); dlg.showModal(); inp.focus();
  }
  const NOTIFY = e => (e.kind === 'receipt' && ['FAILED', 'UNKNOWN_TIMEOUT', 'PARTIAL'].includes(e.state)) || ['watch_triggered', 'watch_unavailable', 'reattached'].includes(e.kind);
  function updateBadge() { const n = st.events.filter(e => NOTIFY(e) && e.seq > st.seenNotif).length; const b = $('#notif-badge'); b.hidden = !n; b.textContent = String(n); }
  function openNotifications() {
    const list = $('#notif-list'); list.replaceChildren();
    const ev = st.events.filter(NOTIFY).slice(-30).reverse();
    if (!ev.length) list.append(h('li', { class: 'muted', text: 'Nothing needs your attention.' }));
    for (const e of ev) list.append(timelineItem(e));
    st.seenNotif = st.seq; store.set('notifSeen', String(st.seq)); updateBadge();
    $('#notifications').showModal();
  }

  // ---------------- toasts (mirror of the status line) ----------------
  function toast(text, cls) { const t = h('div', { class: 'toast ' + (cls || ''), role: 'status', text }); $('#toasts').append(t); setTimeout(() => t.remove(), 5200); }
  new MutationObserver(() => { const t = $('#status').textContent.trim(); $('#status').classList.toggle('bad', /blocked|failed|error|refused/i.test(t)); }).observe($('#status'), { childList: true, characterData: true, subtree: true });

  { const voice = $('.voice-panel'); if (voice) $('#assistant-voice').append(voice); }
  // ---------------- menu ----------------
  function closeMenu() { $('#sidebar').classList.remove('open'); $('.menu-toggle').setAttribute('aria-expanded', 'false'); }

  // ---------------- wiring ----------------
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-action]'); if (!a) return;
    const act = a.dataset.action;
    if (act === 'connect') openConnect();
    if (act === 'connect-close') $('#connect').close();
    if (act === 'assistant') openAssistant();
    if (act === 'assistant-close') closeAssistant();
    if (act === 'palette') openPalette();
    if (act === 'notifications') openNotifications();
    if (act === 'notif-close') $('#notifications').close();
    if (act === 'teach') openTeach();
    if (act === 'discover-home') discoverAndOpen();
    if (act === 'menu') { const sb = $('#sidebar'); const open = !sb.classList.contains('open'); sb.classList.toggle('open', open); a.setAttribute('aria-expanded', String(open)); }
  });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); }
    if (e.key === 'Escape') { closeAssistant(); closeMenu(); }
    if (e.altKey && /^[1-6]$/.test(e.key)) { e.preventDefault(); go(Object.keys(VIEWS)[Number(e.key) - 1]); }
  });
  function filterTree() {
    // The topology list is rendered by app.js; apply the same text filter DOM-side
    // so Cards and Topology list always agree. Parents with a matching descendant stay.
    const q = st.filter.toLowerCase();
    const tree = $('#fabric-tree'); if (!tree) return;
    for (const li of tree.querySelectorAll('li')) {
      const btn = li.querySelector(':scope > .fabric-node, :scope > div.fabric-node');
      const self = !btn || btn.textContent.toLowerCase().includes(q);
      const child = [...li.querySelectorAll(':scope ul .fabric-node')].some(n => n.textContent.toLowerCase().includes(q));
      li.hidden = Boolean(q) && !self && !child;
    }
  }
  $('#device-filter').addEventListener('input', e => { st.filter = e.target.value; renderDevices(); filterTree(); });
  for (const b of $$('[data-layout]')) b.addEventListener('click', () => { st.layout = b.dataset.layout; for (const x of $$('[data-layout]')) { x.classList.toggle('active', x === b); x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); } $('#device-grid').hidden = st.layout !== 'grid'; $('#tree-wrap').hidden = st.layout !== 'tree'; });
  for (const b of $$('#device-tabs [role=tab]')) b.addEventListener('click', () => setTab(b.dataset.tab));
  $('#graph-skill').addEventListener('change', e => { st.graphSkill = e.target.value; renderGraph(); });
  document.addEventListener('click', e => { const sb = $('#sidebar'); if (sb.classList.contains('open') && !sb.contains(e.target) && !e.target.closest('[data-action=menu]')) { sb.classList.remove('open'); $('[data-action=menu]').setAttribute('aria-expanded', 'false'); } });
  for (const b of $$('[data-graph-view]')) b.addEventListener('click', () => { st.graphView = b.dataset.graphView; for (const x of $$('[data-graph-view]')) { x.classList.toggle('active', x === b); x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); } $('#graph-svg').hidden = st.graphView !== 'graph'; $('#graph-list').hidden = st.graphView !== 'list'; $('.graph-tools').hidden = st.graphView !== 'graph'; });
  if (matchMedia('(max-width: 700px)').matches) $('[data-graph-view=list]').click();
  document.addEventListener('click', e => { const g = e.target.closest('[data-graph]'); if (!g) return; if (g.dataset.graph === 'zoom-in') zoom(0.8); if (g.dataset.graph === 'zoom-out') zoom(1.25); if (g.dataset.graph === 'fit') fitGraph(graphModel().nodes); });
  (() => { // pan & wheel zoom
    const svg = $('#graph-svg'); let drag = null;
    svg.addEventListener('pointerdown', e => { if (e.target.closest('.node')) return; drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; svg.setPointerCapture(e.pointerId); });
    svg.addEventListener('pointermove', e => { if (!drag) return; const k = view.w / svg.clientWidth; view.x = drag.vx - (e.clientX - drag.x) * k; view.y = drag.vy - (e.clientY - drag.y) * k; applyView(); });
    svg.addEventListener('pointerup', () => { drag = null; });
    svg.addEventListener('wheel', e => { if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); zoom(e.deltaY > 0 ? 1.1 : 0.9); }, { passive: false });
  })();
  // When a tree node is clicked inside app.js, keep the shell's selection in sync.
  $('#fabric-tree').addEventListener('click', e => { const n = e.target.closest('.fabric-node'); if (!n || !st.snap) return; const d = st.snap.devices.find(x => n.textContent.includes(label(x))); if (d) { st.selected = d.key; renderInspectorHead(d); setTab('controls'); } });
  // Hooks into app.js renderers (global function bindings in this classic-script realm).
  const baseRender = renderFabric;
  renderFabric = function (snap) { baseRender(snap); onSnapshot(snap); filterTree(); }; // eslint-disable-line no-global-assign
  const baseShow = showDevice;
  let inSelect = false;
  showDevice = function (device, links) { // eslint-disable-line no-global-assign
    baseShow(device, links); $('#device-tabs').hidden = false;
    if (inSelect || !device || !device.key) return;
    // Selected from the topology list or a legacy panel: show the same inspector, on the facts tab.
    st.selected = device.key; renderInspectorHead(device); setTab('controls'); $('#device-inspector').classList.add('open');
  };
  // Runtime status pill.
  api('/api/model-status').then(m => { st.model = m; $('#runtime-dot').className = 'dot ' + (m.inference_available ? 'ok' : ''); $('#mode-pill').textContent = m.inference_mode === 'local' ? 'Local Meta' : m.inference_mode === 'cloud' ? 'Cloud on request' : 'Local'; if (current === 'automations') renderAutomations(); if (current === 'skills') renderSkills(); }).catch(() => {});
  window.addEventListener('hashchange', route);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) pollEvents(); });
  setInterval(pollEvents, 8000);
  pollEvents();
  route();
  // app.js already requested /api/fabric; if it rendered before this script ran, pick its snapshot up.
  if (typeof fabric !== 'undefined' && fabric) onSnapshot(fabric);
})();


/* Codex read-only B2 route consumer. No invocation, policy change or automatic polling. */
(() => {
  const host = document.getElementById('route-truth');
  const refresh = document.getElementById('route-refresh');
  const picker = document.getElementById('route-skill');
  if (!host || !refresh || !picker) return;
  const targetPicker = document.getElementById('route-target');
  const targetLabel = document.getElementById('route-target-label');
  const revisions = new Map();
  let generation = 0;
  const node = (tag, text) => { const n = document.createElement(tag); n.textContent = String(text); return n; };
  const states = new Set(['READY', 'STANDBY', 'UNAVAILABLE']);
  const reasons = new Set(['link_down', 'grant_insufficient', 'consent_missing', 'capability_absent', 'lease_stale', 'dependency_unready', 'policy_blocked', 'backend_unknown']);
  function supported(doc, skill, target) {
    if (!doc || doc.schema_version !== 'b2.2' || doc.skill?.skill_id !== skill ||
        !['AUTO', 'PREFERRED', 'PINNED'].includes(doc.policy?.mode) ||
        !doc.graph_revision || typeof doc.graph_revision.epoch !== 'string' ||
        !Number.isSafeInteger(doc.graph_revision.seq) || doc.graph_revision.seq < 0 ||
        !Number.isFinite(Date.parse(doc.server_time)) || !Array.isArray(doc.routes) || doc.routes.length > 128 ||
        !['idle', 'armed', 'executing'].includes(doc.invocation?.status)) return false;
    const ids = new Set();
    return doc.routes.every(r => {
      if (!r || typeof r.route_id !== 'string' || r.route_id.length > 128 || ids.has(r.route_id) ||
          !states.has(r.state) || !['REAL_HARDWARE', 'SIMULATED', 'NONE'].includes(r.evidence) ||
          !['none', 'required', 'armed'].includes(r.consent) ||
          (r.state === 'UNAVAILABLE' ? !reasons.has(r.reason) : r.reason !== null) ||
          !Array.isArray(r.hops) || r.hops.length > 4 || !r.freshness ||
          !Number.isFinite(Date.parse(r.freshness.observed_at)) || !Number.isFinite(Date.parse(r.freshness.expires_at))) return false;
      ids.add(r.route_id);
      return r.hops.every(h => h && typeof h.device_key === 'string' && typeof h.transport === 'string');
    }) && (doc.selected_route_id === null || doc.routes.some(r => r.route_id === doc.selected_route_id && r.state === 'READY' && (!target || r.hops.some(h => h.device_key === target))));
  }
  function render(doc) {
    host.replaceChildren(node('p', `Snapshot · ${doc.server_time} · ${doc.policy.mode} · revision ${doc.graph_revision.seq}`));
    host.append(node('p', 'Eligibility and selection are backend-reported. This snapshot does not authorize execution or promise failover.'));
    if (!doc.routes.length) host.append(node('p', 'No eligible routes reported.'));
    for (const r of doc.routes) {
      const card = document.createElement('article'); card.className = 'route-card';
      card.append(node('h3', r.route_id), node('p', `${r.state} · ${r.evidence}`));
      if (r.route_id === doc.selected_route_id) card.append(node('p', 'Selected by backend'));
      if (['armed', 'executing'].includes(doc.invocation.status) && doc.invocation.route_id === r.route_id) card.append(node('p', `Invocation: ${doc.invocation.status}`));
      if (r.reason) card.append(node('p', `Unavailable reason: ${r.reason}`));
      card.append(node('p', `Consent: ${r.consent}`), node('p', r.hops.map(h => `${h.device_key} via ${h.transport}`).join(' → ')),
        node('p', `Observed ${r.freshness.observed_at}; expires ${r.freshness.expires_at}`));
      const details = document.createElement('details'); details.append(node('summary', 'Inspect route evidence'), node('pre', JSON.stringify(r, null, 2))); card.append(details); host.append(card);
    }
  }
  picker.addEventListener('change', () => {
    generation++; targetLabel.hidden = picker.value === 'ble_scan_room';
    targetPicker.replaceChildren(new Option('Select a discovered device', ''));
    const snapshot = typeof fabric !== 'undefined' ? fabric : null;
    for (const d of snapshot?.devices || []) targetPicker.append(new Option(d.label || d.category || 'Device', d.key));
    host.replaceChildren(node('p', 'Skill changed. Select its device if required, then refresh.'));
  });
  targetPicker.addEventListener('change', () => { generation++; host.replaceChildren(node('p', 'Device changed. Refresh its route snapshot.')); });
  refresh.addEventListener('click', async () => {
    const current = ++generation; const skill = picker.value;
    const target = skill === 'ble_scan_room' ? null : targetPicker.value;
    if (target === '') { host.replaceChildren(node('p', 'Select a discovered device first. Run discovery in My Devices if the list is empty.')); return; }
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 10000);
    refresh.disabled = true; host.setAttribute('aria-busy', 'true'); host.replaceChildren(node('p', 'Requesting route snapshot…'));
    try {
      const response = await fetch(`/api/v2/skill_routes?skill=${encodeURIComponent(skill)}${target ? '&target=' + encodeURIComponent(target) : ''}`, {cache: 'no-store', signal: controller.signal});
      if (current !== generation) return;
      if (response.status === 404) { host.replaceChildren(node('p', 'Routing backend is not available. No routes or failover are assumed.')); return; }
      if (!response.ok) throw new Error('Route request refused');
      const doc = await response.json();
      if (current !== generation) return;
      if (!supported(doc, skill, target)) { host.replaceChildren(node('p', 'Unsupported or invalid route snapshot. No route status is displayed.')); return; }
      const revisionKey = `${skill}:${target || ''}`;
      const previous = revisions.get(revisionKey);
      if (previous && previous.epoch === doc.graph_revision.epoch && previous.seq > doc.graph_revision.seq) {
        host.replaceChildren(node('p', 'Outdated route snapshot refused. Refresh again.')); return;
      }
      revisions.set(revisionKey, doc.graph_revision); render(doc);
    } catch (error) {
      if (current === generation) host.replaceChildren(node('p', error.name === 'AbortError' ? 'Route request timed out. Refresh to try again.' : 'Route evidence unavailable. No route status is assumed.'));
    } finally { clearTimeout(timer); refresh.disabled = false; host.removeAttribute('aria-busy'); }
  });
})();
