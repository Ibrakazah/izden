#!/usr/bin/env python3
"""Cross-check js/engine.js and evals/engine.py on one fixed scenario.

1. Runs the scenario in Python.
2. If `osascript` (macOS JavaScriptCore) is available, runs the same scenario through js/engine.js
   and compares every number (tolerance 1e-9); then refreshes tests/engine_expected.json.
3. Otherwise compares Python with the committed tests/engine_expected.json (exported from the JS run).
Run: python3 tests/test_engine.py   (or python3 -m pytest tests/)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))
import engine as E  # noqa: E402

SCENARIO = {"lang": "ru", "grade": 8, "units": 14, "pattern": [1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1],
            "evidence": [1, 1, 0, 2, 1, 0, 1]}  # 1 = right evidence, 0 = wrong, 2 = not collected
EXPECTED = ROOT / "tests/engine_expected.json"


def run_python():
    params = E.load_params()
    units = E.load_bank(SCENARIO["lang"])
    state = E.new_state(params)
    trace, k = [], 0
    for _ in range(SCENARIO["units"]):
        sel = E.select_next_unit(state, params, units, SCENARIO["grade"])
        answers = []
        for q in E.select_questions(state, params, sel["unit"]):
            ok = SCENARIO["pattern"][k % len(SCENARIO["pattern"])] == 1
            k += 1
            wrong = next(o for o in q["options"] if not o["correct"])
            ev = SCENARIO["evidence"][k % len(SCENARIO["evidence"])]
            r = E.apply_answer(state, params, q, ok, None if ok else wrong["trap"], None if ev == 2 else ev == 1)
            answers.append([q["id"], r["skill"], r["after"]])
        E.mark_unit_done(state, sel["unit"]["id"])
        trace.append({"unit": sel["unit"]["id"], "reason": sel["reason"], "answers": answers})
    return {"trace": trace, "final": state}


def run_js():
    if not shutil.which("osascript"):
        return None
    eng = (ROOT / "js/engine.js").read_text(encoding="utf-8")
    eng = re.sub(r"^export\s+", "", eng, flags=re.M)
    runner = (ROOT / "tests/scenario_runner.js").read_text(encoding="utf-8")
    params = (ROOT / "data/bkt_params.json").read_text(encoding="utf-8")
    bank = (ROOT / f"data/bank.{SCENARIO['lang']}.json").read_text(encoding="utf-8")
    src = (eng + "\n" + runner + "\n"
           + f"var PARAMS = {params};\nvar BANK = ({bank}).units;\nvar SCENARIO = {json.dumps(SCENARIO)};\n"
           + "JSON.stringify(runScenario(BANK, PARAMS, SCENARIO));\n")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(src)
        path = f.name
    out = subprocess.run(["osascript", "-l", "JavaScript", path], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError("JS run failed: " + out.stderr[:2000])
    return json.loads(out.stdout)


def compare(a, b, path="$"):
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), f"{path}: keys differ {set(a) ^ set(b)}"
        for k in a:
            compare(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), f"{path}: length differs"
        for i, (x, y) in enumerate(zip(a, b)):
            compare(x, y, f"{path}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert abs(float(a) - float(b)) < 1e-9, f"{path}: {a} != {b}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def test_engine_js_python_match():
    py = run_python()
    js = run_js()
    if js is not None:
        compare(py, js)
        src = "live JS (osascript/JavaScriptCore)"
        if "--update" in sys.argv:  # refresh the golden file only on request
            EXPECTED.write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
            src += "; golden file updated"
    else:
        print("NOTE: osascript not found, comparing with the golden file exported from JS earlier")
        compare(py, json.loads(EXPECTED.read_text(encoding="utf-8")))
        src = "tests/engine_expected.json"
    # sanity: probabilities in range, adaptive selection never repeats a unit within 10 steps
    units = [t["unit"] for t in py["trace"]]
    assert len(set(units)) == len(units), "unit repeated"
    for t in py["trace"]:
        for _, _, p in t["answers"]:
            assert 0 < p < 1
    return src, py


def test_bkt_direction():
    params = E.load_params()
    s, g = E.slip_guess(params, 2)
    assert E.bkt_update(0.3, True, s, g, params["p_learn"]) > 0.3
    assert E.bkt_update(0.3, False, s, g, 0.0) < 0.3
    proved = E.bkt_update_evidence(0.3, True, True, s, g, params)
    guessed = E.bkt_update_evidence(0.3, True, False, s, g, params)
    assert proved > guessed, "right answer without evidence must count less"
    assert E.diagnose(True, False) == "guessed" and E.diagnose(False, True) == "found_wrong"


if __name__ == "__main__":
    test_bkt_direction()
    src, py = test_engine_js_python_match()
    print(f"OK: Python engine matches {src} on {sum(len(t['answers']) for t in py['trace'])} answers, "
          f"units: {', '.join(t['unit'] for t in py['trace'])}")
