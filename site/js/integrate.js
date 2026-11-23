/* SPDX-License-Identifier: Apache-2.0
 * "Bring your device, leave with an integration": the page around integrate-core.js. Everything runs here;
 * the API description is never sent anywhere. */
(function () {
  'use strict';
  var t = function (k, en) { return window.obT ? window.obT(k, en) : en; };
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); };
  var kit = null, result = null, current = null;

  function loadKit() {
    if (kit) return Promise.resolve(kit);
    return fetch('data/integrate-kit.json').then(function (r) {
      if (!r.ok) throw new Error('integrate-kit.json: HTTP ' + r.status);
      return r.json();
    }).then(function (k) { kit = k; window.OBKit.setKit(k); return k; });
  }

  function allowed(v) {
    if (v === null || v === undefined) return '—';
    if (Array.isArray(v)) return v.map(function (x) { return '<code>' + esc(JSON.stringify(x)) + '</code>'; }).join(' ');
    return '<code>' + esc(v.min) + '…' + esc(v.max) + '</code>';
  }

  function showMap(spec) {
    var rows = [];
    Object.keys(spec.read.fields).forEach(function (k) {
      var f = spec.read.fields[k];
      rows.push(['read', t('int.k.read', 'Read'), k, 'GET ' + spec.read.path, f.unit ? '<span class="muted">' + esc(f.unit) + '</span>' : '']);
    });
    Object.keys(spec.writable).forEach(function (k) {
      var w = spec.writable[k];
      rows.push(['set', t('int.k.set', 'Setting'), k, w.method + ' ' + w.path, allowed(w.values)]);
    });
    Object.keys(spec.commands).forEach(function (k) {
      var c = spec.commands[k];
      rows.push(['cmd', t('int.k.cmd', 'Command'), k, c.method + ' ' + c.path, allowed(c.values)]);
    });
    Object.keys(spec.policy).forEach(function (k) {
      rows.push(['no', t('int.k.no', 'Refused'), k, '', '<span class="muted">' + esc(spec.policy[k]) + '</span>']);
    });
    $('map').innerHTML = rows.map(function (r) {
      return '<tr><td><span class="tag ' + r[0] + '">' + esc(r[1]) + '</span></td><td><code>' + esc(r[2]) + '</code></td><td>' +
        (r[3] ? '<code>' + esc(r[3]) + '</code>' : '') + '</td><td>' + r[4] + '</td></tr>';
    }).join('');
    $('skipped').innerHTML = spec.skipped.map(function (s) { return '<li>' + esc(t('int.k.skip', 'Left out:')) + ' ' + esc(s) + '</li>'; }).join('');
  }

  function showFile(path) {
    current = path;
    $('code').textContent = result.files[path];
    Array.prototype.forEach.call($('tabs').children, function (b) { b.setAttribute('aria-selected', String(b.dataset.path === path)); });
  }

  function showFiles() {
    $('tabs').innerHTML = Object.keys(result.files).map(function (p) {
      return '<button type="button" role="tab" data-path="' + esc(p) + '">' + esc(p.split('/').pop()) + '</button>';
    }).join('');
    showFile(Object.keys(result.files)[0]);
  }

  function generate() {
    $('err').textContent = '';
    var doc;
    try { doc = JSON.parse($('src').value); } catch (e) {
      $('err').textContent = t('int.e.json', 'This is not valid JSON. YAML descriptions: convert them to JSON first.');
      return;
    }
    loadKit().then(function () {
      try {
        result = window.OBKit.generate(doc, $('name').value, $('cat').value.trim().toLowerCase() || 'device');
      } catch (e) {
        $('err').textContent = e.message || String(e);
        $('out').hidden = true;
        return;
      }
      showMap(result.spec);
      showFiles();
      $('out').hidden = false;
      $('out').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }).catch(function (e) { $('err').textContent = e.message || String(e); });
  }

  /* ---------- a small "stored" zip writer (no compression, no library) ---------- */
  var CRC = (function () {
    var table = [];
    for (var n = 0; n < 256; n++) { var c = n; for (var k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; table[n] = c >>> 0; }
    return function (bytes) { var c = 0xFFFFFFFF; for (var i = 0; i < bytes.length; i++) c = table[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  })();

  function zip(files) {
    var enc = new TextEncoder(), parts = [], central = [], offset = 0;
    var u16 = function (v) { return [v & 0xFF, (v >>> 8) & 0xFF]; };
    var u32 = function (v) { return [v & 0xFF, (v >>> 8) & 0xFF, (v >>> 16) & 0xFF, (v >>> 24) & 0xFF]; };
    var d = new Date(), time = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
    var date = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
    Object.keys(files).forEach(function (path) {
      var name = enc.encode(path), data = enc.encode(files[path]), crc = CRC(data);
      var common = [].concat(u16(20), u16(0x0800), u16(0), u16(time), u16(date), u32(crc), u32(data.length), u32(data.length), u16(name.length), u16(0));
      var local = new Uint8Array([].concat(u32(0x04034b50), common));
      parts.push(local, name, data);
      central.push(new Uint8Array([].concat(u32(0x02014b50), u16(20), common, u16(0), u16(0), u16(0), u32(0), u32(offset))), name);
      offset += local.length + name.length + data.length;
    });
    var size = central.reduce(function (s, p) { return s + p.length; }, 0);
    var end = new Uint8Array([].concat(u32(0x06054b50), u16(0), u16(0), u16(Object.keys(files).length), u16(Object.keys(files).length), u32(size), u32(offset), u16(0)));
    return new Blob(parts.concat(central, [end]), { type: 'application/zip' });
  }

  function download(blob, name) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  function readFile(f) {
    if (!f) return;
    var r = new FileReader();
    r.onload = function () { $('src').value = r.result; guessName(); };
    r.readAsText(f);
  }

  function guessName() {
    try {
      var title = (JSON.parse($('src').value).info || {}).title;
      if (title) $('name').value = String(title).replace(/\(.*?\)|\b(local )?api\b/gi, '').replace(/\s+/g, ' ').trim().slice(0, 40);
    } catch (e) { /* not JSON yet */ }
  }

  function init() {
    var drop = $('drop');
    drop.addEventListener('click', function () { $('file').click(); });
    drop.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); } });
    $('file').addEventListener('change', function (e) { readFile(e.target.files[0]); });
    drop.addEventListener('dragover', function (e) { e.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', function () { drop.classList.remove('over'); });
    drop.addEventListener('drop', function (e) { e.preventDefault(); drop.classList.remove('over'); readFile(e.dataTransfer.files[0]); });
    $('src').addEventListener('change', guessName);
    $('example').addEventListener('click', function () {
      fetch('data/openapi-example.json').then(function (r) { return r.text(); }).then(function (txt) {
        $('src').value = txt; $('name').value = 'Acme Glow'; $('cat').value = 'lamp'; generate();
      });
    });
    $('go').addEventListener('click', generate);
    $('tabs').addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) showFile(b.dataset.path); });
    $('zip').addEventListener('click', function () {
      var files = {};
      Object.keys(result.files).forEach(function (p) { files[p] = result.files[p]; });
      files['tests/partners/__init__.py'] = '';
      download(zip(files), 'openbridge-' + result.slug + '.zip');
    });
    $('one').addEventListener('click', function () { download(new Blob([result.files[current]], { type: 'text/plain' }), current.split('/').pop()); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
