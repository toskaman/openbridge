'use strict';
/* Settings (UI V2): connected AI (manual), visual effects, motion, layout and the motion test harness.
   Preferences are per-viewer conveniences kept in this browser (localStorage, try/catch). Nothing here changes a
   device or a permission; the Connected AI card only edits the owner's provider list. The harness is labelled TEST everywhere and never touches the network. */
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
  const store = { get(k) { try { return localStorage.getItem('ob.' + k); } catch { return null; } }, set(k, v) { try { if (v === null) localStorage.removeItem('ob.' + k); else localStorage.setItem('ob.' + k, v); } catch { /* not persisted */ } } };

  function radios(name, legend, options, value, onChange, hint) {
    const fs = h('fieldset', { class: 'choice' }, h('legend', { text: legend }));
    for (const [v, t, sub] of options) {
      const id = `set-${name}-${v}`;
      const input = h('input', { type: 'radio', name, id, value: v });
      input.checked = value === v;
      input.addEventListener('change', () => { if (input.checked) onChange(v); });
      fs.append(h('label', { for: id, class: 'choice-opt' }, input, h('span', {}, h('strong', { text: t }), sub ? h('small', { text: sub }) : null)));
    }
    if (hint) fs.append(h('p', { class: 'muted small', text: hint }));
    return fs;
  }
  function toggle(id, text, sub, checked, onChange) {
    const input = h('input', { type: 'checkbox', id });
    input.checked = checked;
    input.addEventListener('change', () => onChange(input.checked));
    return h('label', { class: 'toggle-row', for: id }, input, h('span', {}, h('strong', { text }), h('small', { text: sub })));
  }

  /* Connected AI (manual). OpenBridge ships no paid model: local Meta Llama stays the default and is free.
     The owner may connect any OpenAI-compatible server or an Ollama server by hand. The API key goes to this PC's
     secret store through the local server and is never sent back to the page. Built once and kept across re-renders. */
  const PRESETS = [
    ['LM Studio', { kind: 'openai', base_url: 'http://127.0.0.1:1234/v1', name: 'lmstudio' }],
    ['Ollama', { kind: 'ollama', base_url: 'http://127.0.0.1:11434', name: 'ollama' }],
    ['llama.cpp', { kind: 'openai', base_url: 'http://127.0.0.1:8080/v1', name: 'llamacpp' }],
    ['OpenRouter', { kind: 'openai', base_url: 'https://openrouter.ai/api/v1', name: 'openrouter' }],
  ];
  let csrf = null;
  async function call(path, body) {
    const opt = { cache: 'no-store' };
    if (body !== undefined) {
      if (!csrf) csrf = (await (await fetch('/api/session', { cache: 'no-store' })).json()).csrf_token;
      Object.assign(opt, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body) });
    }
    const r = await fetch(path, opt);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }
  let aiCard = null;
  function aiSection() {
    if (aiCard) return aiCard;
    const status = h('p', { class: 'muted small', role: 'status', 'aria-live': 'polite', text: 'Loading connected AI…' });
    const list = h('div', { class: 'ai-list' });
    const field = (id, label, input, hint) => h('label', { class: 'ai-field', for: id }, h('span', { text: label }), input, hint ? h('small', { text: hint }) : null);
    const name = h('input', { id: 'ai-name', maxlength: '32', placeholder: 'lmstudio', autocomplete: 'off', spellcheck: 'false' });
    const kind = h('select', { id: 'ai-kind' }, h('option', { value: 'openai', text: 'OpenAI-compatible (/chat/completions)' }), h('option', { value: 'ollama', text: 'Ollama (/api/chat)' }));
    const base = h('input', { id: 'ai-base', placeholder: 'http://127.0.0.1:1234/v1', autocomplete: 'off', spellcheck: 'false' });
    const model = h('input', { id: 'ai-model', placeholder: 'model id, e.g. qwen2.5-7b-instruct', autocomplete: 'off', spellcheck: 'false' });
    const key = h('input', { id: 'ai-key', type: 'password', placeholder: 'optional, stored in this PC’s secret store', autocomplete: 'off' });
    const env = h('input', { id: 'ai-env', placeholder: 'or an environment variable, e.g. OPENROUTER_API_KEY', autocomplete: 'off', spellcheck: 'false' });
    const json = h('input', { type: 'checkbox', id: 'ai-json' });
    const activate = h('input', { type: 'checkbox', id: 'ai-activate' }); activate.checked = true;
    const presets = h('div', { class: 'row wrap ai-presets' }, h('span', { class: 'muted small', text: 'Presets:' }), ...PRESETS.map(([label, p]) => h('button', {
      class: 'ghost small', type: 'button', onclick: () => { name.value = name.value || p.name; kind.value = p.kind; base.value = p.base_url; model.focus(); },
    }, label)));
    const save = h('button', { class: 'primary small', type: 'button' }, 'Connect');
    save.addEventListener('click', async () => {
      const body = { name: name.value.trim().toLowerCase(), kind: kind.value, base_url: base.value.trim(), model: model.value.trim(), json_mode: json.checked, activate: activate.checked };
      if (env.value.trim()) body.api_key_env = env.value.trim();
      if (key.value) body.api_key = key.value;
      save.disabled = true; status.textContent = 'Saving…';
      try {
        const r = await call('/api/v2/ai/providers', body);
        key.value = '';
        status.textContent = `Connected ${r.provider.name} (${r.provider.execution === 'local' ? 'on this PC' : 'outside this PC'})${r.active === r.provider.name ? ' · active' : ''}. Press Test to check it answers.`;
        await refresh(false);
      } catch (e) { status.textContent = `Not saved: ${e.message}`; } finally { save.disabled = false; }
    });
    const form = h('div', { class: 'ai-form' }, presets,
      field('ai-name', 'Name', name, 'Lowercase letters, digits and “-”.'), field('ai-kind', 'API type', kind),
      field('ai-base', 'Base URL', base, 'https:// for anything outside your network; http:// only for this PC or your LAN.'),
      field('ai-model', 'Model', model), field('ai-key', 'API key', key), field('ai-env', 'Key from environment', env),
      h('label', { class: 'toggle-row', for: 'ai-json' }, json, h('span', {}, h('strong', { text: 'JSON mode' }), h('small', { text: 'Ask for response_format=json_object (only if the server supports it).' }))),
      h('label', { class: 'toggle-row', for: 'ai-activate' }, activate, h('span', {}, h('strong', { text: 'Use it for Pro requests' }), h('small', { text: 'Makes it the active connected AI in Ask → AI quality → Pro.' }))),
      h('div', { class: 'row' }, save));
    async function act(path, body, label) {
      status.textContent = `${label}…`;
      try { const r = await call(path, body); await refresh(false); return r; } catch (e) { status.textContent = `${label} failed: ${e.message}`; return null; }
    }
    function row(p, active) {
      const remote = p.execution !== 'local';
      const consentId = `ai-consent-${p.name}`;
      const consent = h('input', { type: 'checkbox', id: consentId });
      const test = h('button', { class: 'ghost small', type: 'button' }, 'Test');
      test.addEventListener('click', async () => {
        if (remote && !consent.checked) { status.textContent = `${p.name} runs outside this PC: tick “allow one test sentence” first.`; return; }
        test.disabled = true; status.textContent = `Testing ${p.name}…`;
        try {
          const r = await call('/api/v2/ai/providers/test', { name: p.name, consent: remote ? true : undefined });
          status.textContent = r.ok ? `${p.name} answered “${String(r.reply).slice(0, 40)}” in ${r.seconds}s (${r.reported_model || r.model}).` : `${p.name} answered, but not with OK: “${String(r.reply).slice(0, 60)}”.`;
        } catch (e) { status.textContent = `Test failed: ${e.message}`; } finally { test.disabled = false; }
      });
      return h('div', { class: 'ai-row' + (active ? ' active' : '') },
        h('div', { class: 'ai-row-main' },
          h('strong', { text: p.name }), ' ',
          h('span', { class: 'tag ' + (remote ? 'warn' : 'ok'), text: remote ? 'outside this PC' : 'local' }), ' ',
          active ? h('span', { class: 'tag ok', text: 'active' }) : null,
          h('small', { class: 'muted ai-row-sub', text: `${p.kind} · ${p.model} · ${p.endpoint} · key ${p.has_key ? 'stored' : p.api_key_env ? 'from $' + p.api_key_env : 'none'}` })),
        h('div', { class: 'row wrap' },
          active ? h('button', { class: 'ghost small', type: 'button', onclick: () => act('/api/v2/ai/providers/activate', { name: null }, 'Deactivating') }, 'Stop using')
            : h('button', { class: 'ghost small', type: 'button', onclick: () => act('/api/v2/ai/providers/activate', { name: p.name }, 'Activating') }, 'Use'),
          test,
          h('button', { class: 'ghost small danger', type: 'button', onclick: () => act('/api/v2/ai/providers/remove', { name: p.name }, 'Removing') }, 'Remove'),
          remote ? h('label', { class: 'muted small ai-consent', for: consentId }, consent, ' allow one test sentence') : null));
    }
    async function refresh(announce = true) {
      try {
        const d = await call('/api/v2/ai/providers');
        list.replaceChildren(...(d.providers.length ? d.providers.map(p => row(p, p.name === d.active))
          : [h('p', { class: 'muted small', text: 'No AI connected. Ask works with the free local models; Pro stays off until you connect one.' })]));
        if (announce) status.textContent = d.active ? `Active: ${d.active}.` : 'No connected AI is active.';
      } catch (e) { status.textContent = `Connected AI unavailable: ${e.message}`; }
    }
    aiCard = h('section', { class: 'panel ai-card', 'aria-labelledby': 'set-ai-title' }, h('h2', { id: 'set-ai-title', text: 'Connected AI' }),
      h('p', { class: 'muted', text: 'OpenBridge ships no paid model: Fast and Smart run on this PC for free. To use another AI for Pro requests, connect it by hand: any OpenAI-compatible server (LM Studio, llama.cpp, vLLM, OpenRouter…) or an Ollama server. Keys are kept in this PC’s secret store and never shown again. A hosted provider bills you directly.' }),
      list, status, h('details', { class: 'ai-add' }, h('summary', { text: 'Connect an AI / API' }), form));
    refresh();
    return aiCard;
  }

  function render() {
    const root = document.getElementById('settings-root');
    if (!root) return;
    const M = global.OBMotion;
    const p = M ? M.prefs : { motion: 'off', flowLabels: true, showFlows: true, perf: 'auto' };
    const set = patch => { if (M) M.setPrefs(patch); render(); };
    const osReduce = global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const classic = store.get('ui') === 'classic';

    const motion = h('section', { class: 'panel', 'aria-labelledby': 'set-motion-title' }, h('h2', { id: 'set-motion-title', text: 'Visual effects' }),
      radios('motion', 'Motion', [['full', 'Full', 'Animated orb and live comets for real messages'], ['reduced', 'Reduced', 'Static orb, no comets; state changes stay as text and counters'], ['off', 'Off', 'No animation at all']], p.motion, v => set({ motion: v }),
        osReduce ? 'Your system asks for reduced motion; OpenBridge starts in Reduced unless you choose otherwise here.' : 'Motion never carries information on its own: every state is also written as text.'),
      toggle('set-flows', 'Show actual network flows', 'Comets for real messages between this window, the runtime and paired Companions.', p.showFlows, v => set({ showFlows: v })),
      toggle('set-labels', 'Flow labels', 'Small “↑/↓ operation · size” labels beside comets (at most 8 at once).', p.flowLabels, v => set({ flowLabels: v })),
      radios('perf', 'Performance mode', [['auto', 'Auto', 'Full detail; lighter orb if frames get slow'], ['balanced', 'Balanced', 'Switches to the lighter orb sooner'], ['low', 'Low', 'Half the particles, 30 frames per second']], p.perf, v => set({ perf: v })));

    const layout = h('section', { class: 'panel', 'aria-labelledby': 'set-layout-title' }, h('h2', { id: 'set-layout-title', text: 'Layout' }),
      radios('ui', 'Navigation', [['v2', 'Workspace (V2)', 'Five sections: Home, Devices, Capabilities, Workflows, Activity'], ['classic', 'Classic', 'The previous navigation, kept as a fallback']], classic ? 'classic' : 'v2', v => {
        store.set('ui', v === 'classic' ? 'classic' : null);
        document.body.classList.toggle('ui-v2', v !== 'classic');
        global.dispatchEvent(new HashChangeEvent('hashchange'));
        render();
      }, 'Both layouts use the same pages, permissions and tests. Add ?ui=classic to the address for a one-off fallback.'));

    const harness = h('section', { class: 'panel', 'aria-labelledby': 'set-test-title' }, h('h2', { id: 'set-test-title' }, h('span', { class: 'tag warn', text: 'TEST' }), ' Motion test harness'),
      h('p', { class: 'muted', text: 'Checks every orb state and both comet directions. Everything shown is labelled TEST; no request is sent and nothing is recorded in Activity.' }),
      h('div', { class: 'harness-orb orb-stage', id: 'settings-orb' }, h('div', { class: 'orb-canvas-host' }), h('div', { class: 'orb-status', 'data-orb-status': '' }, h('strong', { class: 'orb-state' }), h('span', { class: 'orb-note' }))),
      h('div', { class: 'row wrap' }, ...['IDLE', 'LISTENING', 'THINKING', 'SPEAKING', 'ALERT', 'OFFLINE'].map(s => h('button', { class: 'ghost small', type: 'button', onclick: () => M && M.testState(s) }, s.toLowerCase()))),
      h('div', { class: 'row wrap' },
        h('button', { class: 'ghost small lg-out-btn', type: 'button', onclick: () => M && M.signal('transport_outbound', { origin: 'test', label: 'harness', bytes: 512, corr: 'test-out-' + Date.now() }) }, '↑ OUT comet (amber)'),
        h('button', { class: 'ghost small lg-in-btn', type: 'button', onclick: () => M && M.signal('transport_inbound', { origin: 'test', label: 'harness', bytes: 2048, corr: 'test-in-' + Date.now() }) }, '↓ IN comet (emerald)'),
        h('button', { class: 'ghost small', type: 'button', onclick: () => M && M.signal('oracle_success', { origin: 'test', text: 'harness pulse' }) }, 'Verified pulse')),
      h('p', { class: 'muted small', 'data-flow-counts': '' }));
    const watchWrap = h('div', { id: 'set-engo-watch-wrap', hidden: true });
    root.replaceChildren(h('div', { class: 'settings-grid' }, aiSection(), watchWrap, motion, layout, harness));
    refreshWatchOptions(watchWrap);
    if (M) M.mount(document.getElementById('settings-orb'), { sector: [-Math.PI, Math.PI] });
  }
  async function refreshWatchOptions(wrap) {
    try {
      const d = await call('/api/v2/engo_watch_controls');
      if (!d || !d.watch_detected) { wrap.hidden = true; wrap.replaceChildren(); return; }
      const paired = d.paired_watches || [];
      const target = paired[0] || null;
      const pages = d.pages || [];
      const active = target ? (d.active_pages || {})[target.relay_id] : null;
      const status = h('p', { class: 'muted small', role: 'status', text: target ? `Watch detected: ${target.label}${active ? ' · active page: ' + active : ''}` : 'Watch detected on network — pair Companion on the watch first.' });
      const act = async (action, page) => {
        status.textContent = 'Updating watch controls…';
        try {
          await call('/api/v2/engo_watch_controls', Object.assign({ action, consent: true }, page ? { page } : {}, target ? { relay_id: target.relay_id } : {}));
          await refreshWatchOptions(wrap);
        } catch (e) { status.textContent = e.message; }
      };
      wrap.hidden = false;
      wrap.replaceChildren(h('section', { class: 'panel', 'aria-labelledby': 'set-engo-watch-title', 'data-engo-watch': '1' },
        h('h2', { id: 'set-engo-watch-title', text: 'Wear OS Watch · ENGO 3 Controls' }),
        h('p', { class: 'muted', text: 'This option appears only when your Wear OS watch is detected. Push all ENGO 3 controls onto the watch at once.' }),
        status,
        target ? h('div', { class: 'row wrap' },
          pages.map(pg => h('button', { class: (active === pg.id ? 'primary' : 'ghost') + ' small', type: 'button', onclick: () => act('show', pg.id) }, pg.title)),
          active ? h('button', { class: 'ghost small danger', type: 'button', onclick: () => act('hide') }, 'Hide controls') : null) : null));
    } catch { wrap.hidden = true; wrap.replaceChildren(); }
  }
  global.OBViews = global.OBViews || {};
  global.OBViews.settings = { render };
})(window);
