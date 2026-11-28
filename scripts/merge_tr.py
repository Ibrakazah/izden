#!/usr/bin/env python3
"""Merge translated reading texts (data/staging_tr/tr_*.json) into data/bank.<lang>.json and link twins.
  python3 scripts/merge_tr.py           # merge + passport entries
  python3 scripts/merge_tr.py blind     # write evals/tr_blind/<lang>.txt (translated units, no keys)
  python3 scripts/merge_tr.py score     # compare evals/tr_blind/answers.<lang>.json with the key, update passport"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_math import show_unit  # noqa: E402
from shuffle import display_order  # noqa: E402

ST = ROOT / "data/staging_tr"
BL = ROOT / "evals/tr_blind"
is_tr = lambda uid: uid[3:5] in ("r-", "k-")


def translated(lang):  # translations INTO lang
    src = "ru" if lang == "kk" else "kk"
    out = []
    for f in sorted(ST.glob(f"tr_{src}_*.json")):
        out += json.loads(f.read_text(encoding="utf-8"))["units"]
    return out


def merge():
    banks = {l: json.loads((ROOT / f"data/bank.{l}.json").read_text(encoding="utf-8")) for l in ("kk", "ru")}
    pp = ROOT / "data/passport.json"
    passport = json.loads(pp.read_text(encoding="utf-8"))
    for lang in ("kk", "ru"):
        units = [u for u in banks[lang]["units"] if not is_tr(u["id"])]
        tr = translated(lang)
        for u in units:
            u.pop("twin", None)
        other = "ru" if lang == "kk" else "kk"
        for u in tr:
            old = passport.get(u["id"], {})
            passport[u["id"]] = {"lang": lang, "tr": {"from": other}, **({"blind": old["blind"]} if "blind" in old else {})}
        units += tr
        units.sort(key=lambda u: (u["grade"], u["id"]))
        banks[lang]["units"] = units
    # originals point at their translation
    for lang in ("kk", "ru"):
        other = "ru" if lang == "kk" else "kk"
        tw = {u["twin"]: u["id"] for u in banks[other]["units"] if u.get("twin")}
        for u in banks[lang]["units"]:
            if not is_tr(u["id"]) and u["id"] in tw:
                u["twin"] = tw[u["id"]]
    for lang in ("kk", "ru"):
        (ROOT / f"data/bank.{lang}.json").write_text(json.dumps(banks[lang], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        n = len(banks[lang]["units"])
        print(f"bank.{lang}: {n} units ({sum(is_tr(u['id']) for u in banks[lang]['units'])} translated)")
    pp.write_text(json.dumps(passport, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def blind():
    BL.mkdir(parents=True, exist_ok=True)
    for lang in ("kk", "ru"):
        us = translated(lang)
        (BL / f"{lang}.txt").write_text("\n\n".join(show_unit(u) for u in us) + "\n", encoding="utf-8")
        print(lang, len(us), "units")


def score():
    pp = ROOT / "data/passport.json"
    passport = json.loads(pp.read_text(encoding="utf-8"))
    for lang in ("kk", "ru"):
        f = BL / f"answers.{lang}.json"
        if not f.exists():
            continue
        ans = json.loads(f.read_text(encoding="utf-8"))
        miss = []
        tot = 0
        for u in translated(lang):
            m = 0
            for q in u["questions"]:
                order = display_order(u["id"], q)
                k = "ABCD"[[q["options"][i]["correct"] for i in order].index(True)]
                got = str(ans.get(f"{u['id']}/{q['id']}", "")).strip().upper()[:1]
                tot += 1
                if got == k:
                    m += 1
                else:
                    miss.append(f"{u['id']}/{q['id']} key {k} solver {got or '-'}")
            if u["id"] in passport:
                passport[u["id"]]["blind"] = {"match": m, "total": len(u["questions"])}
        print(f"blind {lang}: {tot - len(miss)}/{tot} match")
        for x in miss:
            print("  MISMATCH", x)
    pp.write_text(json.dumps(passport, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    {"blind": blind, "score": score}.get(sys.argv[1] if len(sys.argv) > 1 else "", merge)()
