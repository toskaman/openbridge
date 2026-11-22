/* Benchmarks page: single-series horizontal bar charts drawn from data/benchmarks.json. */
(function () {
  'use strict';
  var t = function (k, en) { return window.obT ? window.obT(k, en) : en; };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]; }); };
  var fmt = function (n) { var fr = (window.OB_LANG === 'fr'); return fr ? String(n).replace('.', ',') : String(n); };
  var pct = function (n) { return fmt(n) + (window.OB_LANG === 'fr' ? '\u202f%' : '%'); };
  var data = null, tip;

  /* rows: [{label, value, shown, tip}] — one series, one colour; the label column carries identity. */
  function hbar(rows, max, ticks, unit) {
    var W = 560, L = 150, R = 70, row = 46, bar = 20, top = 6, H = top + rows.length * row + 26;
    var x = function (v) { return L + (W - L - R) * Math.max(0, v) / max; };
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">';
    ticks.forEach(function (v) {
      s += '<line class="axis" x1="' + x(v) + '" x2="' + x(v) + '" y1="' + top + '" y2="' + (H - 22) + '"/>' +
        '<text class="tick" x="' + x(v) + '" y="' + (H - 6) + '" text-anchor="middle">' + fmt(v) + (unit || '') + '</text>';
    });
    rows.forEach(function (r, i) {
      var y = top + i * row + (row - bar) / 2, x0 = L, x1 = x(r.value), w = Math.max(0, x1 - x0), rad = Math.min(4, w);
      s += '<text class="lbl" x="' + (L - 12) + '" y="' + (y + bar / 2 + 5) + '" text-anchor="end">' + esc(r.label) + '</text>';
      if (w > 0.5) s += '<path class="bar" tabindex="0" data-tip="' + esc(r.tip) + '" d="M' + x0 + ' ' + y + 'H' + (x1 - rad) + 'Q' + x1 + ' ' + y + ' ' + x1 + ' ' + (y + rad) + 'V' + (y + bar - rad) + 'Q' + x1 + ' ' + (y + bar) + ' ' + (x1 - rad) + ' ' + (y + bar) + 'H' + x0 + 'Z"/>';
      else s += '<rect class="bar" tabindex="0" data-tip="' + esc(r.tip) + '" x="' + x0 + '" y="' + y + '" width="2" height="' + bar + '"/>';
      s += '<text class="val" x="' + (Math.max(x1, x0 + 2) + 8) + '" y="' + (y + bar / 2 + 5) + '">' + esc(r.shown) + '</text>';
    });
    return s + '</svg>';
  }
  function table(head, rows) {
    return '<details><summary>' + t('bench.table', 'Show the data as a table') + '</summary><table><thead><tr>' + head.map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + rows.map(function (r) { return '<tr>' + r.map(function (c) { return '<td>' + esc(c) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table></details>';
  }
  function chart(id, title, sub, svg, tbl, note) {
    document.getElementById(id).innerHTML = '<h2>' + title + '</h2><p class="sub">' + sub + '</p>' + svg + (note ? '<p class="note">' + note + '</p>' : '') + tbl;
  }

  function render() {
    if (!data) return;
    var R = data.agent_planning.routes;
    var label = function (r) { return r.route === 'rules' ? t('bench.rules', 'Rules only') : r.label + ' ' + t('bench.local', '(local)'); };
    var src = function (p) { return '<a href="https://github.com/toskaman/openbridge/blob/main/' + p + '">' + t('bench.source', 'Source') + '</a>'; };

    var refused = R.reduce(function (a, r) { return a + r.unsafe_proposed; }, 0);
    document.getElementById('t1').textContent = t('num.tests', '2,400+');
    document.getElementById('t2').textContent = refused + '/' + refused;
    document.getElementById('t3').textContent = String(data.eval_1000.hard_fail.crashes);
    document.getElementById('t4').textContent = String(data.endurance.leaked_threads + data.endurance.leaked_sockets);

    chart('c1', t('bench.c1.h', 'Correct decisions, by AI route'),
      t('bench.c1.p', 'Same 30 planning cases, 3 repeats each. A hand-written rule is as accurate on this narrow task; the models add a grounded explanation. Results unfavourable to the models are kept on purpose.'),
      hbar(R.map(function (r) { return { label: label(r), value: r.correct_pct, shown: pct(r.correct_pct), tip: label(r) + ': ' + fmt(r.correct_pct) + ' ' + t('bench.c1.tip', 'correct, {v} % schema-valid, {n} attempts').replace('{v}', fmt(r.schema_valid_pct)).replace('{n}', r.attempts) }; }), 100, [0, 50, 100], window.OB_LANG === 'fr' ? '\u202f%' : '%'),
      table([t('bench.route', 'Route'), t('bench.correct', 'Correct'), t('bench.valid', 'Schema-valid'), t('bench.attempts', 'Attempts')], R.map(function (r) { return [label(r), pct(r.correct_pct), pct(r.schema_valid_pct), r.attempts]; })),
      t('bench.synth', 'Synthetic inputs, local models, $0.') + ' ' + src(data.agent_planning.source));

    chart('c2', t('bench.c2.h', 'Unsafe proposals, all refused by the safety gate'),
      t('bench.c2.p', 'Every fifth case hides an unsafe target (system UI, messaging). Whatever the route proposes, the deterministic gate refuses it: 100 % refused for every route.'),
      hbar(R.map(function (r) { return { label: label(r), value: r.unsafe_proposed, shown: r.unsafe_proposed + ' ' + t('bench.c2.of', 'proposed, all refused'), tip: label(r) + ': ' + r.unsafe_proposed + ' ' + t('bench.c2.tip', 'unsafe proposals out of {n} attempts, {p} % refused').replace('{n}', r.attempts).replace('{p}', fmt(r.unsafe_refused_pct)) }; }), 12, [0, 6, 12]),
      table([t('bench.route', 'Route'), t('bench.unsafe', 'Unsafe proposals'), t('bench.refused', 'Refused')], R.map(function (r) { return [label(r), r.unsafe_proposed, pct(r.unsafe_refused_pct)]; })),
      src(data.agent_planning.source));

    chart('c3', t('bench.c3.h', 'Median time to a plan'),
      t('bench.c3.p', 'On a desktop PC: Llama on the CPU, Glimmer on an RTX 4060 Ti. The rule answers in under a millisecond.'),
      hbar(R.map(function (r) { return { label: label(r), value: r.median_s, shown: r.median_s ? fmt(r.median_s) + ' s' : t('bench.c3.instant', 'under 1 ms'), tip: label(r) + ': ' + (r.median_s ? fmt(r.median_s) + ' s' : t('bench.c3.instant', 'under 1 ms')) }; }), 20, [0, 10, 20], ' s'),
      table([t('bench.route', 'Route'), t('bench.median', 'Median')], R.map(function (r) { return [label(r), r.median_s ? fmt(r.median_s) + ' s' : '< 1 ms']; })),
      src(data.agent_planning.source));

    var E = data.endurance;
    chart('c4', t('bench.c4.h', 'Command latency under a long session'),
      t('bench.c4.p', '360 discover, pair, dispatch and revoke cycles in {d} s, with injected faults. The maximum is one command queued behind a deliberate re-pairing drill.').replace('{d}', fmt(E.duration_s)),
      hbar([['p50', E.dispatch_ms.p50], ['p95', E.dispatch_ms.p95], [t('bench.max', 'max'), E.dispatch_ms.max]].map(function (p) { return { label: p[0], value: p[1], shown: fmt(p[1]) + ' ms', tip: p[0] + ': ' + fmt(p[1]) + ' ms' }; }), 300, [0, 150, 300], ' ms'),
      table([t('bench.measure', 'Measure'), t('bench.value', 'Value')], [['p50', E.dispatch_ms.p50 + ' ms'], ['p95', E.dispatch_ms.p95 + ' ms'], ['max', E.dispatch_ms.max + ' ms'], [t('bench.err', 'Error rate (injected faults only)'), pct(E.error_rate_pct)], [t('bench.shutdown', 'Graceful shutdown'), fmt(E.shutdown_s) + ' s']]),
      t('bench.sim', 'Simulated network, real OpenBridge code. Windows, Python 3.14.4.') + ' ' + src(E.source));

    var V = data.evidence, lv = V.by_level;
    var LV = [['real', t('lvl.real', 'Real hardware')], ['vm', t('lvl.vm', 'Virtual machines')], ['official', t('lvl.off', 'Official emulators')]];
    chart('c5', t('bench.c5.h', 'Verified runs, by proof level'),
      t('bench.c5.p', 'Each run passed an independent check on the device itself. Emulated results are counted apart and never as hardware proof.'),
      hbar(LV.map(function (p) { return { label: p[1], value: lv[p[0]] || 0, shown: String(lv[p[0]] || 0), tip: p[1] + ': ' + (lv[p[0]] || 0) }; }), 30, [0, 15, 30]),
      table([t('bench.level', 'Proof level'), t('bench.runs', 'Verified runs')], LV.map(function (p) { return [p[1], lv[p[0]] || 0]; })),
      '<a href="compatibility.html">' + t('bench.c5.link', 'See every run on the Compatibility page') + '</a>');

    var H = data.eval_1000.hard_fail;
    document.getElementById('c6').innerHTML = '<h2>' + t('bench.c6.h', 'Zero hard failures over 1,000 scripted turns') + '</h2><p class="sub">' +
      t('bench.c6.p', '200 conversations, 1,000 turns, run against the rules baseline. This run measures safety, not coverage: most requests are answered “unsupported”, which is the honest answer for that baseline.') + '</p>' +
      '<dl class="zeros">' + [[t('bench.c6.crash', 'Crashes'), H.crashes], [t('bench.c6.send', 'Unapproved external sends'), H.external_sends], [t('bench.c6.fake', 'Fabricated receipts'), H.fabricated_receipts], [t('bench.c6.unk', 'Unknown actions proposed'), H.unknown_skill_proposals]]
        .map(function (p) { return '<div><dt>' + esc(p[0]) + '</dt><dd>' + p[1] + '</dd></div>'; }).join('') + '</dl><p class="note">' + src(data.eval_1000.source) + '</p>';
  }

  document.addEventListener('DOMContentLoaded', function () {
    tip = document.createElement('div'); tip.className = 'tip'; tip.setAttribute('role', 'status'); document.body.appendChild(tip);
    var show = function (el, x, y) { tip.textContent = el.getAttribute('data-tip'); tip.style.left = (x + 14) + 'px'; tip.style.top = (y + 14) + 'px'; tip.style.opacity = 1; };
    document.addEventListener('mousemove', function (e) { var b = e.target.closest && e.target.closest('.bar'); if (b) show(b, e.clientX, e.clientY); else tip.style.opacity = 0; });
    document.addEventListener('focusin', function (e) { if (e.target.classList && e.target.classList.contains('bar')) { var r = e.target.getBoundingClientRect(); show(e.target, r.right, r.top); } });
    document.addEventListener('focusout', function () { tip.style.opacity = 0; });
    document.addEventListener('ob:lang', render);
    fetch('data/benchmarks.json').then(function (r) { return r.json(); }).then(function (j) { data = j; render(); })
      .catch(function () { document.getElementById('c1').innerHTML = '<p class="empty">' + t('bench.err2', 'The benchmark data could not be loaded. It is also in the repository: docs/benchmark/.') + '</p>'; });
  });
})();
