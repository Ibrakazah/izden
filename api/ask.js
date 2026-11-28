// Online AI helper for Izden (Vercel serverless function, Node 18+).
// The key never reaches the browser: the page calls /api/ask, this function calls OpenRouter.
// The helper is allowed after the student's first answer only, never names the right option before the
// question is finished, and every reply is checked for a leak before it is returned.
// Without OPENROUTER_API_KEY, or when every model fails, it answers with the question's own hint steps
// (mode "mock" / "fallback"), so the demo never depends on the API.
const fs = require('fs');
const path = require('path');

const MODELS = (process.env.AI_MODELS || 'baidu/ernie-5.5-flash-preview:free,google/gemma-4-31b-it:free,nvidia/nemotron-3-ultra-550b-a55b:free')
  .split(',').map((s) => s.trim()).filter(Boolean);
const TIMEOUT_MS = Number(process.env.AI_TIMEOUT_MS || 9000);
const MAX_MSG = 300, MAX_TURNS = 6, MAX_REPLY = 700;
const PHASES = new Set(['retry', 'prove', 'done']);

const banks = {};
function bank(lang) {
  if (!banks[lang]) {
    // reading bank plus the maths bank (if deployed): the helper serves both subjects
    const units = [];
    for (const name of ['bank', 'math']) {
      try { units.push(...JSON.parse(fs.readFileSync(path.join(process.cwd(), 'data', `${name}.${lang}.json`), 'utf8')).units); } catch (e) { if (name === 'bank') throw e; }
    }
    banks[lang] = { units };
  }
  return banks[lang];
}

// A small per-instance rate limit (best effort: serverless instances do not share memory).
const hits = new Map();
function limited(ip, max = 30) {
  const now = Date.now(), win = 10 * 60 * 1000;
  if (hits.size > 5000) hits.clear();
  const list = (hits.get(ip) || []).filter((x) => now - x < win);
  list.push(now); hits.set(ip, list);
  return list.length > max;
}

function blockText(b) {
  if (b.type === 'h' || b.type === 'p') return b.text;
  if (b.type === 'list') return b.items.map((x) => '- ' + x).join('\n');
  if (b.type === 'table') return (b.caption ? b.caption + ':\n' : '') + b.rows.map((r) => r.join(' | ')).join('\n');
  if (b.type === 'chart') return (b.caption ? b.caption + ' (' + (b.unit || '') + '):\n' : '') + b.rows.map((r) => r[0] + ': ' + r[1]).join('\n');
  return '';
}

const norm = (s) => String(s).toLowerCase().replace(/ё/g, 'е').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();

// Words or numbers that only the right option has: if a reply says them before the question is over, it leaks.
function leaks(reply, q) {
  const right = q.options.find((o) => o.correct);
  const r = ' ' + norm(reply) + ' ';
  if (r.includes(' ' + norm(right.text) + ' ')) return true;
  const others = new Set(norm(q.options.filter((o) => !o.correct).map((o) => o.text).join(' ') + ' ' + q.stem).split(' '));
  const own = [...new Set(norm(right.text).split(' '))].filter((w) => !others.has(w) && (/^\d+$/.test(w) || w.length >= 5));
  if (!own.length) return false;
  const found = own.filter((w) => r.includes(' ' + w + ' ')).length;
  return own.length <= 2 ? found > 0 : found >= Math.ceil(own.length / 2);
}

function systemPrompt(lang, unit, q, phase, choice) {
  const right = q.options.find((o) => o.correct);
  const chosen = q.options.find((o) => o.id === choice);
  const L = lang === 'kk' ? 'казахском (қазақ тілінде)' : 'русском';
  const rules = phase === 'done'
    ? 'Вопрос уже решён: можно объяснить, почему верный ответ верный, опираясь на конкретные слова или строки текста.'
    : phase === 'prove'
      ? 'Ученик выбрал верный ответ, но не показал, где в тексте доказательство. Не показывай точное место (строку, предложение): подскажи, какую часть текста или колонку перечитать и что в ней искать.'
      : 'Ученик ошибся. НИКОГДА не называй верный вариант, его номер или текст, не подтверждай и не опровергай догадки о других вариантах. Объясни, что важно в вопросе, и задай один наводящий вопрос, чтобы он сам нашёл ответ в тексте.';
  return [
    unit.subject === 'math'
      ? 'Ты — помощник по математике в тренажёре «Ізден» для учеников 7–9 классов из сельских школ Казахстана. Не называй итоговое число ответа и не делай последнее вычисление за ученика: подскажи, какие данные из условия взять и какое действие сделать первым.'
      : 'Ты — помощник по чтению в тренажёре «Ізден» для учеников 7–9 классов из сельских школ Казахстана.',
    `Отвечай на ${L} языке, просто и дружелюбно, 1–3 коротких предложения, без markdown и списков.`,
    'Говори только об этом тексте и вопросе; на другие темы мягко возвращай к заданию. Не придумывай факты, которых нет в тексте.',
    rules,
    '',
    `ТЕКСТ «${unit.title}»:`,
    unit.blocks.map(blockText).join('\n\n'),
    '',
    `ВОПРОС: ${q.stem}`,
    'ВАРИАНТЫ: ' + q.options.map((o) => '«' + o.text + '»').join('; '),
    // until the question is finished the model never sees the key, so it cannot leak it, whatever the student asks
    phase === 'done' ? `ВЕРНЫЙ ОТВЕТ: «${right.text}». Почему: ${q.explain}` : '',
    phase === 'prove' && chosen ? `Ученик выбрал верный вариант «${chosen.text}», но не нашёл, где это написано.` : '',
    chosen && !chosen.correct ? `Ученик выбрал «${chosen.text}». Ошибка этого варианта: ${chosen.why}` : '',
    'Шаги подсказки из банка: ' + q.hint_steps.join(' / '),
  ].filter((x) => x !== '').join('\n');
}

// The first model gets 3.5 s alone; if it is slow or fails, the others join and the first good reply wins.
// This keeps the daily quota of free models for real use instead of spending three calls per question.
async function firstReply(run) {
  const [m0, ...rest] = MODELS;
  const p0 = run(m0);
  p0.catch(() => {});
  try {
    return await Promise.race([p0, new Promise((_, rej) => setTimeout(() => rej(new Error('slow')), 3500))]);
  } catch (e) {
    return Promise.any([p0, ...rest.map(run)]);
  }
}

async function callModel(model, messages, key) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const r = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST', signal: ac.signal,
      headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json', 'HTTP-Referer': 'https://izden.vercel.app', 'X-Title': 'Izden' },
      body: JSON.stringify({ model, messages, max_tokens: 300, temperature: 0.3 }),
    });
    if (!r.ok) throw new Error('http ' + r.status);
    const j = await r.json();
    const text = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
    if (typeof text !== 'string' || !text.trim()) throw new Error('empty reply');
    // free models sometimes slip a word of Chinese or Vietnamese into a Russian or Kazakh reply: drop such words
    const clean = text.replace(/[_#`]/g, '').replace(/\*\*/g, '')
      .replace(/\S*[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u024FḀ-ỿ]\S*/gu, '')
      .replace(/[ \t]{2,}/g, ' ').replace(/ ([,.?!:;])/g, '$1').replace(/\s+\n/g, '\n').trim().slice(0, MAX_REPLY);
    if (clean.length < 8) throw new Error('reply in another language');
    return clean;
  } finally { clearTimeout(timer); }
}

function hintReply(lang, q, turn) {
  const step = q.hint_steps[Math.min(turn, q.hint_steps.length - 1)];
  return (lang === 'kk' ? 'Мәтіннен өзің тауып көр: ' : 'Попробуй найти сам: ') + step;
}

// Word mode: translate one word in its sentence (kk <-> ru) for words missing from the offline dictionary.
async function translateWord(body, res) {
  const { lang, word, ctx } = body;
  const w = String(word || '').trim().slice(0, 40);
  if (!['kk', 'ru'].includes(lang) || !/^[\p{L}\p{M}-]{2,40}$/u.test(w)) return res.status(400).json({ error: 'bad request' });
  const key = process.env.OPENROUTER_API_KEY;
  if (!key) return res.status(503).json({ error: 'no key' });
  const from = lang === 'kk' ? 'казахского' : 'русского', to = lang === 'kk' ? 'русский' : 'казахский';
  const msgs = [{ role: 'system', content: `Ты двуязычный словарь для школьников Казахстана. Переведи слово с ${from} на ${to} язык с учётом предложения. Ответь строго JSON без пояснений: {"lemma":"начальная форма слова на языке оригинала","tr":"перевод начальной формы, 1–3 слова"}` },
    { role: 'user', content: `Слово: ${w}\nПредложение: ${String(ctx || '').slice(0, 300)}` }];
  try {
    const { reply } = await firstReply((model) => callModel(model, msgs, key).then((reply) => {
      const m = /\{[\s\S]*\}/.exec(reply); const j = m && JSON.parse(m[0]);
      if (!j || typeof j.tr !== 'string' || !j.tr.trim()) throw new Error('bad json');
      return { reply: j };
    }));
    return res.status(200).json({ lemma: String(reply.lemma || w).slice(0, 40), tr: reply.tr.trim().slice(0, 80), mode: 'ai' });
  } catch (e) {
    return res.status(502).json({ error: 'ai unavailable' });
  }
}

module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
  const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0] || 'local';
  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch { body = null; } }
  // a whole class may share one school IP: the word translator and the helper have separate, larger budgets
  if (body && body.mode === 'word') {
    if (limited(ip + '|w', 120)) return res.status(429).json({ error: 'too many requests' });
    return translateWord(body, res);
  }
  const busy = limited(ip, 90);
  const { lang, unit: unitId, q: qId, phase, choice, messages } = body || {};
  if (!['kk', 'ru'].includes(lang) || !PHASES.has(phase) || !Array.isArray(messages) || !messages.length) return res.status(400).json({ error: 'bad request' });
  const unit = bank(lang).units.find((u) => u.id === unitId);
  const q = unit && unit.questions.find((x) => x.id === qId);
  if (!q) return res.status(400).json({ error: 'unknown question' });
  const turns = messages.slice(-MAX_TURNS).filter((m) => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string')
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_MSG) }));
  if (!turns.length || turns[turns.length - 1].role !== 'user') return res.status(400).json({ error: 'bad messages' });
  const userTurns = turns.filter((m) => m.role === 'user').length - 1;

  const key = process.env.OPENROUTER_API_KEY;
  if (!key) return res.status(200).json({ reply: hintReply(lang, q, userTurns), mode: 'mock' });
  if (busy) return res.status(200).json({ reply: hintReply(lang, q, userTurns), mode: 'fallback' });

  const msgs = [{ role: 'system', content: systemPrompt(lang, unit, q, phase, choice) }, ...turns];
  try {
    const { reply, model } = await firstReply((model) => callModel(model, msgs, key).then((reply) => ({ reply, model })));
    if (phase !== 'done' && leaks(reply, q)) return res.status(200).json({ reply: hintReply(lang, q, userTurns), mode: 'guarded' });
    return res.status(200).json({ reply, mode: 'ai', model });
  } catch (e) {
    return res.status(200).json({ reply: hintReply(lang, q, userTurns), mode: 'fallback' });
  }
};

module.exports.leaks = leaks;
module.exports.systemPrompt = systemPrompt;
