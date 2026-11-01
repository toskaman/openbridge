'use strict';
/* Workflows (UI V2): task-based summary on top of the existing sequence builder.
   Reads GET /api/v2/workflows/receipts (signed obv4.1-wf receipts) and shows each run as a sentence with per-node
   states mapped from the API: VERIFIED/EXECUTED, FAILED, BLOCKED, INCONCLUSIVE (never retried), SKIPPED, CANCELLED.
   A textual list is always available; nothing here runs, grants or rolls back anything. */
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
  const NODE = { VERIFIED: ['Verified', 'ok'], EXECUTED: ['Sent · not verified', 'warn'], FAILED: ['Failed', 'bad'], BLOCKED: ['Blocked', 'bad'],
    INCONCLUSIVE: ['Unknown · not retried', 'warn'], SKIPPED: ['Skipped (a dependency did not succeed)', 'muted'], CANCELLED: ['Cancelled', 'muted'] };
  const RUN = { COMPLETED: 'Completed', PARTIAL: 'Partly completed', FAILED: 'Failed', CANCELLED: 'Cancelled' };
  let seq = 0;

  async function render() {
    const box = document.getElementById('wf-v2');
    if (!box) return;
    const mine = ++seq;
    const intro = h('div', { class: 'wf-tasks' },
      h('a', { class: 'task-card', href: '#/studio/' + encodeURIComponent('Put my TV volume controls on my watch') },
        h('strong', { text: 'Watch button → TV volume' }), h('small', { text: 'Put real controls on a paired Companion. Preview, approve, then each press runs once.' }), h('span', { class: 'tag ok', text: 'available · Studio' })),
      h('a', { class: 'task-card', href: '#/home' }, h('strong', { text: 'Ask for a one-off action' }), h('small', { text: 'Type a request; you see the plan and approve it before anything runs.' }), h('span', { class: 'tag ok', text: 'available · Ask' })));
    const runs = h('section', { class: 'panel', 'aria-labelledby': 'wf-runs-title' }, h('div', { class: 'panel-head' }, h('h2', { id: 'wf-runs-title', text: 'Multi-device workflow runs' }), h('span', { class: 'tag', text: 'signed receipts' })));
    box.replaceChildren(intro, runs);
    let receipts = [];
    try { receipts = (await request('/api/v2/workflows/receipts')).receipts || []; }   // eslint-disable-line no-undef
    catch (e) { if (mine === seq) runs.append(h('p', { class: 'muted', text: 'Workflow receipts unavailable: ' + e.message })); return; }
    if (mine !== seq) return;
    if (!receipts.length) {
      runs.append(h('p', { class: 'muted', text: 'No multi-device workflow has run in this session. A workflow is a Meta-proposed plan (obv4.1-wf) that you sign once; each step keeps its own device permission.' }));
      return;
    }
    const ol = h('ol', { class: 'wf-runs' });
    for (const r of receipts.slice().reverse()) {
      const nodes = h('ol', { class: 'wf-nodes', 'aria-label': 'Steps' }, ...(r.nodes || []).map(n => {
        const [word, cls] = NODE[n.status] || [n.status, 'muted'];
        return h('li', { class: 'wf-node ' + cls }, h('strong', { text: n.node_id }), ' · ', word, n.error ? h('small', { text: ' — ' + String(n.error).slice(0, 120) }) : null);
      }));
      ol.append(h('li', { class: 'wf-run' }, h('div', { class: 'wf-run-head' }, h('strong', { text: r.workflow_id }), h('span', { class: 'tag ' + (r.status === 'COMPLETED' ? 'ok' : r.status === 'PARTIAL' ? 'warn' : ''), text: RUN[r.status] || r.status }),
        h('small', { class: 'muted', text: `${(r.started_at || '').replace('T', ' ').slice(0, 19)} · ${(r.nodes || []).length} step(s)` })), nodes,
        h('details', {}, h('summary', { text: 'Technical details' }), h('pre', { text: JSON.stringify({ operation_id: r.operation_id, workflow_hash: r.workflow_hash, wgrant_id: r.wgrant_id, signature: r.signature }, null, 1) }))));
    }
    runs.append(ol, h('p', { class: 'muted small', text: 'No atomic rollback is implied: a step is restored only where its own receipt proves the previous state.' }));
  }
  global.OBViews = global.OBViews || {};
  global.OBViews.workflows = { render };
})(window);
