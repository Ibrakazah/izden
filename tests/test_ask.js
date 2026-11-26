// node tests/test_ask.js — the AI helper never returns the right option before the question is finished,
// and works without a key (mock mode). No network.
const assert = require('assert');
const fs = require('fs');
delete process.env.OPENROUTER_API_KEY;
const h = require('../api/ask.js');
const bank = JSON.parse(fs.readFileSync(__dirname + '/../data/bank.ru.json', 'utf8'));
const q = bank.units.find((u) => u.id === 'ru-bus-01').questions[0];
assert.strictEqual(h.leaks('Правильный ответ — рейс 103.', q), true);
assert.strictEqual(h.leaks('Это 103', q), true);
assert.strictEqual(h.leaks('Посмотри на колонку «Прибытие в райцентр» и сравни с 15:00.', q), false);
const call = (body) => new Promise((ok) => { const res = { setHeader() {}, status(c) { this.c = c; return this; }, json(j) { ok([this.c, j]); } }; h({ method: 'POST', headers: {}, body }, res); });
(async () => {
  let [c, j] = await call({ lang: 'ru', unit: 'ru-bus-01', q: 'q1', phase: 'retry', messages: [{ role: 'user', content: 'помоги' }] });
  assert.strictEqual(c, 200); assert.strictEqual(j.mode, 'mock'); assert.ok(j.reply.includes(q.hint_steps[0]));
  [c] = await call({ lang: 'ru', unit: 'ru-bus-01', q: 'q1', phase: 'evidence', messages: [{ role: 'user', content: 'x' }] });
  assert.strictEqual(c, 400, 'no help before the first answer');
  [c] = await call({ lang: 'ru', unit: 'nope', q: 'q1', phase: 'retry', messages: [{ role: 'user', content: 'x' }] });
  assert.strictEqual(c, 400);
  console.log('OK: leak guard, mock mode and input checks');
})().catch((e) => { console.error(e); process.exit(1); });
