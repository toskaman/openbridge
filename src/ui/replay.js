'use strict';
/* Campaign Three §5.6 + judge-C W3: scripted UI replay of the S5/S5b receipts.
   Read-only: this view performs exactly one GET (/api/demo-replay) and renders
   verbatim receipt data. No mutations, no model call, no hardware call. Every stage
   carries an unmissable SIMULATED chip; the view banner is always visible. */
function renderReplay(arg) {
  const root = document.querySelector('[data-view="replay"] .replay-body');
  if (!root) return;
  const STAGES = ['intent', 'model', 'proposal', 'validation', 'consent',
    'publish', 'action', 'verify', 'revoke'];
  const reduceMotion = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let bundle = null;
  let scenarioIdx = 0;
  let stageIdx = 0;
  let timer = null;
  let seen = 0;

  function el(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  }
  function chip(text, cls) { return el('span', text, 'tag ' + cls); }
  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
    const b = root.querySelector('[data-replay="play"]');
    if (b) b.textContent = 'Play';
  }
  function scenario() { return bundle.scenarios[scenarioIdx]; }
  function paint() {
    const sc = scenario();
    const dots = root.querySelector('.replay-dots');
    dots.replaceChildren();
    STAGES.forEach((id, i) => {
      const d = el('button', String(i + 1), 'replay-dot' + (i === stageIdx ? ' active' : '') + (i < seen ? ' seen' : ''));
      d.type = 'button';
      d.setAttribute('aria-label', 'Step ' + (i + 1) + ': ' + sc.stages[id].title);
      if (i === stageIdx) d.setAttribute('aria-current', 'step');
      d.addEventListener('click', () => { stop(); stageIdx = i; seen = Math.max(seen, i + 1); paint(); });
      dots.append(d);
    });
    const list = root.querySelector('.replay-stages');
    list.replaceChildren();
    STAGES.forEach((id, i) => {
      const st = sc.stages[id];
      const card = el('article', null, 'replay-stage' + (i === stageIdx ? ' active' : '') + (i < stageIdx ? ' past' : ''));
      card.dataset.stageIdx = String(i);
      const head = el('div', null, 'replay-stage-head');
      head.append(el('span', 'Step ' + (i + 1) + ' of 9', 'replay-stepnum'));
      head.append(el('h3', st.title));
      head.append(chip('SIMULATED', 'sim'));
      card.append(head);
      const dl = document.createElement('dl');
      dl.className = 'replay-facts';
      for (const [k, v] of st.facts) {
        dl.append(el('dt', k));
        dl.append(el('dd', v));
      }
      card.append(dl);
      card.append(el('p', 'Source: ' + st.source, 'replay-source'));
      list.append(card);
    });
    const active = list.querySelector('.replay-stage.active');
    if (active && !reduceMotion) active.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    const counter = root.querySelector('[data-replay="counter"]');
    if (counter) counter.textContent = 'Step ' + (stageIdx + 1) + ' of 9 · ' + sc.stages[STAGES[stageIdx]].title;
    const prev = root.querySelector('[data-replay="prev"]');
    const next = root.querySelector('[data-replay="next"]');
    if (prev) prev.disabled = stageIdx === 0;
    if (next) next.disabled = stageIdx === STAGES.length - 1;
  }
  function step(dir) {
    stop();
    stageIdx = Math.min(STAGES.length - 1, Math.max(0, stageIdx + dir));
    seen = Math.max(seen, stageIdx + 1);
    paint();
  }
  function play() {
    if (timer) { stop(); return; }
    if (stageIdx >= STAGES.length - 1) { stageIdx = 0; seen = 1; }
    const b = root.querySelector('[data-replay="play"]');
    if (b) b.textContent = 'Pause';
    timer = setInterval(() => {
      if (stageIdx >= STAGES.length - 1) { stop(); paint(); return; }
      stageIdx += 1;
      seen = Math.max(seen, stageIdx + 1);
      paint();
    }, 1400);
  }
  function pick(i) {
    stop();
    scenarioIdx = i;
    stageIdx = 0;
    seen = 1;
    for (const t of root.querySelectorAll('[data-scenario]')) {
      const on = Number(t.dataset.scenario) === i;
      t.classList.toggle('active', on);
      if (on) t.setAttribute('aria-current', 'true');
      else t.removeAttribute('aria-current');
    }
    root.querySelector('[data-replay="verdict"]').textContent = scenario().verdict;
    const limits = root.querySelector('[data-replay="limits"]');
    limits.replaceChildren();
    for (const line of scenario().honest_limits) limits.append(el('li', line));
    paint();
  }
  function build(data) {
    bundle = data.bundle;
    scenarioIdx = 0;
    stageIdx = 0;
    seen = 1;
    root.replaceChildren();
    const banner = el('div', null, 'replay-banner');
    banner.setAttribute('role', 'note');
    banner.append(chip('REPLAY', 'replay'));
    banner.append(chip('SIMULATED', 'sim'));
    const bt = el('p', null, 'replay-banner-text');
    bt.append(document.createTextNode(bundle.labels.banner + ' '));
    const strong = el('strong', 'Recorded ' + bundle.recorded + ' · ' + bundle.evidence_kind + '.');
    bt.append(strong);
    banner.append(bt);
    root.append(banner);
    const tabs = el('div', null, 'replay-tabs');
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', 'Recorded scenarios');
    bundle.scenarios.forEach((sc, i) => {
      const t = el('button', sc.title, 'replay-tab' + (i === 0 ? ' active' : ''));
      t.type = 'button';
      t.dataset.scenario = String(i);
      if (i === 0) t.setAttribute('aria-current', 'true');
      t.addEventListener('click', () => pick(i));
      tabs.append(t);
    });
    root.append(tabs);
    const verdict = el('p', bundle.scenarios[0].verdict, 'replay-verdict');
    verdict.dataset.replay = 'verdict';
    root.append(verdict);
    const controls = el('div', null, 'replay-controls');
    const prev = el('button', '← Prev', 'secondary');
    prev.type = 'button';
    prev.dataset.replay = 'prev';
    prev.addEventListener('click', () => step(-1));
    const playBtn = el('button', 'Play', 'primary');
    playBtn.type = 'button';
    playBtn.dataset.replay = 'play';
    playBtn.addEventListener('click', play);
    const next = el('button', 'Next →', 'secondary');
    next.type = 'button';
    next.dataset.replay = 'next';
    next.addEventListener('click', () => step(1));
    const counter = el('span', '', 'replay-counter');
    counter.dataset.replay = 'counter';
    counter.setAttribute('aria-live', 'polite');
    controls.append(prev, playBtn, next, counter);
    root.append(controls);
    root.append(el('div', null, 'replay-dots'));
    const list = el('div', null, 'replay-stages');
    root.append(list);
    const limHead = el('h3', 'Honest limits (from the proof docs)', 'replay-limits-title');
    root.append(limHead);
    const limits = el('ul', null, 'replay-limits');
    limits.dataset.replay = 'limits';
    for (const line of scenario().honest_limits) limits.append(el('li', line));
    root.append(limits);
    paint();
    if (arg === 'autoplay' && !reduceMotion) play();
  }
  root.replaceChildren(el('p', 'Loading the recorded S5/S5b receipts…', 'muted'));
  request('/api/demo-replay').then(build, (error) => {
    root.replaceChildren();
    const banner = el('div', null, 'replay-banner');
    banner.append(chip('REPLAY', 'replay'));
    banner.append(chip('SIMULATED', 'sim'));
    banner.append(el('p', 'Replay unavailable: ' + (error && error.message ? error.message : error), 'replay-banner-text'));
    root.append(banner);
  });
}
