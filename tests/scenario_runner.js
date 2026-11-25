// Runs a fixed scenario with js/engine.js (export keywords stripped by the test) and prints JSON.
// Inputs are injected as globals: BANK (units), PARAMS, SCENARIO.
function runScenario(units, params, scenario) {
  const state = newState(params);
  const trace = [];
  let k = 0;
  for (let step = 0; step < scenario.units; step++) {
    const sel = selectNextUnit(state, params, units, scenario.grade);
    const answers = [];
    for (const q of selectQuestions(state, params, sel.unit)) {
      const ok = scenario.pattern[k % scenario.pattern.length] === 1;
      k += 1;
      const wrong = q.options.find(o => !o.correct);
      const r = applyAnswer(state, params, q, ok, ok ? null : wrong.trap);
      answers.push([q.id, r.skill, r.after]);
    }
    markUnitDone(state, sel.unit.id);
    trace.push({ unit: sel.unit.id, reason: sel.reason, answers,
                 level: conditionalLevel(state, params) });
  }
  return { trace, final: state };
}
