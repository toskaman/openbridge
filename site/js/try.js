/* OpenBridge in-browser simulation. No network, no AI model: a few fixed rules stand in for the AI. */
(function () {
  'use strict';
  var t = function (k, en) { return window.obT ? window.obT(k, en) : en; };
  var esc = function (s) { return String(s).replace(/[&<>"']/g, function (c) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]; }); };
  var norm = function (s) { return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); };
  var has = function (s, words) { return words.some(function (w) { return s.indexOf(w) !== -1; }); };
  var now = function () { var d = new Date(); return d.toTimeString().slice(0, 8); };

  var state = {
    tv: [], watch: [], volume: 22,
    robot: { status: 'docked', battery: 100, readAt: Date.now() },
    stale: false, chat: [], receipts: [], pending: null, busy: false
  };

  var CTRL = {
    start: { k: 'sim.ctrl.start', en: 'Start', primary: true, target: 'robot' },
    pause: { k: 'sim.ctrl.pause', en: 'Pause', target: 'robot' },
    dock: { k: 'sim.ctrl.dock', en: 'Dock', target: 'robot' },
    volup: { k: 'sim.ctrl.volup', en: 'Volume +', primary: true, target: 'tv' },
    voldown: { k: 'sim.ctrl.voldown', en: 'Volume −', target: 'tv' }
  };
  var STATUS = {
    docked: ['sim.st.docked', 'Docked, charging'], cleaning: ['sim.st.cleaning', 'Cleaning'],
    paused: ['sim.st.paused', 'Paused'], returning: ['sim.st.returning', 'Returning to dock']
  };
  var SUGGEST = [
    ['sim.s1', 'Put vacuum controls on the TV'], ['sim.s2', 'Turn my watch into a TV remote'],
    ['sim.s3', 'Send the robot back to its dock'], ['sim.s4', 'Remove the buttons'],
    ['sim.s5', "Change my router's Wi-Fi password"], ['sim.s6', 'Unlock the front door']
  ];

  /* ---------- the "AI": fixed rules, English and French ---------- */
  function understand(text) {
    var s = norm(text);
    var vac = has(s, ['vacuum', 'aspirateur', 'robot']);
    var tv = has(s, [' tv', 'tv ', 'tele', 'television']) || s === 'tv';
    var watch = has(s, ['watch', 'montre']);
    var ctrlWords = has(s, ['button', 'control', 'remote', 'bouton', 'commande', 'telecommande']);
    if (has(s, ['remove', 'delete', 'clear', 'retire', 'supprime', 'enleve', 'efface']) && (ctrlWords || has(s, ['everything', 'tout']))) return { kind: 'revoke' };
    if (has(s, ['router', 'box', 'freebox', 'wi-fi', 'wifi']) && has(s, ['password', 'change', 'set', 'setting', 'mot de passe', 'modifie', 'reglage', 'parametre'])) return { kind: 'policy' };
    if (has(s, ['door', 'porte', 'lock', 'serrure', 'oven', 'four', 'car ', 'voiture', 'garage', 'light', 'lumiere', 'lampe', 'thermostat', 'chauffage', 'camera'])) return { kind: 'unknown' };
    if (vac && tv) return { kind: 'install', screen: 'tv', ctrls: ['start', 'pause', 'dock'] };
    if (watch && (has(s, ['volume', 'remote', 'telecommande']) || tv)) return { kind: 'install', screen: 'watch', ctrls: ['volup', 'voldown'] };
    if (vac && has(s, ['dock', 'home', 'base', 'charge', 'back', 'range', 'rentre', 'retour', 'maison'])) return { kind: 'action', action: 'dock' };
    if (vac && has(s, ['pause', 'stop', 'arrete'])) return { kind: 'action', action: 'pause' };
    if (vac && has(s, ['start', 'clean', 'vacuum the', 'demarre', 'lance', 'nettoie', 'passe'])) return { kind: 'action', action: 'start' };
    if (vac && has(s, ['status', 'battery', 'doing', 'etat', 'batterie', 'fait', 'where', 'ou est'])) return { kind: 'status' };
    if (has(s, ['volume']) && (tv || has(s, ['up', 'down', 'monte', 'baisse', 'louder', 'plus fort']))) return { kind: 'action', action: has(s, ['down', 'baisse', 'lower', 'moins']) ? 'voldown' : 'volup' };
    return { kind: 'unclear' };
  }

  /* ---------- rendering ---------- */
  function msgHTML(m) {
    if (m.who === 'you') return '<div class="msg you"><span class="who">' + t('sim.you', 'You') + '</span>' + esc(m.text) + '</div>';
    var who = '<span class="who">OpenBridge</span>';
    var d = m.data || {};
    switch (m.kind) {
      case 'hello':
        return '<div class="msg ob">' + who + t('sim.hello', 'I found 3 devices nearby: a <b>living room TV</b>, a <b>Galaxy watch</b> and a <b>robot vacuum</b>. What should they do together?') + '</div>';
      case 'plan':
        var screen = d.screen === 'tv' ? t('sim.dev.tv', 'Living room TV') : t('sim.dev.watch', 'Galaxy watch');
        var names = d.ctrls.map(function (c) { return '<b>' + t(CTRL[c].k, CTRL[c].en) + '</b>'; }).join(', ');
        var drives = d.screen === 'tv' ? t('sim.dev.robot', 'Robot vacuum') : t('sim.dev.tv', 'Living room TV');
        var html = '<div class="msg ob">' + who + t('sim.plan.intro', 'Here is my plan. Nothing happens until you approve.') +
          '<ul><li>' + t('sim.plan.add', 'Add {n} buttons to the {screen}: {names}').replace('{n}', d.ctrls.length).replace('{screen}', screen).replace('{names}', names) + '</li>' +
          '<li>' + t('sim.plan.drive', 'They will control the {target}, and nothing else.').replace('{target}', drives) + '</li>' +
          '<li>' + t('sim.plan.check', 'After each press, I read the device back before saying “done”.') + '</li></ul>';
        if (m.open) html += '<div class="row"><button class="btn btn-main" data-act="approve">' + t('sim.approve', 'Approve') + '</button><button class="btn btn-ghost" data-act="decline">' + t('sim.decline', 'Decline') + '</button></div>';
        else html += '<p style="margin-top:8px;color:var(--dim)">' + (m.result === 'approved' ? t('sim.approved', 'Approved.') : t('sim.declined', 'Declined. Nothing was changed.')) + '</p>';
        return html + '</div>';
      case 'actionplan':
        var html2 = '<div class="msg ob">' + who + t('sim.act.intro', 'I can do that: {action}. Approve?').replace('{action}', '<b>' + actName(d.action) + '</b>');
        if (m.open) html2 += '<div class="row"><button class="btn btn-main" data-act="approve">' + t('sim.approve', 'Approve') + '</button><button class="btn btn-ghost" data-act="decline">' + t('sim.decline', 'Decline') + '</button></div>';
        else html2 += '<p style="margin-top:8px;color:var(--dim)">' + (m.result === 'approved' ? t('sim.approved', 'Approved.') : t('sim.declined', 'Declined. Nothing was changed.')) + '</p>';
        return html2 + '</div>';
      case 'installed':
        return '<div class="msg ob">' + who + t('sim.installed', 'Done, verified: the {screen} now shows the new buttons. Try pressing one.').replace('{screen}', d.screen === 'tv' ? t('sim.dev.tv', 'Living room TV') : t('sim.dev.watch', 'Galaxy watch')) + '</div>';
      case 'revoked':
        return '<div class="msg ob">' + who + t('sim.revoked', 'Removed. Verified: no OpenBridge buttons are left on any device, and old presses are now denied.') + '</div>';
      case 'nothing':
        return '<div class="msg ob">' + who + t('sim.nothing', 'There are no OpenBridge buttons to remove right now.') + '</div>';
      case 'policy':
        return '<div class="msg ob refuse">' + who + t('sim.policy', '<b>Refused.</b> Router settings are read-only by policy: OpenBridge can list what is on your network, but never changes the router. Nothing was sent.') + '</div>';
      case 'unknown':
        return '<div class="msg ob refuse">' + who + t('sim.unknown', '<b>I can’t do that.</b> There is no such device among the 3 I discovered, and OpenBridge never acts on a device it hasn’t found and verified.') + '</div>';
      case 'status':
        return '<div class="msg ob">' + who + t('sim.status', 'Robot vacuum: <b>{st}</b>, battery {b}%. Read from the robot just now; nothing was changed.').replace('{st}', stName(state.robot.status)).replace('{b}', state.robot.battery) + '</div>';
      case 'stale':
        return '<div class="msg ob refuse">' + who + t('sim.stale', '<b>Refused.</b> The robot’s state has not been confirmed recently, so I won’t act on it. Nothing was sent. Turn off “stale state” and try again.') + '</div>';
      case 'unclear':
        return '<div class="msg ob">' + who + t('sim.unclear', 'I’m not sure what you mean. In this simulation I understand requests like the suggestions above.') + '</div>';
    }
    return '';
  }
  function actName(a) {
    return ({ start: t('sim.a.start', 'start the robot vacuum'), pause: t('sim.a.pause', 'pause the robot vacuum'), dock: t('sim.a.dock', 'send the robot vacuum to its dock'),
      volup: t('sim.a.volup', 'turn the TV volume up'), voldown: t('sim.a.voldown', 'turn the TV volume down') })[a];
  }
  function stName(s) { return t(STATUS[s][0], STATUS[s][1]); }

  function rcHTML(r) {
    var ic = r.state === 'ok' ? '✓' : r.state === 'no' ? '!' : '…';
    return '<li class="rc ' + r.state + '"><span class="ic" aria-hidden="true">' + ic + '</span><div><b>' + t(r.k, r.en).replace('{x}', r.x || '') + '</b>' +
      (r.dk ? '<p>' + t(r.dk, r.den).replace('{x}', r.dx || '') + '</p>' : '') + '</div><time>' + r.time + '</time></li>';
  }

  function render() {
    var chat = document.getElementById('chat');
    chat.innerHTML = state.chat.map(msgHTML).join('');
    chat.scrollTop = chat.scrollHeight;
    var ctrlBtn = function (c, where) { return '<button class="ctrl' + (CTRL[c].primary ? ' primary' : '') + '" data-ctrl="' + c + '" data-where="' + where + '">' + t(CTRL[c].k, CTRL[c].en) + '</button>'; };
    document.getElementById('tvCtrls').innerHTML = state.tv.length ? state.tv.map(function (c) { return ctrlBtn(c, 'tv'); }).join('') : '<span class="empty">' + t('sim.noctrl', 'No OpenBridge buttons yet') + '</span>';
    document.getElementById('watchCtrls').innerHTML = state.watch.length ? state.watch.map(function (c) { return ctrlBtn(c, 'watch'); }).join('') : '<span class="empty">' + t('sim.noctrlw', 'No buttons yet') + '</span>';
    document.getElementById('tvState').textContent = t('sim.volume', 'Volume') + ' ' + state.volume;
    var robot = document.getElementById('robot');
    robot.className = 'dev robot ' + (state.robot.status === 'cleaning' ? 'cleaning' : state.robot.status === 'docked' ? 'docked' : '');
    document.getElementById('robotStatus').textContent = stName(state.robot.status);
    document.getElementById('robotBattery').textContent = state.robot.battery + '%';
    document.getElementById('robotFresh').textContent = state.stale ? t('sim.notfresh', 'Not confirmed recently') : t('sim.fresh', 'Confirmed just now');
    document.getElementById('rcList').innerHTML = state.receipts.length ? state.receipts.map(rcHTML).join('') : '<li class="empty">' + t('sim.norc', 'Receipts appear here: what was asked, approved, done and verified.') + '</li>';
    var chips = document.getElementById('chips');
    chips.innerHTML = SUGGEST.map(function (s) { return '<button class="chip" type="button" data-say="' + esc(t(s[0], s[1])) + '">' + esc(t(s[0], s[1])) + '</button>'; }).join('');
    document.querySelectorAll('[data-act]').forEach(function (b) { b.disabled = state.busy; });
  }

  function say(kind, data, extra) { var m = { who: 'ob', kind: kind, data: data || {} }; for (var k in extra || {}) m[k] = extra[k]; state.chat.push(m); return m; }
  function receipt(state_, k, en, x, dk, den, dx) { var r = { state: state_, k: k, en: en, x: x, dk: dk, den: den, dx: dx, time: now() }; state.receipts.unshift(r); return r; }
  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  /* ---------- flow ---------- */
  function ask(text) {
    text = (text || '').trim(); if (!text || state.busy) return;
    if (state.pending) { state.pending.open = false; state.pending.result = 'declined'; state.pending = null; }
    state.chat.push({ who: 'you', text: text });
    var it = understand(text);
    if (it.kind === 'install') state.pending = say('plan', { screen: it.screen, ctrls: it.ctrls }, { open: true });
    else if (it.kind === 'action') {
      if ((it.action === 'start' || it.action === 'pause' || it.action === 'dock') && state.stale) { say('stale'); receipt('no', 'sim.rc.refused', 'Refused: {x}', actName(it.action), 'sim.rc.stale', 'Device state not confirmed recently. Nothing was sent.'); }
      else state.pending = say('actionplan', { action: it.action }, { open: true });
    }
    else if (it.kind === 'revoke') {
      if (!state.tv.length && !state.watch.length) say('nothing');
      else { state.tv = []; state.watch = []; say('revoked'); receipt('ok', 'sim.rc.revoked', 'Buttons removed everywhere', '', 'sim.rc.revokedd', 'Verified: 0 OpenBridge buttons left on the TV and the watch.'); }
    }
    else if (it.kind === 'status') { say('status'); receipt('ok', 'sim.rc.read', 'Read the robot vacuum', '', 'sim.rc.readd', 'Read-only. Nothing was changed.'); }
    else if (it.kind === 'policy') { say('policy'); receipt('no', 'sim.rc.refused', 'Refused: {x}', t('sim.x.router', 'change router settings'), 'sim.rc.policy', 'Blocked by policy. Nothing was sent.'); }
    else say(it.kind);
    render();
  }

  async function approve() {
    var m = state.pending; if (!m) return;
    m.open = false; m.result = 'approved'; state.pending = null; state.busy = true; render();
    if (m.kind === 'plan') {
      var r = receipt('wait', 'sim.rc.install', 'Installing buttons on the {x}', m.data.screen === 'tv' ? t('sim.dev.tv', 'Living room TV') : t('sim.dev.watch', 'Galaxy watch'), 'sim.rc.wait', 'Sent. Reading the device back…');
      render(); await wait(900);
      state[m.data.screen] = m.data.ctrls.slice();
      r.state = 'ok'; r.k = 'sim.rc.installed'; r.en = 'Buttons installed on the {x}'; r.dk = 'sim.rc.installedd'; r.den = 'Done, verified: the screen reports {x} buttons.'; r.dx = String(m.data.ctrls.length);
      say('installed', { screen: m.data.screen });
    } else await run(m.data.action);
    state.busy = false; render();
  }
  function decline() { var m = state.pending; if (!m) return; m.open = false; m.result = 'declined'; state.pending = null; render(); }

  async function run(action) {
    var robotAction = action === 'start' || action === 'pause' || action === 'dock';
    if (robotAction && state.stale) {
      receipt('no', 'sim.rc.refused', 'Refused: {x}', actName(action), 'sim.rc.stale', 'Device state not confirmed recently. Nothing was sent.');
      say('stale'); render(); return;
    }
    var r = receipt('wait', 'sim.rc.doing', '{x}', capital(actName(action)), 'sim.rc.wait', 'Sent. Reading the device back…');
    render(); await wait(800);
    var read;
    if (action === 'start') { state.robot.status = 'cleaning'; read = stName('cleaning'); }
    if (action === 'pause') { state.robot.status = 'paused'; read = stName('paused'); }
    if (action === 'dock') { state.robot.status = 'returning'; render(); await wait(1100); state.robot.status = 'docked'; read = stName('docked'); }
    if (action === 'volup') { state.volume = Math.min(100, state.volume + 1); read = t('sim.volume', 'Volume') + ' ' + state.volume; }
    if (action === 'voldown') { state.volume = Math.max(0, state.volume - 1); read = t('sim.volume', 'Volume') + ' ' + state.volume; }
    if (robotAction) state.robot.readAt = Date.now();
    r.state = 'ok'; r.dk = 'sim.rc.verified'; r.den = 'Done, verified. Read back from the device: {x}'; r.dx = read;
  }
  function capital(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  async function press(c) {
    if (state.busy) return;
    state.busy = true; render();
    await run(c);
    state.busy = false; render();
  }

  document.addEventListener('DOMContentLoaded', function () {
    say('hello');
    var form = document.getElementById('askForm'), input = document.getElementById('askInput');
    form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); input.value = ''; });
    document.getElementById('chips').addEventListener('click', function (e) { var b = e.target.closest('[data-say]'); if (b) ask(b.getAttribute('data-say')); });
    document.getElementById('chat').addEventListener('click', function (e) {
      var b = e.target.closest('[data-act]'); if (!b) return;
      if (b.getAttribute('data-act') === 'approve') approve(); else decline();
    });
    document.querySelector('.stage').addEventListener('click', function (e) { var b = e.target.closest('[data-ctrl]'); if (b) press(b.getAttribute('data-ctrl')); });
    document.getElementById('stale').addEventListener('change', function (e) { state.stale = e.target.checked; render(); });
    document.getElementById('reset').addEventListener('click', function () {
      state.tv = []; state.watch = []; state.volume = 22; state.robot.status = 'docked'; state.chat = []; state.receipts = []; state.pending = null;
      state.stale = false; document.getElementById('stale').checked = false; say('hello'); render();
    });
    document.addEventListener('ob:lang', render);
    render();
  });
})();
