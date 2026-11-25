"""Python mirror of js/engine.js (BKT over 3 PISA reading processes + next-text selection).

Must stay numerically identical to the JS version: tests/test_engine.py checks both on one scenario.
"""
import json
import re
from pathlib import Path

SKILLS = ["locate", "understand", "evaluate"]
TRAPS = ["word_match", "near_detail", "outside_knowledge", "overgeneralize", "opposite", "misread_table"]
ROOT = Path(__file__).resolve().parent.parent


def load_params():
    return json.loads((ROOT / "data/bkt_params.json").read_text(encoding="utf-8"))


def load_bank(lang):
    return json.loads((ROOT / f"data/bank.{lang}.json").read_text(encoding="utf-8"))["units"]


def new_state(params):
    return {"v": 2, "skills": {s: {"p": params["p_init"], "n": 0, "c": 0} for s in SKILLS},
            "traps": {t: 0 for t in TRAPS}, "exposure": {t: 0 for t in TRAPS}, "diag": {d: 0 for d in DIAGNOSES},
            "done": {}, "answered": 0}


def slip_guess(params, difficulty):
    i = min(2, max(0, int(difficulty) - 1))
    return params["slip_by_difficulty"][i], params["guess_by_difficulty"][i]


def bkt_update(p, correct, slip, guess, learn):
    if correct:
        post = (p * (1 - slip)) / (p * (1 - slip) + (1 - p) * guess)
    else:
        post = (p * slip) / (p * slip + (1 - p) * (1 - guess))
    return post + (1 - post) * learn


def predict_correct(p, slip, guess):
    return p * (1 - slip) + (1 - p) * guess


DIAGNOSES = ["understood", "guessed", "found_wrong", "not_found"]


def bkt_update_evidence(p, correct, evidence_ok, slip, guess, params):
    lk = (1 - slip) if correct else slip
    lu = guess if correct else (1 - guess)
    if evidence_ok is True:
        lk *= 1 - params["evidence_miss"]
        lu *= params["evidence_guess"]
    elif evidence_ok is False:
        lk *= params["evidence_miss"]
        lu *= 1 - params["evidence_guess"]
    post = (p * lk) / (p * lk + (1 - p) * lu)
    return post + (1 - post) * params["p_learn"]


def diagnose(correct, evidence_ok):
    if correct:
        return "guessed" if evidence_ok is False else "understood"
    return "found_wrong" if evidence_ok is True else "not_found"


def apply_answer(state, params, question, correct, trap=None, evidence_ok=None):
    sk = state["skills"][question["process"]]
    slip, guess = slip_guess(params, question["difficulty"])
    before = sk["p"]
    sk["p"] = bkt_update_evidence(sk["p"], bool(correct), evidence_ok, slip, guess, params)
    if evidence_ok is not None:
        state["diag"][diagnose(bool(correct), evidence_ok)] += 1
    sk["n"] += 1
    if correct:
        sk["c"] += 1
    if not correct and trap in state["traps"]:
        state["traps"][trap] += 1
    offered = {o["trap"] for o in question["options"] if not o["correct"]}
    for t in TRAPS:
        if t in offered:
            state["exposure"][t] += 1
    state["answered"] += 1
    return {"skill": question["process"], "before": before, "after": sk["p"]}


def mark_unit_done(state, unit_id):
    state["done"][unit_id] = state["done"].get(unit_id, 0) + 1


def weakest_skill(state):
    best = SKILLS[0]
    for s in SKILLS:
        if state["skills"][s]["p"] < state["skills"][best]["p"]:
            best = s
    return best


def _unit_number(uid):
    m = re.search(r"(\d+)$", uid)
    return int(m.group(1)) if m else 0


def _order_key(u):
    return (_unit_number(u["id"]), u["id"])


def difficulty_of(q):
    return q.get("cal_difficulty") or q["difficulty"]


def unit_score(state, params, unit, grade):
    s = 0.0
    for q in unit["questions"]:
        p = state["skills"][q["process"]]["p"]
        target = 1 + 2 * p
        closeness = 1 - abs(difficulty_of(q) - target) / 2
        s += (1 - p) ** 2 * (0.5 + 0.5 * closeness)
    s = s / len(unit["questions"])
    s -= params["grade_penalty"] * abs(unit["grade"] - grade)
    s -= params["repeat_penalty"] * state["done"].get(unit["id"], 0)
    return s


def select_next_unit(state, params, units, grade):
    if not units:
        return None
    if state["answered"] == 0 and not state["done"]:
        same = sorted([u for u in units if u["grade"] == grade], key=_order_key)
        unit = (same or sorted(units, key=_order_key))[0]
        return {"unit": unit, "reason": {"kind": "start", "skill": None, "p": None, "count": 0}}
    best, best_score = None, float("-inf")
    for u in sorted(units, key=_order_key):
        sc = unit_score(state, params, u, grade)
        if sc > best_score + 1e-12:
            best, best_score = u, sc
    skill = weakest_skill(state)
    count = sum(1 for q in best["questions"] if q["process"] == skill)
    return {"unit": best, "reason": {"kind": "weak", "skill": skill, "p": state["skills"][skill]["p"], "count": count}}


def select_questions(state, params, unit):
    """Questions to ask in this text: skip skills already mastered (p >= mastery), keep at least 2."""
    qs = unit["questions"]
    keep = [q for q in qs if state["skills"][q["process"]]["p"] < params["mastery"]]
    if len(keep) >= 2:
        return keep
    ranked = sorted(range(len(qs)), key=lambda i: (state["skills"][qs[i]["process"]]["p"], i))[:2]
    return [qs[i] for i in sorted(ranked)]
