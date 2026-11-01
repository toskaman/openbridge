'use strict';
/* OpenBridge flow comets — Canvas2D port of the Android Companion FlowOverlayView
   (companion/android/src/fr/openbridge/companion/FlowOverlayView.java).

   OUT = amber #FFB040: leaves the orb and flies off-screen (or to a real target element).
   IN  = emerald #34FFAA: flies in from off-screen (or from a real source element) and dives into the orb.
   Quadratic Bézier paths with a bend, a 16-sample fading trail, a three-layer glow head and a small pill label
   "↑/↓ operation · size" (≤ 26 characters of operation, ≤ 8 labels at once, never on the orb or on each other).
   At most 48 comets alive and 256 queued; at most 4 spawned per direction per frame.

   This layer is visual only: comets are spawned by the MotionController exclusively from real events (or from
   the explicitly labelled TEST / REPLAY sources). The canvas is pointer-events:none and sits under dialogs. */
(function (global) {
  const IN = 0, OUT = 1;
  const MAX = 48, TRAIL = 16, QUEUE_MAX = 256, LABELS_MAX = 8;
  const C_OUT = [255, 176, 64], C_IN = [52, 255, 170];
  const hot = c => [c[0] + (255 - c[0]) * 0.65, c[1] + (255 - c[1]) * 0.65, c[2] + (255 - c[2]) * 0.65];
  const HOT = [hot(C_IN), hot(C_OUT)];
  const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
  const rgba = (c, a) => `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${clamp(a, 0, 1).toFixed(3)})`;

  function human(n) {
    if (n < 1024) return n + ' B';
    let v = n / 1024, u = 'KB';
    if (v >= 1024) { v /= 1024; u = 'MB'; }
    return (v < 10 ? v.toFixed(1) : String(Math.round(v))) + ' ' + u;
  }

  class Comet {
    constructor() {
      this.alive = false; this.labeled = false; this.dir = IN; this.t = 0; this.life = 1; this.size = 2;
      this.ax = 0; this.ay = 0; this.bx = 0; this.by = 0; this.cx = 0; this.cy = 0; this.tn = 0; this.label = '';
      this.tx = new Float32Array(TRAIL); this.ty = new Float32Array(TRAIL);
      this.pill = { l: 0, t: 0, r: 0, b: 0 }; this.pillOn = false; this.corr = null; this.kill = 0;
    }
  }

  class FlowRenderer {
    constructor(rand) {
      this.rand = rand || Math.random;
      this.comets = Array.from({ length: MAX }, () => new Comet());
      this.queue = [];
      this.msgs = [0, 0];
      this.lastLabel = ['', '']; this.lastLabelAt = [0, 0];
      this.spawnedTotal = [0, 0];
    }
    /** One real message crossed a link. Returns false when the bounded queue is full. */
    enqueue(ev) {
      if (this.queue.length >= QUEUE_MAX) return false;
      this.queue.push(ev);
      return true;
    }
    alive() { let n = 0; for (const c of this.comets) if (c.alive) n++; return n; }
    busy() { return this.queue.length > 0 || this.alive() > 0; }
    clear() { this.queue.length = 0; for (const c of this.comets) c.alive = false; }
    /** Refused / cancelled transaction: its comets stop quickly instead of completing. */
    cancel(corr) { if (!corr) return; for (const c of this.comets) if (c.alive && c.corr === corr) c.kill = 1; this.queue = this.queue.filter(e => e.corr !== corr); }

    spawn(e, orb, w, h, budget, now) {
      const dir = e.dir === OUT ? OUT : IN;
      this.msgs[dir]++;
      if (budget[dir] <= 0) return;
      budget[dir]--;
      let c = null, labeled = 0;
      for (const k of this.comets) { if (k.alive && k.labeled) labeled++; if (!c && !k.alive) c = k; }
      if (!c) return;
      const sector = e.sector || orb.sector || [0, Math.PI * 2];
      const ang = sector[0] + this.rand() * (sector[1] - sector[0]);
      const ux = Math.cos(ang), uy = Math.sin(ang);
      const reach = Math.hypot(w, h) * 0.8 + 60;
      const sx = orb.x + ux * orb.r * 0.98, sy = orb.y + uy * orb.r * 0.98;
      let ox = orb.x + ux * reach, oy = orb.y + uy * reach;
      if (e.point) { ox = e.point.x; oy = e.point.y; }         // a real, on-screen destination/source
      if (dir === OUT) { c.ax = sx; c.ay = sy; c.bx = ox; c.by = oy; } else { c.ax = ox; c.ay = oy; c.bx = sx; c.by = sy; }
      const dx = c.bx - c.ax, dy = c.by - c.ay, L = Math.hypot(dx, dy) + 1e-3;
      const bend = (0.10 + 0.16 * this.rand()) * L * (dir === OUT ? 1 : -1);
      c.cx = (c.ax + c.bx) / 2 - dy / L * bend; c.cy = (c.ay + c.by) / 2 + dx / L * bend;
      c.life = (dir === OUT ? 1.45 : 1.65) + this.rand() * 0.55;
      c.orbX = orb.x; c.orbY = orb.y; c.orbR = orb.r;   // anchor at spawn (diagnostics/tests)
      c.dir = dir; c.t = 0; c.tn = 0; c.alive = true; c.pillOn = false; c.corr = e.corr || null; c.kill = 0;
      const label = String(e.label || '?');
      const fresh = label !== this.lastLabel[dir] || now - this.lastLabelAt[dir] > 650;
      c.labeled = e.showLabel !== false && fresh && labeled < LABELS_MAX;
      const bytes = Math.max(0, +e.bytes || 0);
      c.size = (c.labeled ? 3.0 : 1.9) + Math.min(2.2, Math.log10(bytes + 1) * 0.32);
      if (c.labeled) {
        const name = label.length > 26 ? label.slice(0, 25) + '…' : label;
        c.label = (e.prefix ? e.prefix + ' ' : '') + (dir === OUT ? '↑ ' : '↓ ') + name + (bytes > 0 ? '  ·  ' + human(bytes) : '');
        this.lastLabel[dir] = label; this.lastLabelAt[dir] = now;
      }
      this.spawnedTotal[dir]++;
    }

    fadeOf(c) {
      if (c.dir === OUT) return clamp(c.t / 0.06, 0, 1) * clamp((1 - c.t) / 0.18, 0, 1);
      return clamp(c.t / 0.12, 0, 1) * clamp((1 - c.t) / 0.06, 0, 1);
    }

    /** Advance and draw. `orb` = {x, y, r, sector} in CSS px or null when the orb is not on screen.
        `onArrive(dir)` is called when an IN comet reaches the orb. Returns true while anything is in flight. */
    frame(ctx, w, h, dt, orb, onArrive, now) {
      ctx.clearRect(0, 0, w, h);
      const budget = [4, 4];
      while (this.queue.length && (budget[0] > 0 || budget[1] > 0)) {
        const e = this.queue.shift();
        if (orb) this.spawn(e, orb, w, h, budget, now); else this.msgs[e.dir === OUT ? OUT : IN]++;
      }
      let any = false;
      ctx.globalCompositeOperation = 'lighter';
      for (const c of this.comets) {
        if (!c.alive) continue;
        c.t += dt / c.life * (c.kill ? 4 : 1);
        if (c.kill) c.kill = Math.max(0.0001, c.kill - dt * 3);
        if (c.t >= 1) { if (c.dir === IN && !c.kill && onArrive) onArrive(IN); c.alive = false; continue; }
        any = true;
        const u = c.dir === OUT ? Math.pow(c.t, 1.6) : 1 - Math.pow(1 - c.t, 1.7);
        const a = (1 - u) * (1 - u), b = 2 * (1 - u) * u, d = u * u;
        const x = a * c.ax + b * c.cx + d * c.bx, y = a * c.ay + b * c.cy + d * c.by;
        const n = Math.min(TRAIL, c.tn + 1);
        for (let k = n - 1; k > 0; k--) { c.tx[k] = c.tx[k - 1]; c.ty[k] = c.ty[k - 1]; }
        c.tx[0] = x; c.ty[0] = y; c.tn = n;
        const col = c.dir === OUT ? C_OUT : C_IN;
        const f0 = this.fadeOf(c) * (c.kill ? c.kill : 1), shrink = c.dir === IN ? clamp((1 - c.t) / 0.25, 0.35, 1) : 1;
        for (let k = c.tn - 1; k >= 1; k--) {                 // continuous trail
          const x0 = c.tx[k], y0 = c.ty[k], x1 = c.tx[k - 1], y1 = c.ty[k - 1];
          const steps = Math.min(36, Math.floor(Math.hypot(x1 - x0, y1 - y0) / 2.2) + 1);
          for (let j = 0; j < steps; j++) {
            const uu = j / steps, f = 1 - (k - uu) / TRAIL;
            this.dot(ctx, x0 + (x1 - x0) * uu, y0 + (y1 - y0) * uu, c.size * shrink * (0.22 + 0.55 * f), col, 0.22 * f * f * f0);
          }
        }
        this.dot(ctx, x, y, c.size * 3.2 * shrink, col, 0.10 * f0);
        this.dot(ctx, x, y, c.size * 1.7 * shrink, col, 0.32 * f0);
        this.dot(ctx, x, y, c.size * 0.9 * shrink, HOT[c.dir], 0.95 * f0);
      }
      ctx.globalCompositeOperation = 'source-over';
      this.labels(ctx, w, h, orb);
      return any || this.queue.length > 0;
    }

    dot(ctx, x, y, r, col, a) {
      if (a <= 0.004 || !(r > 0.1)) return;
      ctx.fillStyle = rgba(col, a);
      ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
    }

    /* labels: beside the comet, never on the orb, never on each other */
    labels(ctx, w, h, orb) {
      ctx.font = '500 11px Inter, "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
      ctx.textBaseline = 'middle';
      const on = [];
      for (const c of this.comets) {
        c.pillOn = false;
        if (!c.alive || !c.labeled || c.tn < 2 || c.kill) continue;
        const al = this.fadeOf(c) * (c.dir === IN ? clamp((1 - c.t) / 0.3, 0, 1) : clamp((1 - c.t) / 0.45, 0, 1));
        if (al < 0.05) continue;
        const hx = c.tx[0], hy = c.ty[0];
        if (orb && Math.hypot(hx - orb.x, hy - orb.y) < orb.r * 1.45) continue;
        const vx = c.tx[0] - c.tx[1], vy = c.ty[0] - c.ty[1], L = Math.hypot(vx, vy) + 1e-3;
        const nx = -vy / L, ny = vx / L;
        const pw = ctx.measureText(c.label).width + 16, ph = 20;
        const px = hx + nx * 14 - (nx < 0 ? pw : 0), py = hy + ny * 14 - ph / 2;
        if (px < 4 || py < 4 || px + pw > w - 4 || py + ph > h - 4) continue;
        const p = { l: px, t: py, r: px + pw, b: py + ph };
        if (orb) {
          const qx = Math.max(p.l, Math.min(orb.x, p.r)), qy = Math.max(p.t, Math.min(orb.y, p.b));
          if (Math.hypot(qx - orb.x, qy - orb.y) < orb.r * 1.3) continue;
        }
        if (on.some(o => !(o.r < p.l || p.r < o.l || o.b < p.t || p.b < o.t))) continue;
        on.push(p); c.pillOn = true;
        const col = c.dir === OUT ? C_OUT : C_IN;
        ctx.fillStyle = `rgba(9,12,24,${(0.8 * al).toFixed(3)})`;
        roundRect(ctx, px, py, pw, ph, ph / 2); ctx.fill();
        ctx.strokeStyle = rgba(col, 0.7 * al); ctx.lineWidth = 1; ctx.stroke();
        ctx.fillStyle = rgba([Math.min(255, col[0] + 60), Math.min(255, col[1] + 40), Math.min(255, col[2] + 40)], al);
        ctx.fillText(c.label, px + 8, py + ph / 2 + 0.5);
      }
    }
  }
  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  global.OBFlow = { FlowRenderer, IN, OUT, MAX, TRAIL, QUEUE_MAX, LABELS_MAX, C_IN, C_OUT, human };
})(window);
