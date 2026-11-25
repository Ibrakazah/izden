#!/usr/bin/env python3
"""Shape cues in options: share of questions where the correct option is the longest (ties count),
and correct-answer positions as STORED and as DISPLAYED (after the deterministic shuffle used by the app).

  python3 scripts/option_stats.py data/staging/kk_A.json ...   (or no args: both banks)
  python3 scripts/option_stats.py --list FILE                    list questions where correct is longest
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from shuffle import display_order  # noqa: E402


def stats(units):
    n = longest = 0
    stored, shown = [0, 0, 0, 0], [0, 0, 0, 0]
    lst = []
    for u in units:
        for q in u["questions"]:
            n += 1
            c = next(o for o in q["options"] if o["correct"])
            w = max(len(o["text"]) for o in q["options"] if not o["correct"])
            if len(c["text"]) >= w:
                longest += 1
                lst.append(f"{u['id']}/{q['id']}")
            stored[[o["correct"] for o in q["options"]].index(True)] += 1
            order = display_order(u["id"], q)
            shown[[q["options"][i]["correct"] for i in order].index(True)] += 1
    return {"questions": n, "correct_longest": longest, "correct_longest_share": round(longest / max(1, n), 3),
            "stored_positions": stored, "displayed_positions": shown}, lst


def load(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d["units"] if isinstance(d, dict) else d


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--list":
        for f in args[1:]:
            print("\n".join(stats(load(f))[1]))
        sys.exit(0)
    files = args or [ROOT / "data/bank.kk.json", ROOT / "data/bank.ru.json"]
    for f in files:
        print(f, json.dumps(stats(load(f))[0]))
