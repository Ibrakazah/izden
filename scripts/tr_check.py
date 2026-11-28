#!/usr/bin/env python3
"""Check a translated batch against its source: same structure, sentence counts, evidence, keys and numbers.
Usage: python3 scripts/tr_check.py SRC.json TR.json"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import sentences  # noqa: E402

nums = lambda s: sorted(re.findall(r"\d+(?:[.,:]\d+)?", json.dumps(s, ensure_ascii=False)))


def twin_id(uid):
    lang, rest = uid.split("-", 1)
    return ("kk-r-" if lang == "ru" else "ru-k-") + rest


def compare(a, b):
    e = []
    if b.get("id") != twin_id(a["id"]):
        e.append(f"id must be {twin_id(a['id'])}")
    if b.get("twin") != a["id"]:
        e.append(f"twin must be {a['id']}")
    for f in ("grade", "format", "context"):
        if a.get(f) != b.get(f):
            e.append(f"{f} differs")
    if [(x["id"], x["type"]) for x in a["blocks"]] != [(x.get("id"), x.get("type")) for x in b["blocks"]]:
        return e + ["blocks: ids/types differ"]
    for x, y in zip(a["blocks"], b["blocks"]):
        t = x["type"]
        if t == "p" and len(sentences(x["text"])) != len(sentences(y["text"])):
            e.append(f"{x['id']}: {len(sentences(x['text']))} sentences in source, {len(sentences(y['text']))} in translation")
        if t == "list" and len(x["items"]) != len(y["items"]):
            e.append(f"{x['id']}: list length differs")
        if t in ("table", "chart"):
            if len(x["rows"]) != len(y["rows"]) or any(len(r) != len(s) for r, s in zip(x["rows"], y["rows"])):
                e.append(f"{x['id']}: table/chart shape differs")
            if t == "chart" and [r[1] for r in x["rows"]] != [r[1] for r in y["rows"]]:
                e.append(f"{x['id']}: chart values differ")
        if nums(x) != nums(y):
            e.append(f"{x['id']}: numbers differ {sorted(set(nums(x)) ^ set(nums(y)))}")
    if [q["id"] for q in a["questions"]] != [q.get("id") for q in b["questions"]]:
        return e + ["question ids differ"]
    for q, r in zip(a["questions"], b["questions"]):
        for f in ("process", "difficulty", "evidence", "cal_difficulty", "p_ai"):
            if q.get(f) != r.get(f):
                e.append(f"{q['id']}: {f} differs")
        if [(o["id"], o["correct"], o.get("trap")) for o in q["options"]] != [(o.get("id"), o.get("correct"), o.get("trap")) for o in r["options"]]:
            e.append(f"{q['id']}: options id/correct/trap differ")
        if len(q["hint_steps"]) != len(r.get("hint_steps", [])):
            e.append(f"{q['id']}: hint_steps count differs")
    return e


def main(src, tr):
    A = json.loads(Path(src).read_text(encoding="utf-8"))["units"]
    B = json.loads(Path(tr).read_text(encoding="utf-8"))["units"]
    bad = 0
    if len(A) != len(B):
        print(f"ERR unit count {len(A)} vs {len(B)}")
        bad += 1
    for a, b in zip(A, B):
        for x in compare(a, b):
            print(f"ERR {a['id']}: {x}")
            bad += 1
    print("OK" if not bad else f"FAILED: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
