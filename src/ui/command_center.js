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
    partial: 'Partial success', failed: 'Failed',
  };
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
  let tiers = null, quality = 'auto', cloudConsent = false, running = false;

  function el(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  }
  function fmtUsd(v) { return v === 0 ? '$0.00' : `~$${Number(v).toFixed(2)}`; }

  function render() {
    root.replaceChildren();
    const head = el('div', undefined, 'panel-head');
    const h = el('div'); h.append(el('h2', t('title')), el('p', t('tagline'), 'sub'));
    h.firstChild.id = 'ask-title';
    const langBox = el('div', undefined, 'ask-lang');
    langBox.append(el('span', t('requestLang'), 'ask-label'));
    for (const l of ['en', 'fr']) {
      const b = el('button', l.toUpperCase(), 'ghost small' + (reqLang === l ? ' active' : ''));
      b.type = 'button'; b.onclick = () => { reqLang = l; render(); };
      langBox.append(b);
    }
    head.append(h, langBox);
    root.append(head);

    const qbox = el('div', undefined, 'ask-quality');
    qbox.append(el('span', t('quality'), 'ask-label'));
    for (const q of ['low', 'medium', 'high', 'auto']) {
      const b = el('button', t(q), 'ask-pill' + (quality === q ? ' active' : ''));
      b.type = 'button'; b.onclick = () => { quality = q; render(); };
      qbox.append(b);
    }
    root.append(qbox);
    const tierBox = el('div', undefined, 'ask-tiers');
    if (!tiers) tierBox.append(el('span', '…', 'muted'));
    else {
      for (const q of ['low', 'medium', 'high']) {
        const info = tiers[q] || {};
        const pill = el('span', undefined, 'tag');
        const ok = q === 'high' ? (info.configured && info.enabled) : info.ready;
        pill.textContent = `${q}: ${(info.model || '?').split(':')[0]} · ${ok ? t('ready') : t('notReady')} · ${q === 'high' ? t('cloud') : t('local')} · ${t('estimate')} ${fmtUsd(info.estimate_usd)}`;
        tierBox.append(pill);
      }
    }
    root.append(tierBox);

    const consentRow = el('label', undefined, 'ask-consent');
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = cloudConsent;
    cb.onchange = () => { cloudConsent = cb.checked; };
    consentRow.append(cb, el('span', t('consent')));
    root.append(consentRow);

    const form = el('div', undefined, 'ask-composer');
    const input = document.createElement('input');
    input.id = 'ask-input'; input.maxLength = 2000; input.placeholder = t('placeholder');
    input.setAttribute('aria-label', t('title'));
    const ask = el('button', t('ask'), 'primary');
    ask.type = 'button'; ask.onclick = () => run(input.value);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') run(input.value); });
    const mic = el('button', undefined, 'ghost');
    mic.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
    mic.type = 'button'; mic.disabled = true; mic.title = t('micTitle');
    mic.setAttribute('aria-label', t('micTitle'));
    form.append(input, ask, mic);
    root.append(form);

    const sug = el('div', undefined, 'ask-suggest');
    sug.append(el('span', t('suggestions'), 'ask-label'));
    for (const s of SUGGESTIONS) {
      const b = el('button', s, 'ghost small');
      b.type = 'button'; b.onclick = () => { input.value = s; input.focus(); };
      sug.append(b);
    }
    root.append(sug);

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

  async function run(text) {
    if (running || !text.trim()) return;
    running = true;
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
        return;
      }
      if (d.status === 'unsupported' || d.status === 'escalation_required') {
        const box = resultBox();
        box.append(el('h3', t(d.status === 'unsupported' ? 'unsupported' : 'escalation')));
        box.append(el('p', `${t('reasons')}: ${(d.ambiguities || []).join(' · ')}`));
        pushRecent(text.trim(), null, d.status);
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
        } catch (e) {
          kv(box, 'failed', e.message);
          btn.disabled = false; btn.textContent = t('approve');
        }
      };
      box.append(btn);
      pushRecent(text.trim(), d.skill_id, 'preview');
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
