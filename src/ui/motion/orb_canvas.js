'use strict';
/* OpenBridge orb — Canvas2D port of the Android Companion VoiceOrbView
   (companion/android/src/fr/openbridge/companion/VoiceOrbView.java).

   Same model: 18 latitudes x 46 longitudes = 828 sample points on a unit sphere, spun around Y and tilted
   around X, perspective-projected; noise displacement weighted toward the equator; radial core; three
   equatorial ribbons; expanding event ring; orbiting arcs while THINKING. Same six states and the same
   three-colour palettes (tests/unit/test_ui_v2.py parses the Java file and compares).

   This file only draws. It never decides anything, never fetches and never starts its own loop: the single
   MotionController owns the requestAnimationFrame loop and calls step() + draw(). */
(function (global) {
  const IDLE = 0, LISTENING = 1, THINKING = 2, SPEAKING = 3, ALERT = 4, OFFLINE = 5;
  const STATE_NAMES = ['IDLE', 'LISTENING', 'THINKING', 'SPEAKING', 'ALERT', 'OFFLINE'];
  /* Three colour stops per state: primary, secondary, highlight (VoiceOrbView.PALETTE, verbatim). */
  const PALETTE = [
    [[64, 196, 255], [124, 77, 255], [0, 229, 255]],     // idle: cyan / violet
    [[0, 229, 255], [41, 121, 255], [29, 233, 182]],     // listening: cyan / blue / mint
    [[179, 136, 255], [101, 31, 255], [0, 176, 255]],    // thinking: violet swirl
    [[255, 79, 216], [140, 91, 255], [255, 158, 94]],    // speaking: magenta / violet / amber
    [[255, 183, 77], [255, 110, 64], [255, 213, 79]],    // alert: amber
    [[96, 110, 140], [70, 78, 110], [120, 140, 170]],    // offline: dim steel
  ];
  const LAT = 18, LON = 46, N = LAT * LON;
  const VERIFIED_RING = [88, 225, 171];                  // --good token; ring only, never the comet colours

  const clamp255 = v => (v < 0 ? 0 : v > 255 ? 255 : Math.round(v));
  const rgba = (c, a) => `rgba(${clamp255(c[0])},${clamp255(c[1])},${clamp255(c[2])},${a < 0 ? 0 : a > 1 ? 1 : a.toFixed(3)})`;
  const mixWhite = (c, f) => [c[0] + (255 - c[0]) * f, c[1] + (255 - c[1]) * f, c[2] + (255 - c[2]) * f];

  class OrbRenderer {
    constructor() {
      this.ux = new Float32Array(N); this.uy = new Float32Array(N); this.uz = new Float32Array(N);
      this.lat01 = new Float32Array(N); this.lon01 = new Float32Array(N); this.poleW = new Float32Array(N);
      let i = 0;
      for (let a = 0; a < LAT; a++) {
        const th = Math.PI * (a + 0.5) / LAT;
        for (let b = 0; b < LON; b++, i++) {
          const ph = 2 * Math.PI * (b + (a % 2) * 0.5) / LON;
          this.ux[i] = Math.sin(th) * Math.cos(ph);
          this.uy[i] = Math.cos(th);
          this.uz[i] = Math.sin(th) * Math.sin(ph);
          this.lat01[i] = a / LAT; this.lon01[i] = b / LON;
          this.poleW[i] = Math.pow(Math.sin(th), 1.5);   // calmer poles: no loops where meridians converge
        }
      }
      this.state = IDLE;
      this.input = 0; this.burst = 0; this.pulseAt = -1e9; this.ringColor = null;
      this.col = PALETTE[IDLE].map(c => c.slice());
      this.level = 0; this.energy = 0; this.spin = 0; this.think = 0; this.speakMix = 0; this.listenMix = 0;
      this.t = 0;
    }
    setState(s) { if (s !== this.state && s >= 0 && s < PALETTE.length) { this.state = s; this.pulseAt = this.t; this.ringColor = null; } }
    /** Live amplitude 0..1 (mic RMS, speech envelope). */
    setLevel(l) { this.input = Math.max(0, Math.min(1, +l || 0)); }
    /** Something real happened: a ring ripples out. `verified` uses the verification colour for the ring only. */
    pulse(verified) { this.pulseAt = this.t; this.burst = Math.max(this.burst, 0.6); this.ringColor = verified ? VERIFIED_RING : null; }
    bump(b) { this.burst = Math.max(this.burst, Math.min(1, b)); }
    /** Jump colours to the state palette (static rendering: reduced motion / off). */
    settle() { for (let k = 0; k < 3; k++) this.col[k] = PALETTE[this.state][k].slice(); }

    step(dt) {
      dt = Math.min(0.05, Math.max(0, dt));
      this.t += dt;
      const s = this.state, t = this.t;
      const inp = this.input; this.input = inp * Math.pow(0.25, dt);
      const b = this.burst; this.burst = b * Math.pow(0.04, dt);
      let synth = 0;
      if (s === SPEAKING) synth = 0.28 + 0.30 * Math.abs(Math.sin(t * 8.7) * Math.sin(t * 3.1 + 1));
      else if (s === THINKING) synth = 0.18 + 0.08 * Math.sin(t * 2.4);
      else if (s === IDLE || s === OFFLINE) synth = 0.04 + 0.03 * Math.sin(t * 1.1);
      else if (s === ALERT) synth = 0.25 + 0.15 * Math.sin(t * 4);
      const target = Math.min(1, Math.max(inp, synth) + b * 0.6);
      this.level += (target - this.level) * Math.min(1, dt * (target > this.level ? 14 : 5));
      const base = s === OFFLINE ? 0.05 : s === IDLE ? 0.12 : s === THINKING ? 0.45 : 0.3;
      this.energy += (base + this.level * 0.7 - this.energy) * Math.min(1, dt * 4);
      this.think += ((s === THINKING ? 1 : 0) - this.think) * Math.min(1, dt * 3);
      this.speakMix += ((s === SPEAKING ? 1 : 0) - this.speakMix) * Math.min(1, dt * 3);
      this.listenMix += ((s === LISTENING ? 1 : 0) - this.listenMix) * Math.min(1, dt * 3);
      this.spin += dt * (0.25 + 1.6 * this.think + 0.6 * this.energy);
      const f = Math.min(1, dt * 3.5);
      for (let k = 0; k < 3; k++) for (let j = 0; j < 3; j++) this.col[k][j] += (PALETTE[s][k][j] - this.col[k][j]) * f;
      if (!Number.isFinite(this.level) || !Number.isFinite(this.energy)) { this.level = 0; this.energy = 0; }
    }

    tri(m, depth) {
      let a, bb, f;
      if (m < 0.5) { a = this.col[0]; bb = this.col[1]; f = m * 2; } else { a = this.col[1]; bb = this.col[2]; f = (m - 0.5) * 2; }
      f = f * f * (3 - 2 * f);
      const lift = 0.25 * depth * depth;                    // front particles catch the light
      return [(a[0] + (bb[0] - a[0]) * f) * (1 - lift) + 255 * lift, (a[1] + (bb[1] - a[1]) * f) * (1 - lift) + 255 * lift,
        (a[2] + (bb[2] - a[2]) * f) * (1 - lift) + 255 * lift];
    }

    /** Draw one frame into a context already scaled to CSS pixels. `lite` halves the particle count and drops
        ribbon strokes (adaptive performance); geometry, colours and semantics are unchanged. */
    draw(ctx, w, h, lite) {
      const t = this.t, s = this.state, col = this.col;
      const pulseAge = this.t - this.pulseAt;
      const pulse = pulseAge < 1.4 ? 1 - pulseAge / 1.4 : 0;
      const cx = w / 2, cy = h / 2;
      const R = Math.min(w, h) * 0.30 * (1 + 0.06 * this.level + 0.05 * pulse * pulse);
      ctx.clearRect(0, 0, w, h);
      if (!(R >= 1)) return;
      const density = Math.max(0.8, Math.min(1.6, R / 90));
      const prevOp = ctx.globalCompositeOperation;
      ctx.globalCompositeOperation = 'lighter';

      // Ambient halo
      const haloR = R * (2.0 + 0.5 * this.energy);
      let g = ctx.createRadialGradient(cx, cy, 0, cx, cy, haloR);
      g.addColorStop(0, rgba(col[1], 0.34 + 0.3 * this.energy)); g.addColorStop(0.45, rgba(col[0], 0.12 + 0.1 * this.energy)); g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, haloR, 0, 6.2832); ctx.fill();

      // Expanding event ring
      if (pulse > 0) {
        const pr = R * (1.05 + (1 - pulse) * 0.95);
        ctx.lineWidth = density * (1 + 3 * pulse);
        ctx.strokeStyle = rgba(this.ringColor || col[2], 0.55 * pulse); ctx.beginPath(); ctx.arc(cx, cy, pr, 0, 6.2832); ctx.stroke();
        ctx.strokeStyle = rgba(this.ringColor || col[0], 0.25 * pulse); ctx.beginPath(); ctx.arc(cx, cy, pr * 0.92, 0, 6.2832); ctx.stroke();
      }

      // 3D particle sphere
      const tilt = 0.42 + 0.12 * Math.sin(t * 0.35);
      const cY = Math.cos(this.spin), sY = Math.sin(this.spin), cX = Math.cos(tilt), sX = Math.sin(tilt);
      const amp = 0.035 + 0.26 * this.energy, focal = 3.2, think = this.think, level = this.level;
      const ux = this.ux, uy = this.uy, uz = this.uz, lat01 = this.lat01, lon01 = this.lon01, poleW = this.poleW;
      const stride = lite ? 2 : 1;
      for (let i = 0; i < N; i += stride) {
        const la = lat01[i], lo = lon01[i];
        const n = Math.sin(lo * 18.85 + t * 2.1 + la * 6.0) * Math.cos(la * 12.6 - t * 1.4) * 0.55
          + Math.sin(la * 25.1 + lo * 12.57 - t * 3.3) * (0.25 + 0.55 * level)
          + Math.sin(lo * 37.7 - t * 5.0 + la * 3.0) * 0.35 * think;
        const d = 1 + amp * n * poleW[i];
        const x = ux[i] * d, y = uy[i] * d, z = uz[i] * d;
        const x1 = x * cY + z * sY, z1 = -x * sY + z * cY;           // spin around Y
        const y2 = y * cX - z1 * sX, z2 = y * sX + z1 * cX;          // tilt around X
        const k = focal / (focal - z2);
        let depth = (z2 + 1.25) / 2.5;                               // 0 = back, 1 = front
        depth = depth < 0 ? 0 : depth > 1 ? 1 : depth;
        const mix = (lo + t * 0.04 + la * 0.3) % 1;
        const c = this.tri(mix, depth);
        const alpha = (0.10 + 0.85 * depth * depth) * (0.75 + 0.25 * this.energy);
        const r = density * (0.7 + 1.7 * depth) * k * (lite ? 1.25 : 1);
        ctx.fillStyle = rgba(c, alpha);
        const px = cx + x1 * R * k, py = cy + y2 * R * k;
        if (r < 1.1) ctx.fillRect(px - r, py - r, r * 2, r * 2);
        else { ctx.beginPath(); ctx.arc(px, py, r, 0, 6.2832); ctx.fill(); }
      }

      // Inner core
      const coreR = R * (0.62 + 0.18 * level);
      g = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
      g.addColorStop(0, rgba(mixWhite(col[2], 0.55), 0.55 + 0.35 * level)); g.addColorStop(0.35, rgba(col[0], 0.30)); g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, coreR, 0, 6.2832); ctx.fill();

      // Ribbons through the equator
      const span = R * 1.55;
      const ribbonAmp = R * (0.03 + 0.62 * level * (0.45 + 0.55 * Math.max(this.listenMix, this.speakMix)) + 0.10 * think);
      const steps = lite ? 40 : 72;
      for (let r = 0; r < 3; r++) {
        const freq = 1.6 + r * 0.55, speed = 2.4 + r * 1.3, ph = r * 2.1, a = ribbonAmp * (1 - r * 0.22);
        ctx.beginPath();
        for (let j = 0; j <= steps; j++) {
          const u = -1 + 2 * j / steps;
          const env = Math.pow(4 / (4 + Math.pow(u * 2.2, 4)), 4);
          const yv = Math.sin(u * Math.PI * freq + t * speed + ph) * a * env;
          if (j === 0) ctx.moveTo(cx + u * span, cy + yv); else ctx.lineTo(cx + u * span, cy + yv);
        }
        for (let j = steps; j >= 0; j--) {
          const u = -1 + 2 * j / steps;
          const env = Math.pow(4 / (4 + Math.pow(u * 2.2, 4)), 4);
          const yv = Math.sin(u * Math.PI * freq + t * speed + ph + 0.9) * a * env * 0.35;
          ctx.lineTo(cx + u * span, cy - yv);
        }
        ctx.closePath();
        ctx.fillStyle = this.fade(ctx, cx, span, col[r], 0.22 + 0.25 * level);
        ctx.fill();
        if (!lite) {
          ctx.strokeStyle = this.fade(ctx, cx, span, mixWhite(col[r], 0.25), 0.45 + 0.4 * level);
          ctx.lineWidth = density * 1.4; ctx.stroke();
        }
      }

      // Thinking: orbiting arcs
      if (think > 0.02) {
        const deg = Math.PI / 180;
        let ar = R * 1.22;
        ctx.lineCap = 'round';
        ctx.lineWidth = density * 2.2;
        ctx.strokeStyle = rgba(col[2], 0.75 * think);
        let st = ((t * 220) % 360) * deg; ctx.beginPath(); ctx.arc(cx, cy, ar, st, st + 70 * deg); ctx.stroke();
        ctx.strokeStyle = rgba(col[0], 0.55 * think);
        st = ((t * 220 + 180) % 360) * deg; ctx.beginPath(); ctx.arc(cx, cy, ar, st, st + 40 * deg); ctx.stroke();
        ar = R * 1.32; ctx.lineWidth = density * 1.2;
        ctx.strokeStyle = rgba(col[1], 0.4 * think);
        st = (360 - (t * 140) % 360) * deg; ctx.beginPath(); ctx.arc(cx, cy, ar, st, st + 110 * deg); ctx.stroke();
      }
      ctx.globalCompositeOperation = prevOp;
      void s;
    }

    /** Horizontal fade so ribbons melt into the halo instead of ending in a hard line. */
    fade(ctx, cx, span, c, a) {
      const g = ctx.createLinearGradient(cx - span, 0, cx + span, 0);
      const on = rgba(c, a), off = rgba(c, 0);
      g.addColorStop(0, off); g.addColorStop(0.3, on); g.addColorStop(0.7, on); g.addColorStop(1, off);
      return g;
    }
  }

  global.OBOrb = { OrbRenderer, PALETTE, STATE_NAMES, LAT, LON, POINTS: N, IDLE, LISTENING, THINKING, SPEAKING, ALERT, OFFLINE };
})(window);
