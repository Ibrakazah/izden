#!/usr/bin/env python3
"""Build data/passport.json: per-unit "how this task was made and checked" for the in-app passport.

Reads the QA pipeline artifacts in evals/pipeline/ and evals/ai_students/calibration.json.
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EV = ROOT / "evals/pipeline"


def load(p):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def key_of(units):
    return {(u["id"], q["id"]): next(o["id"] for o in q["options"] if o["correct"]) for u in units for q in u["questions"]}


def main():
    cal = (load(ROOT / "evals/ai_students/calibration.json") or {}).get("per_question", {})
    deep = load(EV / "fixes/kk_demo_proofread.json") or {"units": [], "changes": []}
    deep_counts = Counter(c["unit"] for c in deep["changes"])
    out = {}
    for lang in ("kk", "ru"):
        bank = load(ROOT / f"data/bank.{lang}.json")["units"]
        final_key = key_of(bank)
        batches = {}
        for f in sorted((ROOT / "data/staging").glob(f"{lang}_*.json")):
            for u in load(f)["units"]:
                batches[u["id"]] = f.stem.split("_")[1]
        r1_key = {}
        for f in sorted((EV / "raw_round1").glob(f"{lang}_*.json")):
            r1_key.update(key_of(load(f)["units"]))
        solved_r1 = {(a["unit"], a["q"]): a for a in (load(EV / f"solved/{lang}_round1.json") or {"answers": []})["answers"]}
        solved_fin = {(a["unit"], a["q"]): a for a in (load(EV / f"solved/{lang}_final.json") or {"answers": []})["answers"]}
        reviews = {}
        for rnd in (1, 2):
            lr = load(EV / f"lang/{lang}_round{rnd}.json") or {"issues": [], "unit_verdicts": []}
            fx = load(EV / f"fixes/{lang}_round{rnd}.json") or {"applied": [], "skipped": []}
            for v in lr["unit_verdicts"]:
                uid = v["unit"]
                sev = Counter(i["severity"] for i in lr["issues"] if i["unit"] == uid)
                reviews[uid] = {
                    "round": rnd, "verdict": v.get("verdict"), "language_score": v.get("language_score"),
                    "issues": {k: sev.get(k, 0) for k in ("critical", "major", "minor")},
                    "fixed": sum(1 for a in fx["applied"] if a["unit"] == uid),
                    "skipped": sum(1 for a in fx["skipped"] if a["unit"] == uid),
                }
        for u in bank:
            uid = u["id"]
            qids = [q["id"] for q in u["questions"]]
            b = batches.get(uid, "?")
            rnd = 1 if b in ("A", "B") else 2
            r1 = None
            if rnd == 1:
                r1 = {"match": sum(1 for q in qids if solved_r1.get((uid, q), {}).get("answer") == r1_key.get((uid, q))),
                      "total": len(qids)}
            fin = {"match": sum(1 for q in qids if solved_fin.get((uid, q), {}).get("answer") == final_key[(uid, q)]),
                   "ambiguous": sum(1 for q in qids if solved_fin.get((uid, q), {}).get("ambiguous")),
                   "total": len(qids)}
            p_ai = [cal.get(f"{uid}/{q}", {}).get("p_ai") for q in qids]
            p_ai = [x for x in p_ai if x is not None]
            out[uid] = {
                "lang": lang, "batch": b, "round": rnd,
                "blind_round1": r1, "blind_final": fin,
                "review": reviews.get(uid),
                "deep_proofread": deep_counts.get(uid, 0) if uid in deep.get("units", []) else None,
                "rejected": 0,
                "ai_students": {"p_ai": round(sum(p_ai) / len(p_ai), 2) if p_ai else None, "personas": 4},
                "native_review": "needed" if lang == "kk" else "not_needed",
            }
    (ROOT / "data/passport.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"passport: {len(out)} units")


if __name__ == "__main__":
    main()
