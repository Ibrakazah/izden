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
  const diag = {};
  for (const d of DIAGNOSES) diag[d] = 0;
  return { v: 2, skills, traps, diag, done: {}, answered: 0 };
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

// BKT step with two observations: the answer and the evidence the student tapped first.
// evidenceOk: true / false, or null when evidence was not collected (paper mode).
// A right answer without the right evidence is weak evidence of knowing ("guessed - prove it").
export function bktUpdateEvidence(p, correct, evidenceOk, slip, guess, params) {
  let lk = correct ? 1 - slip : slip;
  let lu = correct ? guess : 1 - guess;
  if (evidenceOk === true) { lk *= 1 - params.evidence_miss; lu *= params.evidence_guess; }
  if (evidenceOk === false) { lk *= params.evidence_miss; lu *= 1 - params.evidence_guess; }
  const post = (p * lk) / (p * lk + (1 - p) * lu);
  return post + (1 - post) * params.p_learn;
}

// 2x2 diagnosis: answer right? x evidence right?
export function diagnose(correct, evidenceOk) {
  if (correct) return evidenceOk === false ? 'guessed' : 'understood';
  return evidenceOk === true ? 'found_wrong' : 'not_found';
}
export const DIAGNOSES = ['understood', 'guessed', 'found_wrong', 'not_found'];

// Only the FIRST attempt of a question is evidence for BKT (second attempt is learning support).
export function applyAnswer(state, params, question, correct, trap, evidenceOk = null) {
  const sk = state.skills[question.process];
  const [slip, guess] = slipGuess(params, question.difficulty);
  const before = sk.p;
  sk.p = bktUpdateEvidence(sk.p, !!correct, evidenceOk, slip, guess, params);
  if (evidenceOk !== null) state.diag[diagnose(!!correct, evidenceOk)] += 1;
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

// Calibrated difficulty from AI-student runs if present, otherwise the author's estimate.
export function difficultyOf(q) { return q.cal_difficulty || q.difficulty; }

export function unitScore(state, params, unit, grade) {
  let s = 0;
  for (const q of unit.questions) {
    const p = state.skills[q.process].p;
    const target = 1 + 2 * p;
    const closeness = 1 - Math.abs(difficultyOf(q) - target) / 2;
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
