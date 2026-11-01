'use strict';
/* Ask OpenBridge — Command Center P0. Self-contained: own fetch + CSRF + i18n.
   Every stage renders only on a real backend event; nothing is simulated. */
(function () {
  const root = document.getElementById('ask-root');
  if (!root) return;

  /* Owner rule: rendered UI is English throughout. French is accepted as
     REQUEST text only (request-language selector below, neutral EN/FR codes). */
  const STRINGS = {
    title: 'Ask OpenBridge', tagline: 'Tell your devices what you want. Meta AI will find or learn a way.',
    ask: 'Ask', placeholder: 'e.g. Start my vacuum · Scan for bluetooth devices',
    quality: 'AI quality', low: 'Low · free local', medium: 'Medium · free local',
    high: 'High · Meta cloud', auto: 'Auto · local first',
    requestLang: 'Request', local: 'local', cloud: 'cloud', ready: 'ready', notReady: 'not ready',
    notConfigured: 'cloud not configured', disabled: 'cloud disabled',
    consent: 'I allow cloud calls for this request (at most $0.10 each, kill switch on).',
    estimate: 'estimate', cost: 'cost', needConsent: 'Cloud consent is required for High quality.',
    stUnderstand: 'Understanding request', stDevices: 'Identifying devices',
    stSkills: 'Checking available skills', stPreview: 'Preview ready',
    stApproval: 'Awaiting approval', stExecute: 'Executing', stVerified: 'Verification completed',
    approve: 'Approve & execute', approved: 'Approved', executing: 'Executing…',
    outcome: 'Outcome', skill: 'Skill', devices: 'Devices', model: 'Model',
    timeTaken: 'Time taken', evidence: 'Evidence', state: 'State',
    clarification: 'One question before I act', unsupported: 'Not supported',
    escalation: 'Needs a stronger model or setup step', reasons: 'Reasons',
    suggestions: 'Try', recents: 'Recent', error: 'Request failed',
    micTitle: 'Voice input arrives in P1; text only for now',
    micReady: 'Record a voice command (local Meta STT)', micStop: 'Stop and transcribe',
    micBusy: 'Transcribing…', micDenied: 'Microphone unavailable in this browser',
    partial: 'Partial success', failed: 'Failed',
    modelSettings: 'Model settings', modelReady: 'Local · model ready', modelOff: 'Meta model unavailable',
    modelChecking: 'Checking model…', modelHint: 'Devices stay usable without a model; start OpenBridge with --local-meta to enable requests.',
    cloudNeeded: 'This request may send the approved request text to Meta cloud. Review the cost estimate before continuing.',
  };
  const motion = (type, extra) => document.dispatchEvent(new CustomEvent('ob:motion', { detail: Object.assign({ type }, extra || {}) }));
  let reqLang = (navigator.language || 'en').toLowerCase().startsWith('fr') ? 'fr' : 'en';
  const t = (k) => STRINGS[k] || k;

  let csrf;
  async function req(path, body) {
    const opt = body === undefined ? {} : { method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify(body) };
    const r = await fetch(path, { cache: 'no-store', ...opt });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(data.error || `HTTP ${r.status}`); e.status = r.status; throw e; }
    return data;
  }
  async function post(path, body) {
    if (!csrf) csrf = (await req('/api/session')).csrf_token;
    try {
      return await req(path, body);
    } catch (e) {
      if (e.status === 403) { csrf = (await req('/api/session')).csrf_token; return req(path, body); }
      throw e;
    }
  }

  const SUGGESTIONS = [
    'Scan for bluetooth devices',
    'Start my vacuum',
    'Set living room TV volume to 10',
  ];
  let tiers = null, quality = 'auto', cloudConsent = false, running = false, advancedOpen = false;

  function el(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  }
  function fmtUsd(v) { return v === 0 ? '$0.00' : `~$${Number(v).toFixed(2)}`; }

  function cloudPossible() {
    if (quality === 'high') return true;
    const hi = tiers && tiers.high;
    return quality === 'auto' && !!(hi && hi.configured && hi.enabled);
  }
  function modelLine() {
    const line = el('p', undefined, 'ask-model');
    const dot = el('span', undefined, 'dot');
    let text = t('modelChecking'), ok = false;
    if (tiers) {
      ok = ['low', 'medium'].some(q => (tiers[q] || {}).ready) || !!((tiers.high || {}).configured && (tiers.high || {}).enabled);
      text = ok ? t('modelReady') : t('modelOff');
    }
    dot.className = 'dot ' + (ok ? 'ok' : tiers ? 'warn' : '');
    line.append(dot, el('span', text));
    if (tiers && !ok) line.append(el('small', t('modelHint'), 'muted'));
    return line;
  }
  function render() {
    root.replaceChildren();
    const head = el('div', undefined, 'panel-head');
    const h = el('div'); h.append(el('h2', t('title')), el('p', t('tagline'), 'sub'));
    h.firstChild.id = 'ask-title';
    head.append(h, modelLine());
    root.append(head);

    const form = el('div', undefined, 'ask-composer');
    const input = document.createElement('input');
    input.id = 'ask-input'; input.maxLength = 2000; input.placeholder = t('placeholder');
    input.setAttribute('aria-label', t('title'));
    input.autocomplete = 'off';
    const ask = el('button', t('ask'), 'primary');
    ask.type = 'button'; ask.onclick = () => run(input.value);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') run(input.value); });
    const mic = el('button', undefined, 'ghost');
    mic.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
    mic.type = 'button';
    const canMic = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.AudioContext);
    mic.disabled = !canMic;
    mic.title = t(canMic ? 'micReady' : 'micDenied');
    mic.setAttribute('aria-label', mic.title);
    mic.onclick = () => toggleMic(input, mic);
    form.append(input, ask, mic);
    root.append(form);

    const adv = document.createElement('details');
    adv.className = 'ask-advanced';
    adv.open = advancedOpen;
    adv.addEventListener('toggle', () => { advancedOpen = adv.open; });
    adv.append(el('summary', t('modelSettings')));
    const langBox = el('div', undefined, 'ask-lang');
    langBox.append(el('span', t('requestLang'), 'ask-label'));
    for (const l of ['en', 'fr']) {
      const b = el('button', l.toUpperCase(), 'ghost small' + (reqLang === l ? ' active' : ''));
      b.type = 'button'; b.onclick = () => { reqLang = l; render(); };
      langBox.append(b);
    }
    adv.append(langBox);
    const qbox = el('div', undefined, 'ask-quality');
    qbox.append(el('span', t('quality'), 'ask-label'));
    for (const q of ['low', 'medium', 'high', 'auto']) {
      const b = el('button', t(q), 'ask-pill' + (quality === q ? ' active' : ''));
      b.type = 'button'; b.onclick = () => { quality = q; render(); };
      qbox.append(b);
    }
    adv.append(qbox);
    const tierBox = el('div', undefined, 'ask-tiers');
    if (!tiers) tierBox.append(el('span', '…', 'muted'));
    else {
      for (const q of ['low', 'medium', 'high']) {
        const info = tiers[q] || {};
        const pill = el('span', undefined, 'tag');
        const ok = q === 'high' ? (info.configured && info.enabled) : info.ready;
        const infer = info.last_inference === 'failed' ? ' · infer failed'
          : (info.last_inference === 'ok' ? ' · infer ok' : '');
        pill.textContent = `${q}: ${(info.model || '?').split(':')[0]} · ${ok ? t('ready') : t('notReady')} · ${q === 'high' ? t('cloud') : t('local')} · ${t('estimate')} ${fmtUsd(info.estimate_usd)}${infer}`;
        tierBox.append(pill);
      }
    }
    adv.append(tierBox);
    root.append(adv);

    // Cloud approval only when this request could actually use the cloud tier; never assumed.
    if (cloudPossible()) {
      const consentRow = el('label', undefined, 'ask-consent');
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = cloudConsent;
      cb.onchange = () => { cloudConsent = cb.checked; };
      const txt = el('span');
      txt.append(el('strong', t('cloudNeeded')), document.createElement('br'), document.createTextNode(t('consent')));
      consentRow.append(cb, txt);
      root.append(consentRow);
    } else cloudConsent = false;

    const sug = el('div', undefined, 'ask-suggest');
    sug.append(el('span', t('suggestions'), 'ask-label'));
    for (const s of SUGGESTIONS) {
      const b = el('button', s, 'ghost small');
      b.type = 'button'; b.onclick = () => { input.value = s; input.focus(); };
      sug.append(b);
    }
    root.append(sug);

    const dev = el('div', undefined, 'ask-devices');
    const devHead = el('div', undefined, 'ask-dev-head');
    devHead.append(el('span', 'From devices', 'ask-label'));
    const check = el('button', 'Check devices', 'ghost small');
    check.type = 'button'; check.onclick = () => checkDevices();
    devHead.append(check);
    dev.append(devHead, el('div', undefined, 'ask-dev-list'));
    root.append(dev);

    root.append(el('ol', undefined, 'ask-stages'));
    root.append(el('div', undefined, 'ask-result'));
    const rec = recentList();
    if (rec.length) {
      const box = el('div', undefined, 'ask-recents');
      box.append(el('span', t('recents'), 'ask-label'));
      for (const r of rec) {
        const b = el('button', `${r.text} → ${r.skill || r.state}`, 'ghost small');
        b.type = 'button'; b.onclick = () => { input.value = r.text; input.focus(); };
        box.append(b);
      }
      root.append(box);
    }
  }

  function stages() { return root.querySelector('.ask-stages'); }
  function stage(key) {
    const li = el('li', t(key), 'done');
    stages().append(li);
    return li;
  }
  function resultBox() {
    const b = root.querySelector('.ask-result');
    b.replaceChildren();
    return b;
  }
  function kv(box, k, v) {
    const row = el('div', undefined, 'ask-kv');
    row.append(el('span', t(k), 'k'), el('span', String(v), 'v'));
    box.append(row);
  }
  async function checkDevices() {
    const list = root.querySelector('.ask-dev-list');
    list.replaceChildren(el('span', '…', 'muted'));
    try {
      const data = await req('/api/v2/companion/commands?poll=1');
      list.replaceChildren();
      const items = (data && data.pending) || [];
      if (!items.length) { list.append(el('span', 'No commands from devices.', 'muted')); return; }
      for (const it of items.slice(0, 12)) {
        const row = el('div', undefined, 'ask-dev-row');
        const d = it.intent || {};
        row.append(el('span', it.text || '', 'ask-dev-text'));
        row.append(el('span', `${d.status || '?'}${d.skill_id ? ' · ' + d.skill_id : ''}`, 'tag'));
        const load = el('button', 'Load', 'ghost small');
        load.type = 'button';
        load.onclick = () => {
          const input = document.getElementById('ask-input');
          if (input) { input.value = it.text || ''; input.focus(); }
        };
        row.append(load);
        list.append(row);
      }
    } catch (e) {
      list.replaceChildren(el('span', `${t('error')}: ${e.message}`, 'ask-error'));
    }
  }

  function recentList() {
    try { return JSON.parse(localStorage.getItem('ask-openbridge-recents') || '[]'); }
    catch { return []; }
  }
  function pushRecent(text, skill, state) {
    try {
      const list = [{ text, skill, state }, ...recentList()].slice(0, 8);
      localStorage.setItem('ask-openbridge-recents', JSON.stringify(list));
    } catch { /* private mode: recents simply do not persist */ }
  }

  /* Device-side voice, PC flavor: record PCM16 16 kHz in the browser, transcribe with
     local Meta STT, fill the same input for owner review. Nothing auto-runs. */
  let rec = null;
  const WORKLET = "registerProcessor('ob-cap',class extends AudioWorkletProcessor{"
    + "process(i){const c=i[0]&&i[0][0];if(c)this.port.postMessage(c.slice(0));return true}});";
  function pcm16b64(chunks, inRate) {
    let n = 0;
    for (const c of chunks) n += c.length;
    const flat = new Float32Array(n);
    let o = 0;
    for (const c of chunks) { flat.set(c, o); o += c.length; }
    const step = Math.max(1, Math.round(inRate / 16000));
    const out = new Int16Array(Math.floor(n / step));
    for (let i = 0; i < out.length; i++) {
      let s = 0;
      for (let k = 0; k < step; k++) s += flat[i * step + k] || 0;
      const v = Math.max(-1, Math.min(1, s / step));
      out[i] = v < 0 ? v * 32768 : v * 32767;
    }
    const bytes = new Uint8Array(out.buffer);
    let bin = '';
    for (let i = 0; i < bytes.length; i += 8192)
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
    return btoa(bin);
  }
  function micState(mic, cls, title) {
    mic.classList.toggle('recording', cls === 'recording');
    mic.disabled = cls === 'busy';
    mic.title = t(title); mic.setAttribute('aria-label', t(title));
  }
  async function toggleMic(input, mic) {
    if (rec) { stopMic(input, mic); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const ctx = new AudioContext();
      await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' })));
      const src = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, 'ob-cap');
      const chunks = [];
      let lastLevelAt = 0;
      node.port.onmessage = (e) => {
        chunks.push(e.data);
        const now = performance.now();
        if (now - lastLevelAt > 50) {   // live mic level for the orb, only while really recording
          lastLevelAt = now;
          let sum = 0; const c = e.data;
          for (let i = 0; i < c.length; i++) sum += c[i] * c[i];
          motion('voice_level', { level: Math.min(1, Math.sqrt(sum / Math.max(1, c.length)) * 4) });
        }
      };
      src.connect(node);
      rec = { ctx, stream, node, chunks, timer: setTimeout(() => stopMic(input, mic), 15000) };
      micState(mic, 'recording', 'micStop');
      motion('voice_capture_started');
    } catch (e) {
      motion('voice_denied');
      resultBox().append(el('p', `${t('error')}: ${e.message || e}`, 'ask-error'));
    }
  }
  async function stopMic(input, mic) {
    const r = rec; rec = null;
    if (!r) return;
    clearTimeout(r.timer);
    motion('voice_capture_stopped');
    micState(mic, 'busy', 'micBusy');
    try {
      r.node.disconnect();
      const rate = r.ctx.sampleRate;
      const chunks = r.chunks;
      r.stream.getTracks().forEach((tr) => tr.stop());
      await r.ctx.close();
      if (!chunks.length) throw new Error('no audio captured');
      const data = await post('/api/v2/voice/transcribe', { audio_b64: pcm16b64(chunks, rate), language: reqLang });
      input.value = (data.transcript || '').trim();
      input.dataset.voice = '1';
      input.focus();
    } catch (e) {
      resultBox().append(el('p', `${t('error')}: ${e.message || e}`, 'ask-error'));
    } finally {
      micState(mic, '', 'micReady');
    }
  }
  /* Spoken outcome on this PC, only for requests that started by voice. */
  function speak(text) {
    try {
      if (!('speechSynthesis' in window) || !text) return;
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(String(text).slice(0, 200));
      u.lang = reqLang === 'fr' ? 'fr-FR' : 'en-US';
      u.onstart = () => motion('speech_started');
      u.onend = u.onerror = () => motion('speech_ended');
      speechSynthesis.speak(u);
    } catch { /* silent: speech is a courtesy, never load-bearing */ }
  }

  async function run(text) {
    if (running || !text.trim()) return;
    running = true;
    const byVoice = document.getElementById('ask-input').dataset.voice === '1';
    document.getElementById('ask-input').dataset.voice = '';
    stages().replaceChildren(); resultBox();
    const t0 = performance.now();
    try {
      stage('stUnderstand');
      const parsed = await post('/api/v2/command/parse', {
        text: text.trim(), lang: reqLang, quality, cloud_consent: cloudConsent });
      const d = parsed.intent;
      if (d.status === 'needs_clarification') {
        const box = resultBox();
        box.append(el('h3', t('clarification')));
        box.append(el('p', d.clarifying_question || ''));
        pushRecent(text.trim(), null, d.status);
        if (byVoice) speak(d.clarifying_question || t('clarification'));
        return;
      }
      if (d.status === 'unsupported' || d.status === 'escalation_required') {
        const box = resultBox();
        box.append(el('h3', t(d.status === 'unsupported' ? 'unsupported' : 'escalation')));
        box.append(el('p', `${t('reasons')}: ${(d.ambiguities || []).join(' · ')}`));
        pushRecent(text.trim(), null, d.status);
        if (byVoice) speak(`${t(d.status === 'unsupported' ? 'unsupported' : 'escalation')}. ${(d.ambiguities || []).join('. ')}`);
        return;
      }
      if (d.status !== 'resolved') {
        resultBox().append(el('p', `${t('error')}: ${d.status}`));
        return;
      }
      stage('stDevices'); stage('stSkills');
      const prev = await post('/api/v2/command/approve', { intent: d });
      stage('stPreview');
      const box = resultBox();
      kv(box, 'outcome', d.outcome || '');
      kv(box, 'skill', d.skill_id);
      kv(box, 'devices', prev.device_keys.join(', '));
      kv(box, 'model', (d.provenance || {}).model_id || '?');
      if (prev.route) kv(box, 'evidence', `route ${prev.route.selected_route_id} (${prev.route.rule})`);
      kv(box, 'cost', parsed.cloud_used && parsed.usage
        ? `$${Number(parsed.usage.estimated_cost_usd).toFixed(4)} (${parsed.usage.usage.prompt_tokens}+${parsed.usage.usage.completion_tokens} tok)`
        : '$0.00 · ' + t('local'));
      stage('stApproval');
      motion('proposal_ready', { text: 'Preview ready · nothing has run yet' });
      motion('permission_requested', { text: 'Waiting for your approval · nothing has run yet' });
      const btn = el('button', t('approve'), 'primary');
      btn.type = 'button';
      btn.onclick = async () => {
        btn.disabled = true; btn.textContent = t('executing');
        try {
          stage('stExecute');
          const rc = await post('/api/v2/command/execute', { intent: d, consent: true, preview: prev });
          stage('stVerified');
          kv(box, 'state', rc.state || '?');
          kv(box, 'evidence', rc.transaction_id || '?');
          kv(box, 'timeTaken', `${Math.round(performance.now() - t0)} ms`);
          btn.textContent = t('approved');
          pushRecent(text.trim(), d.skill_id, rc.state);
          if (byVoice) speak(`${t('approved')}. ${rc.state || ''}`);
        } catch (e) {
          kv(box, 'failed', e.message);
          btn.disabled = false; btn.textContent = t('approve');
        }
      };
      box.append(btn);
      pushRecent(text.trim(), d.skill_id, 'preview');
      if (byVoice) speak(`${d.outcome || d.skill_id}. ${t('stApproval')}`);
    } catch (e) {
      resultBox().append(el('p', `${t('error')}: ${e.message}`, 'ask-error'));
    } finally {
      running = false;
    }
  }

  async function boot() {
    render();
    try { tiers = await req('/api/v2/command/tiers'); } catch { tiers = null; }
    render();
    const nav = document.getElementById('ask-nav');
    if (nav) nav.onclick = () => {
      if (!location.hash.startsWith('#/home')) location.hash = '#/home';
      document.getElementById('ask-openbridge').scrollIntoView({ behavior: 'smooth', block: 'start' });
      const i = document.getElementById('ask-input');
      if (i) setTimeout(() => i.focus({ preventScroll: true }), 350);
    };
  }
  boot();
})();
