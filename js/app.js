// Izden PWA: student practice (evidence first), progress + QR export, teacher class report, paper mode.
import { t, tr, tv, setLang, getLang, LANGS } from './i18n.js';
import * as E from './engine.js';
import { renderBlocks, showEvidence, clearEvidence, evidenceMatches, evidenceLabel, displayOrder, esc } from './text.js';
import * as Q from './qr.js';

const app = document.getElementById('app');
// localStorage with an in-memory fallback (private mode / blocked storage): the app keeps working, a toast warns.
const mem = new Map();
let storageOk = true;
try { localStorage.setItem('izden.__t', '1'); localStorage.removeItem('izden.__t'); } catch (e) { storageOk = false; }
const LS = {
  get(k, d) {
    try { const v = storageOk ? localStorage.getItem('izden.' + k) : mem.get(k); return v ? JSON.parse(v) : d; } catch (e) { return d; }
  },
  set(k, v) {
    const s = JSON.stringify(v);
    mem.set(k, s);
    if (!storageOk) return;
    try { localStorage.setItem('izden.' + k, s); } catch (e) {
      // first failure: keep everything already saved (profile, progress) in memory before switching over
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key && key.startsWith('izden.') && !mem.has(key.slice(6))) mem.set(key.slice(6), localStorage.getItem(key));
        }
      } catch (e2) { /* storage unreadable too */ }
      mem.set(k, s);
      storageOk = false;
      toast(t('noStorage'));
    }
  },
  del(k) { mem.delete(k); try { if (storageOk) localStorage.removeItem('izden.' + k); } catch (e) { /* ignore */ } },
};

let params = null;
const banks = {};
let passport = {};
let trapCards = {};

async function loadJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + ' ' + r.status);
  return r.json();
}
async function bank(lang) {
  if (!banks[lang]) banks[lang] = (await loadJSON(`data/bank.${lang}.json`)).units;
  return banks[lang];
}

// ---------- profile & state ----------
const profile = () => LS.get('profile', null);
function loadState(lang) {
  const s = LS.get('state.' + lang, null);
  if (!s || s.v !== 2) return E.newState(params);
  if (!s.exposure) s.exposure = E.newState(params).exposure; // saved before exposure counting existed
  return s;
}
const saveState = (lang, s) => LS.set('state.' + lang, s);
const pct = p => Math.round(p * 100);

// ---------- shell ----------
function renderShell() {
  const lang = getLang();
  document.getElementById('lang-switch').innerHTML = Object.entries(LANGS)
    .map(([k, v]) => `<button type="button" data-lang="${k}" aria-pressed="${k === lang}">${k === 'kk' ? 'Қаз' : 'Рус'}<span class="sr">${v}</span></button>`).join('');
  document.getElementById('nav').innerHTML = [
    ['#/practice', 'navPractice', 'M4 5h7a3 3 0 0 1 3 3v11a2 2 0 0 0-2-2H4zM20 5h-4a3 3 0 0 0-3 3'],
    ['#/progress', 'navProgress', 'M4 19V9M10 19V5M16 19v-7M22 19H2'],
    ['#/teacher', 'navTeacher', 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h3v3h-3zM18 18h3v3h-3z'],
    ['#/print', 'navPrint', 'M6 9V3h12v6M6 18H4v-7h16v7h-2M8 14h8v7H8z'],
  ].map(([h, k, d]) => `<a href="${h}" data-route="${h}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg><span>${t(k)}</span></a>`).join('');
  document.getElementById('tagline').textContent = t('appTagline');
  markNav();
  updateNetPill();
}
function markNav() {
  const r = location.hash.split('/').slice(0, 2).join('/') || '#/';
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.dataset.route === r));
}
function updateNetPill() {
  const el = document.getElementById('net');
  const ready = !!(navigator.serviceWorker && navigator.serviceWorker.controller);
  // compact on phones: icon + short word; the full sentence is in title / for screen readers
  const set = (cls, short, full) => {
    el.className = cls;
    el.title = full;
    el.setAttribute('aria-label', full);
    el.innerHTML = `<span class="pill-ico" aria-hidden="true"></span><span class="pill-short">${esc(short)}</span><span class="pill-long">${esc(full)}</span>`;
  };
  if (!navigator.onLine) set('pill off', t('offlineShort'), t('offlineNow'));
  else if (ready) set('pill ok', t('offlineShort'), t('offlineReady'));
  else { el.innerHTML = ''; el.className = 'pill'; el.removeAttribute('title'); }
}

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove('show'), 2600);
}

// ---------- router ----------
const routes = { '': home, practice, progress, teacher, print: printPage, trap: trapPage };
let cleanup = null;
async function route() {
  if (cleanup) { try { cleanup(); } catch (e) { /* ignore */ } cleanup = null; }
  const parts = location.hash.replace(/^#\/?/, '').split('/');
  const name = parts[0] || '';
  const fn = routes[name] || home;
  if (!profile() && ['practice', 'progress'].includes(name)) { location.hash = '#/'; return; }
  markNav();
  app.innerHTML = `<p class="muted pad">${t('loading')}</p>`;
  try {
    await fn(...parts.slice(1));
  } catch (e) {
    console.error(e);
    app.innerHTML = `<div class="card pad"><p>${t('loadError')}</p><p class="muted small">${esc(e.message)}</p></div>`;
  }
  window.scrollTo(0, 0);
}

// ---------- home / onboarding ----------
async function home() {
  const pr = profile();
  const lang = getLang();
  const modes = tv('modes').map(([h, p], i) => `<li><span class="mode-ico m${i}" aria-hidden="true"></span><div><b>${esc(h)}</b><p>${esc(p)}</p></div></li>`).join('');
  let top;
  if (!pr) {
    top = `<section class="hero">
      <div class="pick-lang" role="group" aria-label="Тіл / Язык">${Object.entries(LANGS).map(([k, v]) => `<button type="button" data-pick="${k}" aria-pressed="${k === lang}">${v}</button>`).join('')}</div>
      <p class="bilingual"><span lang="kk">Алдымен дәлелде → сосын жауап бер · интернетсіз жұмыс істейді · тапсырмаларды ИИ жасап, тексерген</span>
        <span lang="ru">Докажи → ответь · работает без интернета · банк заданий от ИИ с проверкой</span></p>
      <h1>${t('welcomeTitle')}</h1>
      <p class="lead">${t('welcomeLead')}</p>
      <form id="onb" class="card form">
        <label>${t('yourName')}<input name="name" required maxlength="24" autocomplete="given-name" placeholder="${t('namePh')}"></label>
        <div>
          <label>${t('grade')}<select name="grade">${[7, 8, 9].map(g => `<option value="${g}" ${g === 8 ? 'selected' : ''}>${t('gradeN', g)}</option>`).join('')}</select></label>
        </div>
        <button class="btn primary big" type="submit">${t('start')}</button>
        <p class="muted small">${t('offlineNote')}</p>
      </form></section>`;
  } else {
    const st = loadState(lang);
    top = `<section class="hero">
      <h1>${esc(pr.name)}</h1>
      <p class="lead">${t('gradeN', pr.grade)} · ${LANGS[lang]}</p>
      ${skillBars(st, true)}
      <a class="btn primary big" href="#/practice">${st.answered ? t('continue') : t('start')}</a>
      <button class="btn ghost" id="edit-prof" type="button">${t('changeProfile')}</button>
    </section>`;
  }
  app.innerHTML = `${top}
    <section class="card pad"><h2>${t('modesTitle')}</h2><ul class="modes">${modes}</ul></section>
    <section class="card pad about"><p>${t('aboutAi')}</p>${lang === 'kk' ? `<p class="muted small">${t('kkNote')}</p>` : ''}</section>`;
  app.querySelectorAll('[data-pick]').forEach(b => b.addEventListener('click', () => switchLang(b.dataset.pick)));
  const f = document.getElementById('onb');
  if (f) f.addEventListener('submit', ev => {
    ev.preventDefault();
    const d = new FormData(f);
    const p = { name: String(d.get('name')).trim().slice(0, 24), grade: +d.get('grade'), lang: getLang() };
    LS.set('profile', p);
    switchLang(p.lang, false);
    location.hash = '#/practice';
  });
  const ed = document.getElementById('edit-prof');
  if (ed) ed.addEventListener('click', () => {
    // a new student on the same phone must not inherit (and send by QR) the previous student's progress
    if (!confirm(t('changeProfileConfirm'))) return;
    ['profile', 'state.kk', 'state.ru', 'session.kk', 'session.ru'].forEach(k => LS.del(k));
    home();
  });
}

function skillBars(st, compact = false) {
  return `<div class="skills${compact ? ' compact' : ''}">${E.SKILLS.map(s => {
    const p = st.skills[s].p;
    const rated = st.skills[s].n > 0;
    return `<div class="skill sk-${s}${rated ? '' : ' unrated'}" data-skill="${s}"><div class="skill-head"><span>${tr('skills', s)}</span><b title="${rated ? '' : t('notRated')}">${rated ? pct(p) + '%' : '—'}</b></div>
      <div class="meter"><span style="width:${rated ? pct(p) : 0}%"></span></div>${rated || compact ? '' : `<p class="muted small">${t('notRated')}</p>`}${compact ? '' : `<p class="muted small">${esc(tr('skillsLong', s))}</p>`}</div>`;
  }).join('')}</div>`;
}

// ---------- practice ----------
async function practice() {
  const pr = profile();
  const lang = getLang();
  const units = await bank(lang);
  const st = loadState(lang);
  let ses = LS.get('session.' + lang, null);
  let unit = ses && units.find(u => u.id === ses.unitId);
  if (!unit || ses.i >= ses.qids.length) {
    const sel = E.selectNextUnit(st, params, units, pr.grade);
    unit = sel.unit;
    const qs = E.selectQuestions(st, params, unit);
    ses = { unitId: unit.id, qids: qs.map(q => q.id), i: 0, reason: sel.reason,
      skipped: unit.questions.length - qs.length,
      start: Object.fromEntries(E.SKILLS.map(s => [s, st.skills[s].p])), diag: [] };
    LS.set('session.' + lang, ses);
  }
  const allDone = units.every(u => st.done[u.id]);
  const r = ses.reason;
  const reasonText = r.kind === 'start' ? t('reasonStart') : t('reasonWeak', tr('skills', r.skill), pct(r.p), r.count);
  app.innerHTML = `
    <div class="practice">
      <div class="topline">
        ${skillBars(st, true)}
        <details class="reason" ${r.kind === 'weak' ? 'open' : ''}><summary>${t('whyChosen')}</summary><p>${esc(reasonText)}${ses.skipped ? ' ' + esc(t('skipped', ses.skipped)) : ''}${allDone ? ' ' + esc(t('allDone')) : ''}</p></details>
      </div>
      <div class="reader card" id="reader">
        <div class="unit-meta"><span class="tag">${t('gradeN', unit.grade)}</span><button type="button" class="link" id="pass-btn">${t('passport')}</button></div>
        ${renderBlocks(unit)}
      </div>
      <section class="qpanel card" id="qpanel" aria-live="polite"></section>
    </div>
    <dialog id="pass-dlg" class="dlg"></dialog>`;
  document.getElementById('pass-btn').addEventListener('click', () => openPassport(unit));
  runQuestion(unit, ses, st, lang);
}

function openPassport(unit) {
  const d = document.getElementById('pass-dlg');
  const p = passport[unit.id];
  const items = [];
  if (p) {
    items.push(t('pGen', p.round, p.batch));
    if (p.blind_round1) items.push(t('pBlind1', p.blind_round1.match, p.blind_round1.total));
    items.push(t('pBlindFinal', p.blind_final.match, p.blind_final.total, p.blind_final.ambiguous));
    if (p.review) {
      const i = p.review.issues;
      items.push(t('pReview', p.review.language_score, i.critical, i.major, i.minor, p.review.fixed));
    }
    if (p.deep_proofread != null) items.push(t('pDeep', p.deep_proofread));
    if (p.ai_students && p.ai_students.p_ai != null) items.push(t('pStudents', pct(p.ai_students.p_ai)));
    items.push(t('pRejected'));
  }
  const status = unit.id.startsWith('kk-') ? t('pNative') : t('pNativeRu');
  d.innerHTML = `<form method="dialog"><h2>${t('passport')}</h2><p class="muted">${t('passportLead')}</p>
    <ol class="pass-steps">${items.map(x => `<li>${esc(x)}</li>`).join('')}</ol>
    <p class="pass-status">${esc(status)}</p><button class="btn primary">OK</button></form>`;
  if (d.showModal) d.showModal(); else d.setAttribute('open', '');
}

function runQuestion(unit, ses, st, lang) {
  const panel = document.getElementById('qpanel');
  const reader = document.getElementById('reader');
  const q = unit.questions.find(x => x.id === ses.qids[ses.i]);
  const n = ses.qids.length;
  const correctId = q.options.find(o => o.correct).id;
  const order = displayOrder(unit.id, q);
  ses.answered = ses.answered || {};
  // rec = everything about this question after the first check; persisted so that a reload or a visit to
  // another screen resumes in the same phase (retry / prove / done) and never counts the answer twice.
  let rec = ses.answered[q.id] || null;
  let phase = rec ? rec.phase : 'evidence';
  let tap = null;
  let choice = rec ? (rec.phase === 'retry' ? null : rec.retryChoice || rec.choice) : null;
  let collapsed = false;
  let extraLast = rec ? rec.extra : undefined;
  const disabled = new Set(rec ? rec.disabled : []);

  const persist = () => { ses.answered[q.id] = rec; LS.set('session.' + lang, ses); };
  const markPicked = ref => {
    reader.querySelectorAll('.picked').forEach(x => x.classList.remove('picked'));
    const el = ref && reader.querySelector(`[data-ev="${CSS.escape(ref)}"]`);
    if (el) el.classList.add('picked');
  };

  clearEvidence(reader);
  reader.classList.toggle('picking', phase === 'evidence' || phase === 'answer' || phase === 'prove');
  if (rec) {
    if (phase === 'retry') markPicked(rec.evOk ? rec.tap : null);
    if (phase === 'done' || rec.helped) showEvidence(reader, q.evidence);
  }

  const onTap = ev => {
    const el = ev.target.closest('.tap');
    if (!el || !reader.contains(el)) return;
    if (phase === 'evidence' || phase === 'answer') {
      markPicked(el.dataset.ev);
      tap = el.dataset.ev;
      if (phase === 'evidence') { phase = 'answer'; draw(); scrollPanel(); } else draw();
    } else if (phase === 'prove') {
      markPicked(el.dataset.ev);
      const ok = evidenceMatches(el.dataset.ev, q.evidence);
      const firstEl = showEvidence(reader, q.evidence);
      reader.classList.remove('picking');
      phase = 'done';
      rec.phase = 'done'; rec.extra = ok ? 'proved' : 'provedNot'; persist();
      draw(rec.extra);
      if (!ok && firstEl) scrollToEl(firstEl);
    }
  };
  reader.addEventListener('click', onTap);
  cleanup = () => reader.removeEventListener('click', onTap);

  function scrollPanel() {
    if (window.matchMedia('(max-width: 899px)').matches) panel.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function optionsHtml(lock) {
    return `<div class="opts" role="radiogroup">${order.map(k => q.options[k]).map((o, i) => {
      const cls = ['opt'];
      if (o.id === choice) cls.push('chosen');
      if (disabled.has(o.id)) cls.push('wrong');
      if ((phase === 'done' || phase === 'prove') && o.id === correctId) cls.push('right');
      const dis = lock || disabled.has(o.id) || phase === 'evidence';
      return `<button type="button" class="${cls.join(' ')}" data-opt="${o.id}" role="radio" aria-checked="${o.id === choice}" ${dis ? 'disabled' : ''}>
        <span class="letter">${'ABCD'[i]}</span><span>${esc(o.text)}</span></button>`;
    }).join('')}</div>`;
  }

  function trapHtml(optId) {
    const o = q.options.find(x => x.id === optId);
    if (!o || o.correct) return '';
    return `<div class="trap"><div class="trap-name"><span class="trap-ico" aria-hidden="true"></span>${t('trapTitle')}: <b>${esc(tr('traps', o.trap))}</b></div><p>${esc(o.why)}</p></div>`;
  }

  function hintsHtml() {
    const shown = rec.hintsShown;
    const hs = q.hint_steps.slice(0, shown).map(h => `<li>${esc(h)}</li>`).join('');
    const more = shown < q.hint_steps.length ? `<button type="button" class="btn ghost small" id="hint-more">${t('hintShow')} (${shown + 1}/${q.hint_steps.length})</button>` : '';
    const help = rec.helped ? `<p class="small muted">${t('evidenceShown')}</p>`
      : `<button type="button" class="btn ghost small" id="show-ev">${t('showEvidence')}</button>`;
    return `<div class="hints"><b>${t('hint')}</b>${hs ? `<ol>${hs}</ol>` : ''}<div class="btnrow">${more}${help}</div></div>`;
  }

  function diagHtml(d) {
    const [h, p] = tv('diag')[d];
    const text = (d === 'not_found' && phase === 'retry' && !rec.helped) ? t('notFoundHint') : p;
    return `<div class="diag d-${d}"><span class="diag-ico" aria-hidden="true"></span><div><b>${esc(h)}</b><p>${esc(text)}</p></div></div>`;
  }

  const okMsg = txt => `<div class="diag d-understood"><span class="diag-ico"></span><div><b>${txt}</b></div></div>`;
  const badMsg = txt => `<div class="diag d-not_found"><span class="diag-ico"></span><div><b>${txt}</b></div></div>`;

  function draw(extra) {
    extraLast = extra;
    const steps = `<ol class="steps"><li class="${phase === 'evidence' ? 'cur' : 'ok'}">1. ${t('step1')}</li><li class="${phase === 'answer' ? 'cur' : (phase === 'evidence' ? '' : 'ok')}">2. ${t('step2')}</li></ol>`;
    let body = '';
    if (phase === 'evidence') {
      body = `<p class="instr">${t('tapEvidence')}</p>${optionsHtml(true)}
        <button type="button" class="link" id="no-ev">${t('noEvidence')}</button>`;
    } else if (phase === 'answer') {
      body = `<p class="instr small muted">${tap ? t('changeEvidence') : ''}</p>${optionsHtml(false)}
        <button type="button" class="btn primary" id="check" ${choice ? '' : 'disabled'}>${t('check')}</button>`;
    } else if (phase === 'retry') {
      body = diagHtml(rec.diag) + trapHtml(rec.choice) + hintsHtml() + optionsHtml(false)
        + `<button type="button" class="btn primary" id="check" ${choice && !disabled.has(choice) ? '' : 'disabled'}>${t('check')}</button>`;
    } else if (phase === 'prove') {
      body = diagHtml('guessed') + optionsHtml(true);
    } else if (phase === 'done') {
      let msg;
      const helped = rec.helped ? ` <span class="tag">${t('withHelp')}</span>` : '';
      if (extra === 'proved') msg = okMsg(t('proved'));
      else if (extra === 'provedNot') msg = badMsg(t('provedNot'));
      else if (extra === 'second') msg = okMsg(t('correctSecond') + helped);
      else if (extra === 'final') msg = badMsg(t('wrongFinal')) + trapHtml(rec.retryChoice);
      else msg = diagHtml(rec.diag);
      const last = ses.i + 1 >= n;
      body = msg + optionsHtml(true) + `<div class="explain"><p>${esc(q.explain)}</p></div>`
        + `<button type="button" class="btn primary" id="next">${last ? t('unitDone') + ' →' : t('next')}</button>`;
    }
    panel.className = `qpanel card ph-${phase}${collapsed ? ' collapsed' : ''}`;
    panel.innerHTML = `<div class="qhead"><span class="qnum">${t('questionOf', ses.i + 1, n)}</span><span class="tag sk-${q.process}">${tr('skills', q.process)}</span>
      <button type="button" class="fold" id="fold" aria-expanded="${!collapsed}" aria-label="${t('toText')}">${collapsed ? '▴' : '▾'}</button></div>
      <p class="stem">${esc(q.stem)}</p>${steps}${body}`;
    bind();
  }

  function bind() {
    panel.querySelector('#fold').addEventListener('click', () => { collapsed = !collapsed; draw(extraLast); });
    panel.querySelectorAll('[data-opt]').forEach(b => b.addEventListener('click', () => {
      choice = b.dataset.opt;
      draw(extraLast);
    }));
    const noEv = panel.querySelector('#no-ev');
    if (noEv) noEv.addEventListener('click', () => { tap = null; phase = 'answer'; draw(); });
    const hm = panel.querySelector('#hint-more');
    if (hm) hm.addEventListener('click', () => { rec.hintsShown++; persist(); draw(); });
    const se = panel.querySelector('#show-ev');
    if (se) se.addEventListener('click', () => {
      // asking to see the evidence is recorded as "with help"
      rec.helped = true; persist();
      const el = showEvidence(reader, q.evidence);
      draw();
      if (el) scrollToEl(el);
    });
    const ck = panel.querySelector('#check');
    if (ck) ck.addEventListener('click', check);
    const nx = panel.querySelector('#next');
    if (nx) nx.addEventListener('click', next);
  }

  function check() {
    if (!choice) return;
    const correct = choice === correctId;
    if (phase === 'answer') {
      if (ses.answered[q.id]) return; // first attempt is recorded exactly once
      const evOk = evidenceMatches(tap, q.evidence);
      const diag = E.diagnose(correct, evOk);
      const wrongOpt = q.options.find(o => o.id === choice);
      const before = st.skills[q.process].p;
      rec = { correct, evOk, diag, choice, tap, phase: 'done', disabled: [], hintsShown: 0, helped: false };
      ses.diag.push(diag);
      if (correct && evOk) {
        showEvidence(reader, q.evidence);
        reader.classList.remove('picking');
      } else if (correct) {
        markPicked(null);
        rec.phase = 'prove';
      } else {
        // first mistake: text hint first; the evidence is highlighted only on request or after a 2nd mistake
        disabled.add(choice);
        rec.disabled = [choice];
        rec.hintsShown = 1;
        rec.phase = 'retry';
        if (!evOk) markPicked(null);
        reader.classList.remove('picking');
        choice = null;
      }
      persist();
      E.applyAnswer(st, params, q, correct, correct ? null : wrongOpt.trap, evOk);
      saveState(lang, st);
      animateSkill(q.process, before, st.skills[q.process].p);
      phase = rec.phase;
      draw();
    } else if (phase === 'retry') {
      if (!correct) disabled.add(choice);
      rec.disabled = [...disabled];
      rec.retryChoice = choice;
      rec.phase = 'done';
      rec.extra = correct ? 'second' : 'final';
      persist();
      phase = 'done';
      const el = showEvidence(reader, q.evidence);
      draw(rec.extra);
      if (!correct && el) scrollToEl(el);
    }
  }

  function next() {
    reader.classList.remove('picking');
    reader.querySelectorAll('.picked').forEach(x => x.classList.remove('picked'));
    ses.i += 1;
    LS.set('session.' + lang, ses);
    if (ses.i < n) { cleanup(); runQuestion(unit, ses, st, lang); window.scrollTo({ top: 0, behavior: 'smooth' }); return; }
    E.markUnitDone(st, unit.id);
    saveState(lang, st);
    unitSummary(unit, ses, st, lang);
  }

  draw(extraLast);
}

// Scroll so the element sits near the top (on phones the question panel covers the bottom half).
function scrollToEl(el) {
  const y = el.getBoundingClientRect().top + window.scrollY - 120;
  window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
}

function animateSkill(skill, before, after) {
  const el = document.querySelector(`.topline .skill[data-skill="${skill}"]`);
  if (!el) return;
  el.classList.remove('unrated');
  el.querySelector('b').textContent = `${pct(after)}%`;
  el.querySelector('.meter span').style.width = `${pct(after)}%`;
  el.classList.remove('up', 'down');
  void el.offsetWidth;
  el.classList.add(after >= before ? 'up' : 'down');
}

function unitSummary(unit, ses, st, lang) {
  const rows = E.SKILLS.map(s => {
    const a = pct(ses.start[s]), b = pct(st.skills[s].p);
    const d = b - a;
    return `<li class="sk-${s}"><span>${tr('skills', s)}</span><span class="delta ${d > 0 ? 'pos' : d < 0 ? 'neg' : ''}">${a}% → <b>${b}%</b> ${d > 0 ? '▲' : d < 0 ? '▼' : ''}</span></li>`;
  }).join('');
  const dc = {};
  ses.diag.forEach(d => { dc[d] = (dc[d] || 0) + 1; });
  const diag = E.DIAGNOSES.filter(d => dc[d]).map(d => `<span class="chip d-${d}">${esc(tr('diagShort', d))}: ${dc[d]}</span>`).join(' ');
  document.getElementById('qpanel').innerHTML = `<h2>${t('unitDone')}</h2><p>${t('unitDoneLead')}</p><ul class="deltas">${rows}</ul>
    <p class="chips">${diag}</p>
    <button class="btn primary big" id="next-unit" type="button">${t('nextText')} →</button>
    <a class="btn ghost" href="#/progress">${t('navProgress')}</a>`;
  LS.del('session.' + lang);
  document.getElementById('next-unit').addEventListener('click', () => practice().then(() => window.scrollTo(0, 0)));
}

// ---------- progress ----------
async function progress() {
  const pr = profile();
  const lang = getLang();
  const st = loadState(lang);
  const nTot = E.SKILLS.reduce((a, s) => a + st.skills[s].n, 0);
  const cTot = E.SKILLS.reduce((a, s) => a + st.skills[s].c, 0);
  const traps = E.TRAPS.filter(k => st.traps[k] > 0).sort((a, b) => st.traps[b] - st.traps[a]);
  const diagTot = E.DIAGNOSES.reduce((a, d) => a + (st.diag[d] || 0), 0) || 1;
  app.innerHTML = `
    <section class="card pad"><h1>${t('progressTitle')}</h1>
      <p class="muted">${esc(pr.name)} · ${t('gradeN', pr.grade)} · ${LANGS[lang]}</p>
      <div class="stats"><div><b>${nTot}</b><span>${t('answered')}</span></div><div><b>${nTot ? pct(cTot / nTot) : 0}%</b><span>${t('firstTry')}</span></div></div>
      <h2>${t('pKnow')}</h2>${skillBars(st)}
    </section>
    <section class="card pad"><h2>${t('diagProfile')}</h2>
      <div class="diag-grid">${E.DIAGNOSES.map(d => `<div class="dcell d-${d}"><b>${st.diag[d] || 0}</b><span>${esc(tr('diagShort', d))}</span><i style="width:${pct((st.diag[d] || 0) / diagTot)}%"></i></div>`).join('')}</div>
    </section>
    <section class="card pad"><h2>${t('myTraps')}</h2>
      ${traps.length ? `<ul class="traplist">${traps.map(k => `<li><span class="cnt">${st.traps[k]}</span><div><b>${esc(tr('traps', k))}</b><p class="muted small">${esc(tr('trapsLong', k))}</p></div></li>`).join('')}</ul>` : `<p class="muted">${t('noTraps')}</p>`}
    </section>
    <section class="card pad" id="share"><h2>${t('shareTitle')}</h2><p>${t('shareLead')}</p>
      <div class="qr-box" id="qr"></div>
      <p class="muted small">${t('shortCode')}</p><p class="short-code" id="scode"></p>
    </section>
    <p class="center"><button class="btn ghost" id="reset" type="button">${t('resetProgress')}</button></p>`;
  const payload = Q.encodePayload({ ...pr, lang }, st);
  document.getElementById('qr').innerHTML = Q.qrSvg(payload);
  document.getElementById('qr').dataset.payload = payload;
  document.getElementById('scode').textContent = Q.encodeShortCode({ ...pr, lang }, st);
  document.getElementById('reset').addEventListener('click', () => {
    if (!confirm(t('resetConfirm'))) return;
    LS.del('state.' + lang); LS.del('session.' + lang);
    progress();
  });
}

// ---------- teacher ----------
const classData = () => LS.get('class', { students: {} });
const saveClass = c => LS.set('class', c);

function addStudent(rec) {
  const c = classData();
  const key = `${rec.source === 'demo' ? 'demo:' : ''}${rec.name.toLowerCase()}|${rec.grade}|${rec.lang}`;
  c.students[key] = { ...rec, ts: Date.now() };
  saveClass(c);
  return rec.name;
}

const DEMO = [
  ['Жансая', 8, [62, 48, 31], [1, 4, 0, 1, 2, 3], [9, 3, 2, 4]], ['Нұрлан', 8, [71, 55, 40], [0, 3, 1, 2, 1, 1], [11, 2, 1, 2]],
  ['Дана', 8, [45, 38, 22], [2, 5, 2, 1, 3, 4], [5, 4, 3, 6]], ['Ерлан', 8, [80, 66, 52], [0, 1, 0, 2, 0, 1], [14, 1, 1, 1]],
  ['Әсел', 8, [55, 60, 35], [1, 2, 1, 3, 1, 2], [9, 2, 2, 3]], ['Тимур', 8, [38, 30, 18], [3, 4, 2, 2, 4, 5], [4, 5, 3, 6]],
  ['Мадина', 8, [66, 52, 44], [0, 2, 0, 2, 1, 2], [10, 2, 2, 2]], ['Олжас', 8, [50, 42, 28], [2, 3, 1, 1, 2, 3], [6, 3, 3, 4]],
];

async function teacher() {
  const lang = getLang();
  // share of bank questions offering each trap type: estimates exposure for students added by short code
  const trapShareInBank = {};
  for (const l of ['kk', 'ru']) {
    const qs = (await bank(l)).flatMap(u => u.questions);
    trapShareInBank[l] = E.TRAPS.map(tp => qs.filter(q => q.options.some(o => !o.correct && o.trap === tp)).length / qs.length);
  }
  const exposureOf = s => {
    if (s.exposure) return { ex: s.exposure, est: false };
    const nTot = s.n.reduce((a, b) => a + b, 0) || (s.diag || []).reduce((a, b) => a + b, 0);
    return { ex: trapShareInBank[s.lang].map(x => Math.round(x * nTot)), est: true };
  };
  app.innerHTML = `
    <section class="card pad"><h1>${t('teacherTitle')}</h1><p class="muted">${t('teacherLead')}</p>
      <div class="btnrow">
        <button class="btn primary" id="scan" type="button">${t('scan')}</button>
        <label class="btn ghost file">${t('scanFromPhoto')}<input type="file" accept="image/*" capture="environment" id="photo" hidden></label>
      </div>
      <div class="scanner" id="scanner" hidden><video id="video" muted playsinline></video><div class="frame"></div>
        <button class="btn ghost" id="stop" type="button">${t('stopScan')}</button></div>
      <details class="manual"><summary>${t('enterCode')}</summary>
        <form id="codeform" class="form"><label>${t('studentName')}<input name="name" required maxlength="24"></label>
          <label>${t('code')}<input name="code" required placeholder="XXXX-XXXX-XXXX-XXXX" autocapitalize="characters" autocomplete="off" spellcheck="false"></label>
          <button class="btn primary" type="submit">${t('add')}</button></form></details>
    </section>
    <section class="card pad" id="report"></section>`;
  let stop = null;
  let last = '';
  let lastAt = 0;
  let badAt = 0;
  const handle = text => {
    if (text === last && Date.now() - lastAt < 4000) return;
    const rec = Q.decodePayload(text);
    if (!rec) {
      // a foreign QR stays in the frame for seconds: warn at most every 4 s
      if (Date.now() - badAt > 4000) { badAt = Date.now(); toast(t(String(text).startsWith('IZ') ? 'badCode' : 'notIzden')); }
      return;
    }
    last = text; lastAt = Date.now();
    toast(t('added', addStudent(rec)));
    if (navigator.vibrate) navigator.vibrate(80);
    drawReport();
  };
  let starting = false;
  document.getElementById('scan').addEventListener('click', async () => {
    if (stop || starting) return; // already running
    starting = true;
    const box = document.getElementById('scanner');
    try {
      box.hidden = false;
      stop = await Q.startScanner(document.getElementById('video'), handle);
    } catch (e) {
      box.hidden = true;
      toast(t('noCamera'));
    } finally {
      starting = false;
    }
  });
  document.getElementById('stop').addEventListener('click', () => { if (stop) stop(); stop = null; document.getElementById('scanner').hidden = true; });
  cleanup = () => { if (stop) stop(); };
  document.getElementById('photo').addEventListener('change', async ev => {
    const f = ev.target.files[0];
    if (!f) return;
    const text = await Q.decodeFile(f).catch(() => null);
    if (text) handle(text); else toast(t('badCode'));
    ev.target.value = '';
  });
  document.getElementById('codeform').addEventListener('submit', ev => {
    ev.preventDefault();
    const d = new FormData(ev.target);
    const rec = Q.decodeShortCode(d.get('code'), d.get('name'));
    if (!rec) { toast(t('badCode')); return; }
    toast(t('added', addStudent(rec)));
    ev.target.reset();
    drawReport();
  });
  drawReport();

  function drawReport() {
    const c = classData();
    const list = Object.entries(c.students).sort((a, b) => a[1].name.localeCompare(b[1].name));
    const el = document.getElementById('report');
    const demoBtn = `<button class="btn ghost small" id="demo" type="button">${t('demoClass')}</button>`;
    if (!list.length) {
      el.innerHTML = `<h2>${t('students')}</h2><p class="muted">${t('noStudents')}</p>${demoBtn}`;
      document.getElementById('demo').addEventListener('click', addDemo);
      return;
    }
    const avg = [0, 1, 2].map(i => list.reduce((a, [, s]) => a + s.p[i], 0) / list.length);
    const weakIdx = avg.indexOf(Math.min(...avg));
    const weakSkill = E.SKILLS[weakIdx];
    // trap rate = wrong answers into this trap / all class answers to questions that offered this trap
    let estimated = false;
    const trapStats = E.TRAPS.map((k, i) => {
      let falls = 0, exposed = 0;
      for (const [, s] of list) {
        const { ex, est } = exposureOf(s);
        if (est) estimated = true;
        falls += s.traps[i];
        exposed += Math.max(ex[i], s.traps[i]);
      }
      return { k, falls, exposed, rate: exposed ? falls / exposed : 0, students: list.filter(([, s]) => s.traps[i] > 0).length };
    }).filter(x => x.falls > 0).sort((a, b) => b.rate - a.rate || b.falls - a.falls);
    const cell = v => `<td class="heat ${v < 40 ? 'h-low' : v < 70 ? 'h-mid' : 'h-high'}">${v}</td>`;
    const rows = list.map(([key, s]) => {
      const ti = s.traps.indexOf(Math.max(...s.traps));
      const top = Math.max(...s.traps) > 0 ? tr('traps', E.TRAPS[ti]) : '—';
      return `<tr><th scope="row">${esc(s.name)}${s.source === 'demo' ? ` <span class="tag">${t('demoMark')}</span>` : ''}<small>${t('gradeN', s.grade)} · ${s.lang === 'kk' ? 'қаз' : 'рус'}</small></th>
        ${s.p.map(cell).join('')}<td>${s.diag ? s.diag[1] : '—'}</td><td class="small">${esc(top)}</td>
        <td><button class="x" data-del="${esc(key)}" aria-label="${t('removeStudent')}" type="button">×</button></td></tr>`;
    }).join('');
    el.innerHTML = `<h2>${t('students')}: ${list.length}</h2>
      <div class="table-scroll"><table class="report"><thead><tr><th>${t('name')}</th>${E.SKILLS.map(s => `<th>${tr('skills', s)}</th>`).join('')}<th>${t('diagGuessedCol')}</th><th>${t('topTrap')}</th><th></th></tr></thead>
      <tbody>${rows}</tbody><tfoot><tr><th>${t('avg')}</th>${avg.map(v => cell(Math.round(v))).join('')}<td></td><td></td><td></td></tr></tfoot></table></div>
      <div class="insight"><p>${esc(t('classWeak', tr('skills', weakSkill)))}</p>
        <a class="btn ghost small" href="#/print/${weakSkill}">${t('printForSkill')}</a></div>
      <h2>${t('classTraps')}</h2>
      <ul class="class-traps">${trapStats.slice(0, 3).map((x, i) => `<li class="${i === 0 ? 'top' : ''}">
        <div class="bar-line"><span style="width:${pct(x.rate)}%"></span></div>
        <p>${esc(t('trapRate', tr('traps', x.k), pct(x.rate), x.students, list.length))}</p>
        <a class="btn ${i === 0 ? 'primary' : 'ghost'} small" href="#/trap/${x.k}">${t('tomorrow')} →</a></li>`).join('')}</ul>
      ${estimated ? `<p class="muted small">* ${t('trapRateEst')}</p>` : ''}
      <div class="btnrow">${demoBtn}<button class="btn ghost small" id="csv" type="button">${t('exportCsv')}</button>
        <button class="btn ghost small danger" id="clear" type="button">${t('clearClass')}</button></div>`;
    el.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => {
      const cc = classData(); delete cc.students[b.dataset.del]; saveClass(cc); drawReport();
    }));
    document.getElementById('demo').addEventListener('click', addDemo);
    document.getElementById('clear').addEventListener('click', () => { if (confirm(t('clearConfirm'))) { LS.del('class'); drawReport(); } });
    document.getElementById('csv').addEventListener('click', () => {
      const head = ['name', 'grade', 'lang', ...E.SKILLS, ...E.TRAPS, ...E.DIAGNOSES, 'source'];
      const lines = [head.join(',')].concat(list.map(([, s]) => [JSON.stringify(s.name), s.grade, s.lang, ...s.p, ...s.traps, ...(s.diag || [0, 0, 0, 0]), s.source].join(',')));
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob(['﻿' + lines.join('\n')], { type: 'text/csv' }));
      a.download = 'izden-class.csv';
      a.click();
    });
  }
  function addDemo() {
    DEMO.forEach(([name, grade, p, traps, diag]) => {
      const nTot = diag.reduce((a, b) => a + b, 0);
      const exposure = trapShareInBank[lang].map((x, i) => Math.max(traps[i], Math.round(x * nTot)));
      addStudent({ name, grade, lang, p, n: [0, 0, 0], c: [0, 0, 0], traps, diag, exposure, units: 0, date: '', source: 'demo' });
    });
    drawReport();
  }
}

// ---------- trap card ("what to do tomorrow") ----------
async function trapPage(type) {
  const lang = getLang();
  const card = (trapCards[lang] || {})[type];
  if (!card) { location.hash = '#/teacher'; return; }
  const units = await bank(lang);
  // mini-sheet: the unit with the most distractors of this trap type, only its questions that contain it
  let best = null, bestN = 0;
  for (const u of units) {
    const n = u.questions.filter(q => q.options.some(o => o.trap === type)).length;
    if (n > bestN || (n === bestN && best && u.grade < best.grade)) { best = u; bestN = n; }
  }
  const qs = best ? best.questions.filter(q => q.options.some(o => o.trap === type)) : [];
  app.innerHTML = `<section class="card pad trapcard">
      <a href="#/teacher" class="link">← ${t('back')}</a>
      <p class="eyebrow">${t('tomorrow')}</p><h1>${esc(card.title)}</h1><p>${esc(card.why)}</p>
      <h2>${t('lessonPlan')}</h2><ol class="lesson">${card.lesson.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
      <h2>${t('tipForStudents')}</h2><p class="tip">${esc(card.tip)}</p>
      <button class="btn primary" id="pr" type="button">${t('printMini')}</button>
    </section>
    <div class="paper" id="paper">${sheetHtml(best ? [{ unit: best, qs }] : [], { key: true, sheet: false, title: card.title, tip: card.tip })}</div>`;
  document.getElementById('pr').addEventListener('click', () => window.print());
}

// ---------- paper mode ----------
// A sheet is its own document: spread the correct answers over A-D (balanced, shuffled in blocks of 4)
// by rotating each question's options; the sheet's key uses exactly the same order.
function sheetTargets(count, seedText) {
  let seed = 0;
  for (let i = 0; i < seedText.length; i++) seed = (seed * 31 + seedText.charCodeAt(i)) >>> 0;
  const rnd = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  const out = [];
  while (out.length < count) {
    const block = [0, 1, 2, 3];
    for (let i = 3; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [block[i], block[j]] = [block[j], block[i]]; }
    out.push(...block);
  }
  return out;
}

function sheetHtml(items, { key, sheet, title, tip }) {
  const total = items.reduce((a, it) => a + it.qs.length, 0);
  const targets = sheetTargets(total, items.map(it => it.unit.id).join('|') + title);
  const head = `<header class="sheet-head"><h1>Ізден · ${esc(title)}</h1><p>${t('studentLine')}</p>${tip ? `<p class="tip">${esc(tip)}</p>` : ''}<p class="small">${t('evNumsNote')}</p></header>`;
  let qn = 0;
  const keyRows = [];
  const body = items.map(({ unit, qs }) => {
    const qh = qs.map(q => {
      qn += 1;
      const base = displayOrder(unit.id, q).map(k => q.options[k]);
      const nOpt = base.length;
      const want = targets[qn - 1] % nOpt;
      const shift = (base.findIndex(o => o.correct) - want + nOpt) % nOpt;
      const opts = base.map((_, i) => base[(i + shift) % nOpt]);
      const ci = opts.findIndex(o => o.correct);
      keyRows.push(`<tr><td>${qn}</td><td>${'ABCD'[ci]}</td><td>${esc(evidenceLabel(unit, q.evidence))}</td><td>${esc(tr('skills', q.process))}</td></tr>`);
      return `<li class="pq"><p><b>${qn}.</b> ${esc(q.stem)}</p><ol class="popts">${opts.map((o, i) => `<li><b>${'ABCD'[i]}</b> ${esc(o.text)}</li>`).join('')}</ol></li>`;
    }).join('');
    return `<section class="sheet-unit">${renderBlocks(unit, { numbers: true, compact: true })}<ol class="pqs">${qh}</ol></section>`;
  }).join('');
  const answerSheet = sheet ? `<section class="sheet-answers"><h2>${t('answerSheet')}</h2><p>${t('studentLine')}</p>
    <table><thead><tr><th>${t('q')}</th><th>${t('answer')}</th><th>${t('evidenceNo')}</th></tr></thead><tbody>
    ${Array.from({ length: qn }, (_, i) => `<tr><td>${i + 1}</td><td>A&nbsp;&nbsp;B&nbsp;&nbsp;C&nbsp;&nbsp;D</td><td></td></tr>`).join('')}</tbody></table></section>` : '';
  const keyHtml = key ? `<section class="sheet-key"><h2>${t('answerKey')}</h2><table><thead><tr><th>${t('q')}</th><th>${t('answer')}</th><th>${t('evidenceNo')}</th><th>${t('focusSkill')}</th></tr></thead><tbody>${keyRows.join('')}</tbody></table></section>` : '';
  return head + body + answerSheet + keyHtml;
}

async function printPage(skillArg) {
  const lang = getLang();
  const pr = profile();
  const units = await bank(lang);
  const sel = { grade: pr ? pr.grade : 8, skill: E.SKILLS.includes(skillArg) ? skillArg : 'any', count: 2, sheet: true, key: true };
  app.innerHTML = `<section class="card pad noprint"><h1>${t('printTitle')}</h1><p class="muted">${t('printLead')}</p>
    <form id="pf" class="form grid3">
      <label>${t('grade')}<select name="grade">${[7, 8, 9].map(g => `<option value="${g}" ${g === sel.grade ? 'selected' : ''}>${t('gradeN', g)}</option>`).join('')}</select></label>
      <label>${t('focusSkill')}<select name="skill"><option value="any">${t('anySkill')}</option>${E.SKILLS.map(s => `<option value="${s}" ${s === sel.skill ? 'selected' : ''}>${tr('skills', s)}</option>`).join('')}</select></label>
      <label>${t('units')}<select name="count">${[1, 2, 3, 4].map(n => `<option ${n === sel.count ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
      <label class="check"><input type="checkbox" name="sheet" checked> ${t('withSheet')}</label>
      <label class="check"><input type="checkbox" name="key" checked> ${t('withKey')}</label>
    </form><button class="btn primary" id="pbtn" type="button">${t('printBtn')}</button></section>
    <div class="paper" id="paper"></div>`;
  const f = document.getElementById('pf');
  const draw = () => {
    const d = new FormData(f);
    const grade = +d.get('grade'), skill = d.get('skill'), count = +d.get('count');
    const score = u => (skill === 'any' ? 0 : u.questions.filter(q => q.process === skill).length);
    const pick = units.filter(u => u.grade === grade).sort((a, b) => score(b) - score(a) || a.id.localeCompare(b.id)).slice(0, count);
    const title = `${t('printTitle')} · ${t('gradeN', grade)}${skill !== 'any' ? ' · ' + tr('skills', skill) : ''}`;
    document.getElementById('paper').innerHTML = sheetHtml(pick.map(u => ({ unit: u, qs: u.questions })), { key: d.get('key'), sheet: d.get('sheet'), title });
  };
  f.addEventListener('change', draw);
  document.getElementById('pbtn').addEventListener('click', () => window.print());
  draw();
}

// ---------- language ----------
function switchLang(l, rerender = true) {
  setLang(l);
  LS.set('lang', l);
  const p = profile();
  if (p && p.lang !== l) { p.lang = l; LS.set('profile', p); }
  renderShell();
  if (rerender) route();
}

// ---------- boot ----------
async function boot() {
  const p = profile();
  setLang((p && p.lang) || LS.get('lang', 'kk'));
  renderShell();
  document.getElementById('lang-switch').addEventListener('click', e => {
    const b = e.target.closest('[data-lang]');
    if (b && b.dataset.lang !== getLang()) switchLang(b.dataset.lang);
  });
  window.addEventListener('online', updateNetPill);
  window.addEventListener('offline', updateNetPill);
  [params, passport, trapCards] = await Promise.all([
    loadJSON('data/bkt_params.json'), loadJSON('data/passport.json').catch(() => ({})), loadJSON('data/trap_cards.json').catch(() => ({})),
  ]);
  window.addEventListener('hashchange', route);
  await route();
  if ('serviceWorker' in navigator && location.protocol !== 'file:') {
    navigator.serviceWorker.register('sw.js').then(() => navigator.serviceWorker.ready).then(updateNetPill).catch(() => {});
    navigator.serviceWorker.addEventListener('controllerchange', updateNetPill);
  }
}

boot();
