/* Compatibility page: filterable view of docs/DEVICE_EVIDENCE.json (generated into data/compatibility.json). */
(function () {
  'use strict';
  var t = function (k, en) { return window.obT ? window.obT(k, en) : en; };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]; }); };
  var CATS = [
    ['screens', 'compat.cat.screens', 'TVs and screens'], ['wearables', 'compat.cat.wearables', 'Wearables'],
    ['phones', 'compat.cat.phones', 'Phones'], ['robots', 'compat.cat.robots', 'Robots'],
    ['network', 'compat.cat.network', 'Network'], ['pcs', 'compat.cat.pcs', 'PCs'],
    ['cross', 'compat.cat.cross', 'Cross-device scenarios'], ['glasses', 'compat.cat.glasses', 'Smart glasses'],
    ['vms', 'compat.cat.vms', 'Virtual machines'], ['micro', 'compat.cat.micro', 'Microcontrollers']
  ];
  var LEVELS = {
    real: ['lvl.real', 'Real hardware', '#34d399'], vm: ['lvl.vm', 'Virtual machine', '#60a5fa'],
    official: ['lvl.off', 'Official emulator', '#c084fc'], emulated: ['lvl.emu', 'Emulator, hardware pending', '#facc15']
  };
  var INTEG = {
    NATIVE_COMPANION: ['compat.int.companion', 'OpenBridge companion app on the device'],
    HOST_APP_ADAPTER: ['compat.int.adapter', 'Adapter on the PC, using the device’s own interface'],
    PROTOCOL_ENDPOINT: ['compat.int.agent', 'Lightweight OpenBridge agent']
  };
  var data = null, filt = { cat: 'all', level: 'all', q: '' };

  function chip(group, value, label, count) {
    var on = filt[group] === value;
    return '<button class="chip" type="button" data-group="' + group + '" data-value="' + value + '" aria-pressed="' + on + '">' + esc(label) + (count != null ? ' <span style="color:var(--dim)">' + count + '</span>' : '') + '</button>';
  }
  function matches(d) {
    if (filt.cat !== 'all' && d.category !== filt.cat) return false;
    if (filt.level !== 'all' && d.level !== filt.level) return false;
    if (filt.q) {
      var hay = (d.name + ' ' + d.platform + ' ' + d.runs.map(function (r) { return r.operations.join(' '); }).join(' ')).toLowerCase();
      if (hay.indexOf(filt.q.toLowerCase()) === -1) return false;
    }
    return true;
  }
  function badge(level) { var L = LEVELS[level] || LEVELS.real; return '<span class="badge" style="--c:' + L[2] + '">' + esc(t(L[0], L[1])) + '</span>'; }
  function catName(c) { for (var i = 0; i < CATS.length; i++) if (CATS[i][0] === c) return t(CATS[i][1], CATS[i][2]); return c; }

  function rowHTML(d) {
    var runs = d.runs.length;
    var sub = catName(d.category) + (d.integration ? ', ' + esc(INTEG[d.integration] ? t(INTEG[d.integration][0], INTEG[d.integration][1]) : d.integration) : '');
    var right = runs ? t(runs === 1 ? 'compat.run1' : 'compat.runs', runs === 1 ? '1 verified run' : '{n} verified runs').replace('{n}', runs) + (d.last ? ', ' + t('compat.last', 'last on') + ' ' + d.last : '') : t('compat.pending', 'Hardware tests start when the pair arrives');
    var body;
    if (!runs) {
      body = '<div class="run"><p style="color:var(--muted)">' + t('compat.engo', '38 heads-up display features and 82 tests, validated in the HUD Studio emulator driven by the official ActiveLook app. Emulator results are never counted as hardware proof, so this device is not in the evidence registry yet.') + '</p><p class="ev"><a href="' + esc(d.link) + '">' + t('compat.engolink', 'Read the ENGO case study') + '</a></p></div>';
    } else {
      body = d.runs.map(function (r) {
        var ev = r.evidence.map(function (e) { return e.url ? '<a href="' + esc(e.url) + '">' + esc(e.label) + '</a>' : '<span>' + esc(e.label) + '</span>'; }).join(', ');
        return '<div class="run"><h4><span>' + esc(r.test) + '</span><time>' + esc(r.date) + '</time></h4>' +
          '<ul>' + r.operations.map(function (o) { return '<li>' + esc(o) + '</li>'; }).join('') + '</ul>' +
          (r.oracle ? '<p class="ev"><b>' + t('compat.oracle', 'Independent check') + ':</b> ' + esc(r.oracle) + '</p>' : '') +
          (r.limitations.length ? '<p class="lim"><b>' + t('compat.limits', 'Known limits') + ':</b> ' + r.limitations.map(esc).join('; ') + '</p>' : '') +
          (ev ? '<p class="ev"><b>' + t('compat.evidence', 'Evidence') + ':</b> ' + ev + '</p>' : '') + '</div>';
      }).join('');
    }
    return '<details class="devrow"><summary><div><h3>' + esc(d.name) + '</h3><p>' + sub + '</p></div>' + badge(d.level) + '<span class="runs">' + right + '</span></summary><div class="body">' + body + '</div></details>';
  }

  function render() {
    if (!data) return;
    var counts = {}; data.devices.forEach(function (d) { counts[d.category] = (counts[d.category] || 0) + 1; });
    var cats = chip('cat', 'all', t('compat.all', 'All devices'), data.devices.length) + CATS.filter(function (c) { return counts[c[0]]; }).map(function (c) { return chip('cat', c[0], t(c[1], c[2]), counts[c[0]]); }).join('');
    var lv = chip('level', 'all', t('compat.anyproof', 'Any proof level')) + Object.keys(LEVELS).map(function (k) { return chip('level', k, t(LEVELS[k][0], LEVELS[k][1])); }).join('');
    document.getElementById('catChips').innerHTML = cats;
    document.getElementById('lvlChips').innerHTML = lv;
    var list = data.devices.filter(matches);
    document.getElementById('counter').textContent = t('compat.showing', 'Showing {n} of {total} devices, backed by {runs} verified runs.').replace('{n}', list.length).replace('{total}', data.devices.length).replace('{runs}', data.verified_runs);
    document.getElementById('devlist').innerHTML = list.length ? list.map(rowHTML).join('') : '<p class="empty">' + t('compat.none', 'No device matches these filters.') + '</p>';
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.addEventListener('click', function (e) {
      var b = e.target.closest('[data-group]'); if (!b) return;
      filt[b.getAttribute('data-group')] = b.getAttribute('data-value'); render();
    });
    document.getElementById('q').addEventListener('input', function (e) { filt.q = e.target.value.trim(); render(); });
    document.addEventListener('ob:lang', render);
    fetch('data/compatibility.json').then(function (r) { return r.json(); }).then(function (j) { data = j; render(); })
      .catch(function () { document.getElementById('devlist').innerHTML = '<p class="empty">' + t('compat.err', 'The device list could not be loaded. It is also available in the repository: docs/HARDWARE_TEST_MATRIX.md.') + '</p>'; });
  });
})();
