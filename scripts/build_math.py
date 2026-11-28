#!/usr/bin/env python3
"""Maths bank pipeline.

  python3 scripts/build_math.py parity      # ru <-> kk: same structure, keys, evidence and numbers
  python3 scripts/build_math.py blind       # write evals/math_blind/<topic>.ru.txt without keys (for a blind solver)
  python3 scripts/build_math.py score       # compare evals/math_blind/answers_*.json with the key
  python3 scripts/build_math.py build [ID ...]  # merge staging into data/math.<lang>.json (IDs = rejected unit suffixes)
                                                # and add maths entries to data/passport.json
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check import validate_file  # noqa: E402
from shuffle import display_order  # noqa: E402

ST = ROOT / "data/staging_math"
BL = ROOT / "evals/math_blind"
TOPICS = ["percent", "money", "ratio", "data", "geometry"]


def load(lang):
    units = []
    for f in sorted(ST.glob(f"*.{lang}.json")):
        errs, us = validate_file(f)
        if errs:
            print(f"SKIP {f.name}: {len(errs)} schema errors")
            continue
        units += us
    return units


def suffix(uid):
    return uid.split("-", 1)[1]


def nums(s):
    # sorted: word order differs between the languages
    return sorted(re.findall(r"\d+(?:[.,]\d+)?", str(s)))


def parity():
    ru = {suffix(u["id"]): u for u in load("ru")}
    kk = {suffix(u["id"]): u for u in load("kk")}
    bad = {}
    for k in sorted(set(ru) | set(kk)):
        e = []
        a, b = ru.get(k), kk.get(k)
        if not a or not b:
            bad[k] = ["missing in " + ("kk" if a else "ru")]
            continue
        for f in ("grade", "format", "context", "topic", "subject"):
            if a.get(f) != b.get(f):
                e.append(f"{f} differs")
        if a.get("subject") != "math" or a.get("topic") not in TOPICS:
            e.append("bad subject/topic")
        if [(x["id"], x["type"]) for x in a["blocks"]] != [(x["id"], x["type"]) for x in b["blocks"]]:
            e.append("blocks differ")
        elif nums(json.dumps(a["blocks"], ensure_ascii=False)) != nums(json.dumps(b["blocks"], ensure_ascii=False)):
            e.append("numbers in the task text differ")
        if len(a["questions"]) != len(b["questions"]):
            e.append("question count differs")
        else:
            for qa, qb in zip(a["questions"], b["questions"]):
                for f in ("id", "process", "difficulty", "evidence"):
                    if qa[f] != qb[f]:
                        e.append(f"{qa['id']}: {f} differs")
                oa = [(o["id"], o["correct"], o.get("trap"), nums(o["text"])) for o in qa["options"]]
                ob = [(o["id"], o["correct"], o.get("trap"), nums(o["text"])) for o in qb["options"]]
                if oa != ob:
                    e.append(f"{qa['id']}: options differ (id/correct/trap/numbers)")
                if nums(qa["stem"]) != nums(qb["stem"]):
                    e.append(f"{qa['id']}: numbers in the stem differ")
        if e:
            bad[k] = e
    for k, e in bad.items():
        print("PARITY", k, "; ".join(e))
    print(f"parity: {len(set(ru) | set(kk)) - len(bad)} ok, {len(bad)} with problems")
    return bad


def show_unit(u):
    out = [f"=== {u['id']} | {u['title']}"]
    for b in u["blocks"]:
        t = b["type"]
        if t in ("h", "p"):
            out.append(b["text"])
        elif t == "list":
            out += ["- " + i for i in b["items"]]
        elif t == "table":
            if b.get("caption"):
                out.append(b["caption"] + ":")
            out += [" | ".join(map(str, r)) for r in b["rows"]]
        elif t == "chart":
            out.append(f"{b['caption']} ({b.get('unit', '')}):")
            out += [f"{r[0]}: {r[1]}" for r in b["rows"]]
    for q in u["questions"]:
        out.append(f"\n[{u['id']}/{q['id']}] {q['stem']}")
        for n, i in enumerate(display_order(u["id"], q)):
            out.append(f"  {'ABCD'[n]}) {q['options'][i]['text']}")
    return "\n".join(out)


def blind():
    BL.mkdir(parents=True, exist_ok=True)
    for lang in ("ru", "kk"):
        units = load(lang)
        for tp in TOPICS:
            us = [u for u in units if u.get("topic") == tp]
            (BL / f"{tp}.{lang}.txt").write_text("\n\n".join(show_unit(u) for u in us) + "\n", encoding="utf-8")
            print(tp, lang, len(us), "units")


def key(lang):
    k = {}
    for u in load(lang):
        for q in u["questions"]:
            order = display_order(u["id"], q)
            k[f"{u['id']}/{q['id']}"] = "ABCD"[[q["options"][i]["correct"] for i in order].index(True)]
    return k


def score():
    res = {}
    for lang in ("ru", "kk"):
        k = key(lang)
        ans = {}
        for f in sorted(BL.glob(f"answers_*.{lang}.json")):
            ans.update(json.loads(f.read_text(encoding="utf-8")))
        if not ans:
            continue
        miss = [x for x in k if x in ans and str(ans[x]).strip().upper()[:1] != k[x]]
        absent = [x for x in k if x not in ans]
        print(f"blind {lang}: {len(k) - len(miss) - len(absent)}/{len(k)} match, {len(miss)} mismatch, {len(absent)} unanswered")
        for x in miss:
            print("  MISMATCH", x, "key", k[x], "solver", ans[x])
        res[lang] = {"key": k, "ans": ans}
    return res


def build(reject):
    reject = set(reject)
    sc = score()
    pp = ROOT / "data/passport.json"
    passport = {k: v for k, v in json.loads(pp.read_text(encoding="utf-8")).items() if not v.get("math")}
    for lang in ("kk", "ru"):
        units = [u for u in load(lang) if suffix(u["id"]) not in reject]
        units.sort(key=lambda u: (TOPICS.index(u["topic"]), u["id"]))
        out = {"version": 1, "lang": lang, "subject": "math", "units": units}
        (ROOT / f"data/math.{lang}.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        s = sc.get(lang) or sc.get("ru")
        for u in units:
            ids = [f"{u['id']}/{q['id']}" for q in u["questions"]]
            if s is sc.get("ru") and lang != "ru":
                ids = [x.replace(lang + "-", "ru-", 1) for x in ids]
            m = sum(1 for x in ids if s and str(s["ans"].get(x, "")).strip().upper()[:1] == s["key"].get(x))
            passport[u["id"]] = {"lang": lang, "math": True, "blind": {"match": m, "total": len(ids)}}
        print(f"math.{lang}: {len(units)} units, {sum(len(u['questions']) for u in units)} questions")
    pp.write_text(json.dumps(passport, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "parity":
        sys.exit(1 if parity() else 0)
    elif cmd == "blind":
        blind()
    elif cmd == "score":
        score()
    elif cmd == "build":
        build(sys.argv[2:])
    else:
        print(__doc__)
