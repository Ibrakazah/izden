// Izden on-device "AI": Bayesian Knowledge Tracing over three PISA reading processes
// plus next-text selection for the weakest skill.
// Mirrored 1:1 in evals/engine.py; tests/test_engine.py runs both on the same scenario.
// Keep this file free of DOM / fetch so it can be evaluated outside the browser.

export const SKILLS = ['locate', 'understand', 'evaluate'];
export const TRAPS = ['word_match', 'near_detail', 'outside_knowledge', 'overgeneralize', 'opposite', 'misread_table'];

export function newState(params) {
  const skills = {};
  for (const s of SKILLS) skills[s] = { p: params.p_init, n: 0, c: 0 };
  const traps = {};
  for (const t of TRAPS) traps[t] = 0;
  return { v: 1, skills, traps, done: {}, answered: 0 };
}

function clamp(x, lo, hi) { return Math.min(hi, Math.max(lo, x)); }

export function slipGuess(params, difficulty) {
  const i = clamp((difficulty | 0) - 1, 0, 2);
  return [params.slip_by_difficulty[i], params.guess_by_difficulty[i]];
}

// Standard BKT step: Bayes posterior on the observation, then the learning transition.
export function bktUpdate(p, correct, slip, guess, learn) {
  let post;
  if (correct) {
    post = (p * (1 - slip)) / (p * (1 - slip) + (1 - p) * guess);
  } else {
    post = (p * slip) / (p * slip + (1 - p) * (1 - guess));
  }
  return post + (1 - post) * learn;
}

// Probability that the student answers this question correctly (first try).
export function predictCorrect(p, slip, guess) {
  return p * (1 - slip) + (1 - p) * guess;
}

// Only the FIRST attempt of a question is evidence for BKT (second attempt is learning support).
export function applyAnswer(state, params, question, correct, trap) {
  const sk = state.skills[question.process];
  const [slip, guess] = slipGuess(params, question.difficulty);
  const before = sk.p;
  sk.p = bktUpdate(sk.p, !!correct, slip, guess, params.p_learn);
  sk.n += 1;
  if (correct) sk.c += 1;
  if (!correct && trap && Object.prototype.hasOwnProperty.call(state.traps, trap)) state.traps[trap] += 1;
  state.answered += 1;
  return { skill: question.process, before, after: sk.p };
}

export function markUnitDone(state, unitId) {
  state.done[unitId] = (state.done[unitId] || 0) + 1;
}

export function weakestSkill(state) {
  let best = SKILLS[0];
  for (const s of SKILLS) if (state.skills[s].p < state.skills[best].p) best = s;
  return best;
}

function unitNumber(id) {
  const m = /(\d+)$/.exec(id);
  return m ? parseInt(m[1], 10) : 0;
}

export function unitScore(state, params, unit, grade) {
  let s = 0;
  for (const q of unit.questions) {
    const p = state.skills[q.process].p;
    const target = 1 + 2 * p;
    const closeness = 1 - Math.abs(q.difficulty - target) / 2;
    s += (1 - p) * (1 - p) * (0.5 + 0.5 * closeness);
  }
  s = s / unit.questions.length;
  s -= params.grade_penalty * Math.abs(unit.grade - grade);
  s -= params.repeat_penalty * (state.done[unit.id] || 0);
  return s;
}

// Returns {unit, reason:{kind:'start'|'weak', skill, p, count}}
export function selectNextUnit(state, params, units, grade) {
  if (!units.length) return null;
  const byNum = (a, b) => unitNumber(a.id) - unitNumber(b.id) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  if (state.answered === 0 && Object.keys(state.done).length === 0) {
    const same = units.filter(u => u.grade === grade).sort(byNum);
    const unit = (same.length ? same : units.slice().sort(byNum))[0];
    return { unit, reason: { kind: 'start', skill: null, p: null, count: 0 } };
  }
  let best = null;
  let bestScore = -Infinity;
  const sorted = units.slice().sort(byNum);
  for (const u of sorted) {
    const sc = unitScore(state, params, u, grade);
    if (sc > bestScore + 1e-12) { best = u; bestScore = sc; }
  }
  const skill = weakestSkill(state);
  const count = best.questions.filter(q => q.process === skill).length;
  return { unit: best, reason: { kind: 'weak', skill, p: state.skills[skill].p, count } };
}

// Questions to ask in this text: skip skills already mastered (p >= mastery), keep at least 2.
export function selectQuestions(state, params, unit) {
  const qs = unit.questions;
  const keep = qs.filter(q => state.skills[q.process].p < params.mastery);
  if (keep.length >= 2) return keep;
  const ranked = qs.map((q, i) => i)
    .sort((a, b) => (state.skills[qs[a].process].p - state.skills[qs[b].process].p) || (a - b))
    .slice(0, 2).sort((a, b) => a - b);
  return ranked.map(i => qs[i]);
}

export function conditionalLevel(state, params) {
  let sum = 0;
  for (const s of SKILLS) sum += state.skills[s].p;
  const avg = sum / SKILLS.length;
  let level = 1;
  for (const cut of params.level_cuts) if (avg >= cut) level += 1;
  return { level, avg };
}
