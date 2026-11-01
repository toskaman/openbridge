'use strict';
/* Settings (UI V2): visual effects, motion, layout and the motion test harness.
   Preferences are per-viewer conveniences kept in this browser (localStorage, try/catch). Nothing here changes a
   device, a permission or the runtime. The harness is labelled TEST everywhere and never touches the network. */
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
    root.replaceChildren(h('div', { class: 'settings-grid' }, motion, layout, harness));
    if (M) M.mount(document.getElementById('settings-orb'), { sector: [-Math.PI, Math.PI] });
  }
  global.OBViews = global.OBViews || {};
  global.OBViews.settings = { render };
})(window);
