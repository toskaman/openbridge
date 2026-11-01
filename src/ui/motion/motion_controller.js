'use strict';
/* OpenBridge MotionController — the single animation engine of the workspace.

   - One orb canvas (moved between stages: Home hero, Studio, compact header) and one transparent flow layer.
   - One requestAnimationFrame loop, running only while something visible needs it (an orb on screen with
     Motion = Full, or comets in flight). Hidden tab => no frames. No setInterval.
   - Inputs are real events only (motion_state.js maps runtime facts to signals). The renderer never decides,
     authorizes or fetches anything. TEST and REPLAY sources are labelled on every comet and in a banner.
   - Motion preference: Full / Reduced / Off (default follows prefers-reduced-motion). Reduced and Off draw a
     static orb frame on state change and never animate; the textual state and flow counters stay available.
   - The orb state is always mirrored as text ([data-orb-status]) and announced, throttled, in #orb-live. */
(function (global) {
  const O = global.OBOrb, F = global.OBFlow;
  if (!O || !F) return;
  const STORE_KEY = 'ob-motion-prefs';
  const reduceQuery = global.matchMedia ? global.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const DEFAULTS = () => ({ motion: reduceQuery && reduceQuery.matches ? 'reduced' : 'full', flowLabels: true, showFlows: true, perf: 'auto' });
  function loadPrefs() {
    const p = DEFAULTS();
    try { Object.assign(p, JSON.parse(localStorage.getItem(STORE_KEY) || '{}')); } catch { /* storage blocked: defaults */ }
    if (!['full', 'reduced', 'off'].includes(p.motion)) p.motion = DEFAULTS().motion;
    if (!['auto', 'balanced', 'low'].includes(p.perf)) p.perf = 'auto';
    p.flowLabels = p.flowLabels !== false; p.showFlows = p.showFlows !== false;
    return p;
  }

  const TEXT = {
    IDLE: 'Ready · waiting for your request',
    LISTENING: 'Listening · microphone open',
    THINKING: 'Thinking · a model request is in progress',
    SPEAKING: 'Speaking the result',
    OFFLINE: 'Runtime unreachable · showing the last known state',
  };

  class MotionController {
    constructor() {
      this.prefs = loadPrefs();
      this.orb = new O.OrbRenderer();
      this.flow = new F.FlowRenderer();
      this.orbCanvas = document.createElement('canvas');
      this.orbCanvas.className = 'ob-orb-canvas';
      this.orbCanvas.setAttribute('aria-hidden', 'true');
      this.flowCanvas = document.createElement('canvas');
      this.flowCanvas.className = 'ob-flow-layer';
      this.flowCanvas.setAttribute('aria-hidden', 'true');
      this.stage = null; this.stageOpts = {};
      this.stageVisible = false;
      this.raf = 0; this.lastTs = 0; this.lastOrbDraw = 0;
      this.frames = 0; this.loopStarts = 0; this.orbFrames = 0;
      this.lite = false; this.costAvg = 0;
      this.thinking = new Set(); this.listening = false; this.speaking = false; this.offline = false;
      this.alert = null;          // {text, until}
      this.note = null;           // {text, until}: last real outcome / step, shown under the state
      this.lastSpoken = ''; this.lastAnnounceAt = 0; this.announceTimer = 0;
      this.counts = { in: 0, out: 0 }; this.testInFlight = 0;
      this.io = global.IntersectionObserver ? new IntersectionObserver(es => { for (const e of es) if (e.target === this.stage) this.stageVisible = e.isIntersecting; this.kick(); }) : null;
      this.ro = global.ResizeObserver ? new ResizeObserver(() => this.resizeOrb()) : null;
      this.onVis = () => { if (document.hidden) this.stop(); else { this.lastTs = 0; this.kick(); } };
      this.onResize = () => this.resizeFlow();
      document.addEventListener('visibilitychange', this.onVis);
      global.addEventListener('resize', this.onResize);
      if (reduceQuery && reduceQuery.addEventListener) reduceQuery.addEventListener('change', () => { if (!this.prefsExplicit()) { this.prefs.motion = DEFAULTS().motion; this.applyPrefs(); } });
      document.body.append(this.flowCanvas);
      this.resizeFlow();
      this.applyPrefs();
    }
    prefsExplicit() { try { return !!JSON.parse(localStorage.getItem(STORE_KEY) || 'null'); } catch { return false; } }
    setPrefs(p) {
      Object.assign(this.prefs, p);
      try { localStorage.setItem(STORE_KEY, JSON.stringify(this.prefs)); } catch { /* not persisted */ }
      this.applyPrefs();
    }
    applyPrefs() {
      const m = this.prefs.motion;
      document.documentElement.dataset.motion = m;
      if (m !== 'full' || !this.prefs.showFlows) { this.flow.clear(); this.clearFlowCanvas(); }
      this.lite = this.prefs.perf === 'low';
      this.orb.settle();
      this.render(true);
      this.kick();
    }

    // ---------- stages ----------
    /** Move the single orb into `el`. opts: {sector:[a0,a1] radians where comets may fly, label}. */
    mount(el, opts) {
      if (!el) return;
      if (this.stage && this.stage !== el) this.unmount(this.stage);
      this.stage = el; this.stageOpts = opts || {};
      const host = el.querySelector('.orb-canvas-host') || el;
      if (this.orbCanvas.parentElement !== host) host.prepend(this.orbCanvas);
      const r = el.getBoundingClientRect();   // synchronous first answer; the observer keeps it current
      this.stageVisible = r.width > 0 && r.bottom > 0 && r.top < global.innerHeight && r.right > 0 && r.left < global.innerWidth;
      if (this.io) this.io.observe(el); else this.stageVisible = true;
      if (this.ro) this.ro.observe(el);
      this.resizeOrb();
      this.render(true);
      this.kick();
    }
    unmount(el) {
      if (!el || el !== this.stage) return;
      if (this.io) this.io.unobserve(el);
      if (this.ro) this.ro.unobserve(el);
      this.stage = null; this.stageVisible = false;
      if (this.orbCanvas.parentElement) this.orbCanvas.remove();
    }
    dpr() { return Math.min(2, global.devicePixelRatio || 1); }
    resizeOrb() {
      if (!this.stage) return;
      const host = this.orbCanvas.parentElement || this.stage;
      const r = host.getBoundingClientRect();
      const size = Math.max(40, Math.min(r.width || 0, r.height || r.width || 0) || 0);
      const d = this.dpr(), px = Math.round(size * d);
      if (this.orbCanvas.width !== px || this.orbCanvas.height !== px) { this.orbCanvas.width = px; this.orbCanvas.height = px; }
      this.orbCanvas.style.width = size + 'px'; this.orbCanvas.style.height = size + 'px';
      this.orbSize = size;
      this.drawOrb();
    }
    resizeFlow() {
      const d = this.dpr(), w = global.innerWidth, h = global.innerHeight;
      const W = Math.round(w * d), H = Math.round(h * d);
      if (this.flowCanvas.width !== W || this.flowCanvas.height !== H) { this.flowCanvas.width = W; this.flowCanvas.height = H; }
      this.flowCanvas.style.width = w + 'px'; this.flowCanvas.style.height = h + 'px';
    }
    clearFlowCanvas() { const c = this.flowCanvas.getContext('2d'); c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, this.flowCanvas.width, this.flowCanvas.height); }
    orbGeometry() {
      if (!this.stage || !this.stageVisible || !this.orbCanvas.isConnected) return null;
      const r = this.orbCanvas.getBoundingClientRect();
      if (!r.width) return null;
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, r: Math.min(r.width, r.height) * 0.30, sector: this.stageOpts.sector };
    }

    // ---------- state ----------
    stateNow() {
      const now = performance.now();
      if (this.alert && this.alert.until < now) this.alert = null;
      if (this.note && this.note.until < now) this.note = null;
      if (this.test && this.test.until < now) { this.test = null; this.testInFlight = Math.max(0, this.testInFlight - 1); this.showBanner(); }
      if (this.test) return this.test.state;
      if (this.offline) return O.OFFLINE;
      if (this.listening) return O.LISTENING;
      if (this.speaking) return O.SPEAKING;
      if (this.thinking.size) return O.THINKING;
      if (this.alert) return O.ALERT;
      return O.IDLE;
    }
    stateText() {
      const s = this.stateNow(), name = O.STATE_NAMES[s];
      if (this.test) return 'TEST · ' + (TEXT[name] || name + ' (harness)');
      if (s === O.ALERT && this.alert) return this.alert.text;
      return TEXT[name] || name;
    }
    render(force) {
      const s = this.stateNow();
      if (s !== this.orb.state) { this.orb.setState(s); if (this.prefs.motion !== 'full') this.orb.settle(); force = true; }
      const text = this.stateText(), note = this.note ? this.note.text : '';
      for (const el of document.querySelectorAll('[data-orb-status]')) {
        el.dataset.state = O.STATE_NAMES[s].toLowerCase();
        const main = el.querySelector('.orb-state') || el, sub = el.querySelector('.orb-note');
        if (main.textContent !== text) main.textContent = text;
        if (sub && sub.textContent !== note) sub.textContent = note;
      }
      for (const el of document.querySelectorAll('[data-flow-counts]')) {
        const t = `↑ ${this.counts.out} out · ↓ ${this.counts.in} in`;
        if (el.textContent !== t) el.textContent = t;
      }
      this.announce(note ? `${text}. ${note}` : text);
      if (force && this.prefs.motion !== 'full') this.drawOrb();
      this.kick();
    }
    /** Live-region announcement for important state changes only; throttled, never per particle or byte. */
    announce(text) {
      if (text === this.lastSpoken) return;
      clearTimeout(this.announceTimer);
      const wait = Math.max(0, 1500 - (performance.now() - this.lastAnnounceAt));
      this.announceTimer = setTimeout(() => {
        const live = document.getElementById('orb-live');
        if (live && text !== this.lastSpoken) { live.textContent = text; this.lastSpoken = text; this.lastAnnounceAt = performance.now(); }
      }, wait);
    }
    setAlert(text, ms) { this.alert = { text, until: performance.now() + (ms || 6000) }; this.render(true); setTimeout(() => this.render(), (ms || 6000) + 30); }
    setNote(text, ms) { this.note = { text, until: performance.now() + (ms || 8000) }; this.render(); setTimeout(() => this.render(), (ms || 8000) + 30); }

    /** Real-event signal entry point (see motion_state.js for the source mapping). */
    signal(type, d) {
      d = d || {};
      const origin = d.origin === 'test' || d.origin === 'replay' || d.origin === 'simulated' ? d.origin : 'live';
      const prefix = origin === 'test' ? 'TEST' : origin === 'replay' ? 'REPLAY' : origin === 'simulated' ? 'SIM' : '';
      switch (type) {
        case 'model_inference_started': this.thinking.add(d.corr || 'model'); break;
        case 'model_inference_finished': this.thinking.delete(d.corr || 'model'); break;
        case 'voice_capture_started': this.listening = true; break;
        case 'voice_capture_stopped': this.listening = false; this.orb.setLevel(0); break;
        case 'voice_level': if (this.listening) this.orb.setLevel(d.level); break;
        case 'voice_denied': this.listening = false; this.setAlert('Microphone unavailable or permission refused · nothing was recorded'); break;
        case 'speech_started': this.speaking = true; break;
        case 'speech_ended': this.speaking = false; break;
        case 'runtime_offline': this.offline = true; this.thinking.clear(); break;
        case 'runtime_online': this.offline = false; break;
        case 'transport_outbound':
        case 'transport_inbound': {
          const dir = type === 'transport_outbound' ? F.OUT : F.IN;
          if (dir === F.OUT) this.counts.out++; else this.counts.in++;
          if (origin === 'test') { this.testInFlight++; this.testBannerUntil = performance.now() + 3000; this.showBanner(); }
          if (this.prefs.motion === 'full' && this.prefs.showFlows && !document.hidden) {
            const point = d.target && d.target.isConnected ? centerOf(d.target) : null;
            this.flow.enqueue({ dir, label: d.label, bytes: d.bytes, corr: d.corr, prefix, point, showLabel: this.prefs.flowLabels });
          } else this.orb.bump(dir === F.OUT ? 0.3 : 0.2);
          break;
        }
        case 'proposal_ready': this.orb.pulse(false); this.setNote(d.text || 'Preview ready · nothing has run yet'); break;
        case 'permission_requested': this.setNote(d.text || 'Waiting for your approval · nothing has run yet', 60000); break;
        case 'companion_applied_revision': this.orb.pulse(false); this.setNote(d.text || 'Interface installed on the device · no physical action has run'); break;
        case 'invoke_refused': this.flow.cancel(d.corr); this.thinking.delete(d.corr); this.setAlert('Refused' + (d.reason ? ' · ' + d.reason : '')); break;
        case 'oracle_success': this.orb.pulse(true); this.setNote((prefix ? prefix + ' · ' : '') + (d.text || 'Verified by an independent read-back')); break;
        case 'outcome_uncertain': this.setAlert((prefix ? prefix + ' · ' : '') + (d.text || 'Result not confirmed · it will not be retried automatically'), 9000); break;
        case 'action_failed': this.setAlert((prefix ? prefix + ' · ' : '') + (d.text || 'Failed · nothing was confirmed')); break;
        case 'restored': this.orb.pulse(false); this.setNote(d.text || 'Restored to the recorded previous value'); break;
        case 'grant_revoked': this.flow.cancel(d.corr); this.setNote(d.text || 'Revoked · new presses are refused'); break;
        default: return;
      }
      this.render();
    }
    /** Motion test harness: show one orb state for a few seconds, labelled TEST everywhere. */
    testState(name, ms) {
      if (!(name in O)) return;
      if (!this.test) this.testInFlight++;
      this.test = { state: O[name], until: performance.now() + (ms || 4000) };
      this.testBannerUntil = this.test.until;
      this.showBanner(); this.render(true); setTimeout(() => this.render(true), (ms || 4000) + 30);
    }
    showBanner() {
      const b = document.getElementById('motion-test-banner');
      const left = (this.testBannerUntil || 0) - performance.now();
      if (b) b.hidden = this.testInFlight <= 0 && left <= 0;
      if (left > 0) { clearTimeout(this.bannerTimer); this.bannerTimer = setTimeout(() => this.showBanner(), left + 20); }
    }

    // ---------- loop ----------
    needsFrames() {
      if (document.hidden) return false;
      const orbAnim = this.prefs.motion === 'full' && this.stage && this.stageVisible;
      return !!(orbAnim || (this.prefs.motion === 'full' && this.flow.busy()));
    }
    kick() {
      if (this.raf || !this.needsFrames()) return;
      if (!this.looping) { this.looping = true; this.loopStarts++; }
      this.raf = requestAnimationFrame(ts => this.tick(ts));
    }
    stop() { if (this.raf) cancelAnimationFrame(this.raf); this.raf = 0; this.lastTs = 0; this.looping = false; }
    tick(ts) {
      this.raf = 0;
      if (!this.needsFrames()) { this.lastTs = 0; this.looping = false; return; }
      const dt = this.lastTs ? Math.min(0.1, (ts - this.lastTs) / 1000) : 0.016;
      this.lastTs = ts; this.frames++;
      const flowing = this.flow.busy();
      const s = this.stateNow();
      // Idle orb without comets: 30 fps is enough (Low performance mode: always 30 fps).
      const minGap = (s === O.IDLE || s === O.OFFLINE) && !flowing || this.prefs.perf === 'low' ? 32 : 0;
      if (this.stage && this.stageVisible && this.prefs.motion === 'full' && ts - this.lastOrbDraw >= minGap) {
        const t0 = performance.now();
        this.orb.step(this.lastOrbDraw ? Math.min(0.05, (ts - this.lastOrbDraw) / 1000) : dt);
        this.drawOrb();
        this.lastOrbDraw = ts; this.orbFrames++;
        this.adapt(performance.now() - t0);
      }
      if (flowing || this.flowWasBusy) this.drawFlow(dt);
      this.flowWasBusy = flowing;
      if (s !== this.orb.state || (this.alert && this.alert.until < performance.now()) || (this.note && this.note.until < performance.now())) this.render();
      if (!this.needsFrames()) this.looping = false;
      this.kick();
    }
    adapt(cost) {
      this.costAvg = this.costAvg * 0.95 + cost * 0.05;
      if (this.prefs.perf === 'auto' || this.prefs.perf === 'balanced') {
        const limit = this.prefs.perf === 'balanced' ? 6 : 10;
        if (!this.lite && this.costAvg > limit && this.orbFrames > 60) this.lite = true;
        else if (this.lite && this.costAvg < limit * 0.4 && this.orbFrames % 600 === 0) this.lite = false;
      }
    }
    drawOrb() {
      if (!this.orbCanvas.width) return;
      const ctx = this.orbCanvas.getContext('2d'), d = this.dpr(), size = this.orbSize || this.orbCanvas.width / d;
      ctx.setTransform(d, 0, 0, d, 0, 0);
      this.orb.draw(ctx, size, size, this.lite);
    }
    drawFlow(dt) {
      const ctx = this.flowCanvas.getContext('2d'), d = this.dpr();
      ctx.setTransform(d, 0, 0, d, 0, 0);
      const before = this.flow.alive() + this.flow.queue.length;
      this.flow.frame(ctx, global.innerWidth, global.innerHeight, dt, this.orbGeometry(), () => this.orb.bump(0.45), performance.now());
      const after = this.flow.alive() + this.flow.queue.length;
      if (after === 0 && before >= 0 && this.testInFlight) { this.testInFlight = 0; this.showBanner(); }
    }

    /** Introspection for tests and diagnostics; never used for decisions. */
    debug() {
      return { rafActive: !!this.raf, loopStarts: this.loopStarts, frames: this.frames, orbFrames: this.orbFrames,
        comets: this.flow.alive(), queued: this.flow.queue.length, spawned: this.flow.spawnedTotal.slice(),
        state: O.STATE_NAMES[this.stateNow()], motion: this.prefs.motion, lite: this.lite,
        mounted: !!this.stage, stageVisible: this.stageVisible, counts: Object.assign({}, this.counts), orbCanvases: document.querySelectorAll('canvas.ob-orb-canvas').length,
        flowCanvases: document.querySelectorAll('canvas.ob-flow-layer').length };
    }
  }
  function centerOf(el) { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }

  if (!global.OBMotion) global.OBMotion = new MotionController();
})(window);
