#!/usr/bin/env python3
"""Content QA pipeline helpers.

  python3 scripts/pipeline.py blind data/staging/kk_A.json evals/pipeline/blind/kk_A.txt
      -> text + questions WITHOUT keys/traps/evidence/hints (input for the blind solver agent)
  python3 scripts/pipeline.py score data/staging/kk_A.json evals/pipeline/solved/kk_A.json
      -> compares blind answers with the key, prints mismatches, writes a JSON summary next to answers

Blind answers format (written by the solver agent):
  {"answers":[{"unit":"kk-bus-01","q":"q1","answer":"c","evidence":"b2:r3",
               "ambiguous":false,"note":"..."}]}
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import sentences, load_units  # noqa: E402


def render_text(u):
    out = [f"=== UNIT {u['id']} | grade {u['grade']} | {u['title']}"]
    for b in u["blocks"]:
        t = b["type"]
        if t == "h":
            out.append(f"[{b['id']}] # {b['text']}")
        elif t == "p":
            for i, s in enumerate(sentences(b["text"]), 1):
                out.append(f"[{b['id']}:s{i}] {s}")
        elif t == "list":
            for i, s in enumerate(b["items"], 1):
                out.append(f"[{b['id']}:i{i}] - {s}")
        elif t == "table":
            if b.get("caption"):
                out.append(f"[{b['id']}] TABLE: {b['caption']}")
            out.append(f"[{b['id']}:header] " + " | ".join(map(str, b["rows"][0])))
            for i, r in enumerate(b["rows"][1:], 1):
                out.append(f"[{b['id']}:r{i}] " + " | ".join(map(str, r)))
        elif t == "chart":
            out.append(f"[{b['id']}] BAR CHART: {b['caption']} ({b.get('unit', '')})")
            for i, r in enumerate(b["rows"], 1):
                out.append(f"[{b['id']}:r{i}] {r[0]}: {r[1]}")
    return out


def blind(src, dst):
    units, _ = load_units(src)
    out = []
    for u in units:
        out += render_text(u)
        out.append("")
        for q in u["questions"]:
            out.append(f"--- {u['id']} {q['id']}: {q['stem']}")
            for o in q["options"]:
                out.append(f"    ({o['id']}) {o['text']}")
        out.append("")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {dst}")


def score(src, answers_path):
    units, _ = load_units(src)
    key = {}
    for u in units:
        for q in u["questions"]:
            corr = next(o["id"] for o in q["options"] if o["correct"])
            key[(u["id"], q["id"])] = (corr, q["evidence"])
    ans = json.loads(Path(answers_path).read_text(encoding="utf-8"))["answers"]
    seen = set()
    res = {"total": len(key), "answered": 0, "match": 0, "mismatch": [], "ambiguous": [], "evidence_block_match": 0}
    for a in ans:
        k = (a["unit"], a["q"])
        if k not in key or k in seen:
            continue
        seen.add(k)
        res["answered"] += 1
        corr, ev = key[k]
        if a.get("answer") == corr:
            res["match"] += 1
        else:
            res["mismatch"].append({"unit": k[0], "q": k[1], "key": corr, "solver": a.get("answer"),
                                    "note": a.get("note", "")})
        if a.get("ambiguous"):
            res["ambiguous"].append({"unit": k[0], "q": k[1], "note": a.get("note", "")})
        sb = str(a.get("evidence", "")).split(":")[0]
        if sb and any(str(e).split(":")[0] == sb for e in ev):
            res["evidence_block_match"] += 1
    res["missing"] = [f"{u} {q}" for (u, q) in key if (u, q) not in seen]
    out = Path(answers_path).with_suffix(".score.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{src}: {res['match']}/{res['total']} match, {len(res['mismatch'])} mismatch, "
          f"{len(res['ambiguous'])} flagged ambiguous, evidence block match {res['evidence_block_match']}/{res['answered']}")
    for m in res["mismatch"]:
        print("  MISMATCH", m)
    for m in res["ambiguous"]:
        print("  AMBIGUOUS", m)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "blind":
        blind(sys.argv[2], sys.argv[3])
    elif cmd == "score":
        score(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
