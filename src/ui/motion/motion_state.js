'use strict';
/* Real-event adapter for the MotionController. Maps observed facts to motion signals; nothing else.

   Sources (all real, none invented):
   1. HTTP messages this window exchanges with the local OpenBridge runtime (POST /api/…):
      request sent => OUT comet; successful reply received => IN comet (size from Content-Length).
      Model endpoints => THINKING while the request is actually in flight.
      Execution replies are read (a clone) for their reported state: VERIFIED => verified pulse,
      EXECUTED/UNKNOWN/INCONCLUSIVE => "result not confirmed", FAILED/BLOCKED => failed. Never inferred.
      An HTTP refusal => no IN comet, refusal text. Simulated endpoints are labelled SIM.
   2. Runtime events (GET /api/v2/events, polled by shell.js) that describe relay traffic:
      remote_request (a Companion press reached this PC) => IN; remote_controls / ui_plan_installed (controls
      sent to a Companion) => OUT; relay_reconnected => IN; receipts => outcome text. Events that existed before
      this page loaded are history and never animate.
   3. Microphone capture and speech synthesis started by command_center.js (ob:motion DOM events).
   The fetch observer forwards every call unchanged and never alters requests or responses. */
(function (global) {
  const M = global.OBMotion;
  if (!M) return;
  const MODEL = new Set(['/api/v2/command/parse', '/api/v2/voice/intent', '/api/v2/voice/transcribe', '/api/recommend', '/api/fabric-advise',
    '/api/agent-plan', '/api/v2/cloud/confirm', '/api/v2/capabilities/followup', '/api/v2/diagnose']);
  const EXEC = new Set(['/api/v2/execute', '/api/v2/command/execute', '/api/v2/skill_invoke', '/api/v2/manifests/invoke', '/api/v2/remote_controls/invoke',
    '/api/v2/workflows/run', '/api/agent-execute', '/api/agent-undo', '/api/agent-recover', '/api/session-restore', '/api/demo-transaction']);
  const SIMULATED = new Set(['/api/demo-transaction']);
  const QUIET = new Set(['/api/session']);
  const UNCONFIRMED = new Set(['EXECUTED', 'EXECUTED_UNVERIFIED', 'UNKNOWN', 'UNKNOWN_TIMEOUT', 'UNCERTAIN', 'INCONCLUSIVE', 'PARTIAL']);
  const FAILED = new Set(['FAILED', 'BLOCKED', 'DENIED', 'REFUSED', 'EXPIRED']);
  let n = 0;

  const opName = path => path.replace(/^\/api\/(v2\/)?/, '').replace(/[/_-]+/g, ' ').trim() || 'request';
  function pathOf(input) {
    try { const u = new URL(typeof input === 'string' ? input : input.url, location.href); return u.origin === location.origin ? u.pathname : null; } catch { return null; }
  }
  function sizeOf(body) {
    if (typeof body === 'string') return new Blob([body]).size;
    if (body && typeof body.size === 'number') return body.size;
    if (body && typeof body.byteLength === 'number') return body.byteLength;
    return 0;
  }
  function stateOf(doc) {
    if (!doc || typeof doc !== 'object') return null;
    const s = doc.state || doc.status || (doc.receipt && doc.receipt.state) || (doc.result && doc.result.state);
    return typeof s === 'string' ? s.toUpperCase() : null;
  }
  function outcome(path, doc, origin) {
    const s = stateOf(doc);
    if (!s) return;
    const sim = origin === 'simulated';
    if (s === 'VERIFIED' && (doc.verified !== false)) M.signal('oracle_success', { origin, text: sim ? 'Simulated change verified by read-back' : 'Verified by an independent read-back' });
    else if (s === 'REVERTED' || s === 'RESTORED') M.signal('restored', { origin, text: sim ? 'SIM · restored' : undefined });
    else if (UNCONFIRMED.has(s)) M.signal('outcome_uncertain', { origin, text: s === 'EXECUTED' ? 'Sent · result not confirmed by a read-back' : undefined });
    else if (FAILED.has(s)) M.signal('action_failed', { origin, text: `${opName(path)} · ${s.toLowerCase()}` });
  }

  const origFetch = global.fetch && global.fetch.bind(global);
  if (origFetch && !origFetch.__obObserved) {
    const observed = function (input, init) {
      const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      const path = pathOf(input);
      if (method !== 'POST' || !path || !path.startsWith('/api/') || QUIET.has(path)) {
        return origFetch(input, init).then(r => { if (M.offline && path && path.startsWith('/api/')) M.signal('runtime_online'); return r; });
      }
      const corr = 'http-' + (++n), op = opName(path), model = MODEL.has(path);
      const origin = SIMULATED.has(path) ? 'simulated' : 'live';
      if (model) M.signal('model_inference_started', { corr });
      const hint = M.hint && M.hint.path === path && M.hint.until > performance.now() ? M.hint : null;   // a real on-screen destination
      if (hint) M.hint = null;
      M.signal('transport_outbound', { label: op, bytes: sizeOf(init && init.body), corr, origin, target: hint && hint.el });
      return origFetch(input, init).then(r => {
        if (model) M.signal('model_inference_finished', { corr });
        if (M.offline) M.signal('runtime_online');
        if (r.ok) {
          M.signal('transport_inbound', { label: op, bytes: Number(r.headers.get('content-length')) || 0, corr, origin });
          if (EXEC.has(path)) r.clone().json().then(doc => outcome(path, doc, origin)).catch(() => {});
        } else if (r.status === 403) {
          M.flow.cancel(corr);            // CSRF handshake: callers refresh the session and retry; not a refusal
        } else {
          r.clone().json().then(doc => M.signal('invoke_refused', { corr, reason: /no READY route/i.test(String(doc.error)) ? 'no connected device can do this yet' : `${op} · ${String(doc.error || 'HTTP ' + r.status).slice(0, 90)}` }))
            .catch(() => M.signal('invoke_refused', { corr, reason: `${op} · HTTP ${r.status}` }));
        }
        return r;
      }, err => {
        if (model) M.signal('model_inference_finished', { corr });
        M.flow.cancel(corr);
        if (!err || err.name !== 'AbortError') M.signal('runtime_offline');
        throw err;
      });
    };
    observed.__obObserved = true;
    global.fetch = observed;
  }

  // Runtime events (dispatched by shell.js after each real poll). The first batch is history: never animated.
  let primed = false;
  document.addEventListener('ob:runtime-events', e => {
    const evs = (e.detail && e.detail.events) || [];
    if (!primed) { primed = true; return; }
    for (const ev of evs) {
      const relay = ev.relay_id ? String(ev.relay_id).slice(0, 10) : '';
      if (ev.kind === 'remote_request') M.signal('transport_inbound', { label: 'Companion press' + (relay ? ' · ' + relay : ''), corr: 'ev-' + ev.seq });
      else if (ev.kind === 'remote_controls' || ev.kind === 'ui_plan_installed') M.signal('transport_outbound', { label: (ev.kind === 'ui_plan_installed' ? 'UI plan' : 'controls') + (relay ? ' → ' + relay : ''), corr: 'ev-' + ev.seq });
      else if (ev.kind === 'relay_reconnected') M.signal('transport_inbound', { label: 'relay reconnected', corr: 'ev-' + ev.seq });
      else if (ev.kind === 'receipt') outcome('/api/' + (ev.primitive_id || 'receipt'), ev, 'live');
      else if (ev.kind === 'remote_control_suspended') M.signal('action_failed', { text: 'A remote control was suspended after repeated presses' });
    }
  });
  document.addEventListener('ob:runtime-reachable', e => M.signal(e.detail && e.detail.ok ? 'runtime_online' : 'runtime_offline'));
  // Microphone / speech, from command_center.js.
  document.addEventListener('ob:motion', e => { const d = e.detail || {}; if (d.type) M.signal(d.type, d); });
})(window);
