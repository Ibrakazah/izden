// Word translation (kk <-> ru) and the student's own dictionary with spaced review.
// Offline: data/dict.<lang>.json maps every word form used in the texts to [lemma, translation].
// Online: a word missing from the offline dictionary can be translated in context by the AI helper (/api/ask, mode "word").
import { t, getLang } from './i18n.js';
import { esc } from './text.js';

const dicts = {};
export async function loadDict(lang) {
  if (!dicts[lang]) {
    try { const r = await fetch(`data/dict.${lang}.json`); dicts[lang] = r.ok ? await r.json() : {}; } catch (e) { dicts[lang] = {}; }
  }
  return dicts[lang];
}
export const norm = w => w.toLowerCase().replace(/ё/g, 'е').replace(/^[-–]+|[-–]+$/g, '');

// ---- saved words (Leitner boxes) ----
const DAY = 864e5;
const STEPS = [0, 1, 2, 4, 7, 14, 30];
let store = null;
export function initDict(ls) { store = ls; }
export const words = () => store.get('words', []);
const saveWords = w => store.set('words', w);
export function isSaved(lang, lemma) { return words().some(x => x.lang === lang && x.lemma === lemma); }
export function addWord(e) {
  const w = words();
  if (w.some(x => x.lang === e.lang && x.lemma === e.lemma)) return false;
  w.unshift({ ...e, box: 0, due: Date.now(), added: Date.now() });
  saveWords(w.slice(0, 500));
  return true;
}
export function removeWord(lang, lemma) { saveWords(words().filter(x => !(x.lang === lang && x.lemma === lemma))); }
export const dueWords = () => words().filter(x => x.due <= Date.now());
function grade(x, ok) {
  const w = words();
  const it = w.find(y => y.lang === x.lang && y.lemma === x.lemma);
  if (!it) return;
  it.box = ok ? Math.min(STEPS.length - 1, it.box + 1) : 0;
  it.due = ok ? Date.now() + STEPS[it.box] * DAY : Date.now() + 10 * 60 * 1000;
  saveWords(w);
}

// ---- word under the finger ----
const LETTER = /[\p{L}\p{M}-]/u;
export function wordAt(x, y) {
  let node, off;
  if (document.caretRangeFromPoint) { const r = document.caretRangeFromPoint(x, y); if (!r) return null; node = r.startContainer; off = r.startOffset; }
  else if (document.caretPositionFromPoint) { const p = document.caretPositionFromPoint(x, y); if (!p) return null; node = p.offsetNode; off = p.offset; }
  if (!node || node.nodeType !== 3) return null;
  const s = node.textContent;
  let a = off, b = off;
  while (a > 0 && LETTER.test(s[a - 1])) a--;
  while (b < s.length && LETTER.test(s[b])) b++;
  const w = s.slice(a, b).replace(/^-+|-+$/g, '');
  if (w.length < 2 || /^\d+$/.test(w)) return null;
  const range = document.createRange();
  range.setStart(node, a); range.setEnd(node, b);
  const holder = node.parentElement.closest('.sent, li, tr, .bar-row, .blk-h, .unit-title, figcaption, .stem, .opt') || node.parentElement;
  const raw = holder.tagName === 'TR' ? [...holder.children].map(c => c.textContent).join(' ') : holder.textContent;
  return { w, ctx: raw.replace(/\s+/g, ' ').trim().slice(0, 300), range };
}

// ---- bottom sheet with the translation ----
let sheet = null;
let seq = 0;
export function closeSheet() { seq++; if (sheet) { sheet.remove(); sheet = null; } document.querySelectorAll('.w-hl').forEach(e => e.replaceWith(...e.childNodes)); }

export async function showWord(hit, lang, { unitId } = {}) {
  closeSheet();
  const my = ++seq; // a newer tap or a close makes this call stale
  try { const mark = document.createElement('mark'); mark.className = 'w-hl'; hit.range.surroundContents(mark); } catch (e) { /* range crosses nodes */ }
  const to = lang === 'kk' ? 'ru' : 'kk';
  const d = await loadDict(lang);
  if (my !== seq) return;
  const found = d[norm(hit.w)];
  const el = sheet = document.createElement('div');
  el.className = 'wsheet';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', hit.w);
  document.body.appendChild(el);
  const draw = (entry, state) => {
    if (my !== seq) return;
    const lemma = entry ? entry[0] : norm(hit.w);
    const saved = entry && isSaved(lang, lemma);
    const body = entry
      ? `<p class="w-tr"><span class="w-flag">${to === 'kk' ? 'ҚАЗ' : 'РУС'}</span> ${esc(entry[1])}</p>${entry[2] ? `<p class="small muted">${t('wByAi')}</p>` : ''}`
      : state === 'busy' ? `<p class="muted">${t('aiThinking')}</p>`
        : state === 'err' ? `<p class="muted">${t('wAiErr')}</p>`
          : `<p class="muted">${t('wMissing')}</p>`;
    const aiBtn = !entry && state !== 'busy' ? (navigator.onLine
      ? `<button type="button" class="btn primary small" data-w="ai"><span aria-hidden="true">✦</span> ${t('wAskAi')}</button>`
      : `<p class="small ai-off">${t('wOffline')}</p>`) : '';
    const saveBtn = entry ? (saved
      ? `<button type="button" class="btn ghost small" disabled>✓ ${t('wSaved')}</button>`
      : `<button type="button" class="btn primary small" data-w="save">＋ ${t('wSave')}</button>`) : '';
    el.innerHTML = `<div class="wsheet-in"><div class="w-head"><b class="w-word">${esc(hit.w)}</b>${entry && norm(entry[0]) !== norm(hit.w) ? `<span class="muted"> → ${esc(entry[0])}</span>` : ''}
      <button type="button" class="w-x" data-w="close" aria-label="${t('wClose')}">×</button></div>${body}<div class="btnrow">${saveBtn}${aiBtn}<a class="btn ghost small" href="#/dict">${t('navDict')}</a></div></div>`;
  };
  let entry = found || null;
  draw(entry);
  el.addEventListener('click', async e => {
    const b = e.target.closest('[data-w]');
    if (!b) return;
    if (b.dataset.w === 'close') closeSheet();
    if (b.dataset.w === 'save') {
      addWord({ lang, w: hit.w, lemma: entry[0], tr: entry[1], ctx: hit.ctx, unit: unitId || '' });
      draw(entry);
      setTimeout(() => { if (my === seq) closeSheet(); }, 1100); // saved: let the student see it, then get out of the way
    }
    if (b.dataset.w === 'ai') {
      draw(null, 'busy');
      try {
        const ac = new AbortController();
        const timer = setTimeout(() => ac.abort(), 15000);
        const r = await fetch('/api/ask', { method: 'POST', signal: ac.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'word', lang, word: hit.w, ctx: hit.ctx }) });
        clearTimeout(timer);
        const j = r.ok ? await r.json() : null;
        if (!j || !j.tr) throw new Error('no');
        entry = [j.lemma || norm(hit.w), j.tr, 1];
        d[norm(hit.w)] = entry; // remember for this session
        draw(entry);
      } catch (err) { draw(null, 'err'); }
    }
  });
}

// ---- dictionary page ----
export function dictPage(app) {
  const all = words();
  const due = dueWords();
  const learned = all.filter(x => x.box >= 3).length;
  const list = all.map((x, i) => `<li><div><b>${esc(x.lemma)}</b> <span class="w-flag">${x.lang === 'kk' ? 'ҚАЗ' : 'РУС'}</span> — ${esc(x.tr)}
      ${x.ctx ? `<p class="small muted">${esc(x.ctx)}</p>` : ''}</div>
      <span class="w-box" title="${t('wBox')}">${'●'.repeat(Math.min(x.box, 5))}${'○'.repeat(Math.max(0, 5 - x.box))}</span>
      <button type="button" class="w-x" data-del="${i}" aria-label="${t('wDelete')}">×</button></li>`).join('');
  app.innerHTML = `<section class="card pad"><h1>${t('dictTitle')}</h1>
      <div class="stats s3"><div><b>${all.length}</b><span>${t('wTotal')}</span></div><div><b>${learned}</b><span>${t('wLearned')}</span></div><div><b>${due.length}</b><span>${t('wDue')}</span></div></div>
      ${all.length ? `<button class="btn primary big" id="w-review" type="button" ${due.length ? '' : 'disabled'}>${due.length ? t('wReview', due.length) : t('wNoDue')}</button>` : ''}
      <p class="muted small">${t('dictLead')}</p></section>
    ${all.length ? `<section class="card pad"><ul class="wlist">${list}</ul></section>` : `<section class="card pad"><p>${t('dictEmpty')}</p><a class="btn primary" href="#/practice">${t('navPractice')}</a></section>`}`;
  app.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => {
    const x = all[+b.dataset.del];
    if (x) removeWord(x.lang, x.lemma);
    dictPage(app);
  }));
  const rv = document.getElementById('w-review');
  if (rv) rv.addEventListener('click', () => review(app));
}

function review(app) {
  const deck = dueWords().slice(0, 20);
  let i = 0, ok = 0;
  const card = () => {
    if (i >= deck.length) {
      app.innerHTML = `<section class="card pad center"><h1>${t('wDoneTitle')}</h1><p class="lead">${t('wDoneLead', ok, deck.length)}</p>
        <a class="btn primary big" href="#/dict">${t('navDict')}</a></section>`;
      return;
    }
    const x = deck[i];
    const pat = x.w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const ctx = x.ctx ? esc(x.ctx).replace(new RegExp(`(^|[^\\p{L}&])(${pat})(?=[^\\p{L}]|$)`, 'iu'), (m, a, w) => `${a}<b>${w}</b>`) : '';
    app.innerHTML = `<section class="card pad wcard"><p class="muted small">${i + 1} / ${deck.length}</p>
      <div class="meter"><span style="width:${Math.round(i / deck.length * 100)}%"></span></div>
      <p class="w-front">${esc(x.lemma)} <span class="w-flag">${x.lang === 'kk' ? 'ҚАЗ' : 'РУС'}</span></p>
      ${ctx ? `<p class="muted">${ctx}</p>` : ''}
      <div id="w-back"><button class="btn primary big" id="w-show" type="button">${t('wShow')}</button></div></section>`;
    document.getElementById('w-show').addEventListener('click', () => {
      document.getElementById('w-back').innerHTML = `<p class="w-tr big">${esc(x.tr)}</p>
        <div class="w-grade"><button class="btn ghost" id="w-no" type="button">${t('wForgot')}</button><button class="btn primary" id="w-yes" type="button">${t('wKnew')}</button></div>`;
      document.getElementById('w-no').addEventListener('click', () => { grade(x, false); i++; card(); });
      document.getElementById('w-yes').addEventListener('click', () => { grade(x, true); ok++; i++; card(); });
    });
  };
  card();
}
export { getLang };
