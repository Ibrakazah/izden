#!/usr/bin/env python3
"""Shape cues in answer options (a student should not be able to guess the key without reading).

For every question we compute how often simple "test-wise" strategies would pick the correct option:
  longest, second-longest, shortest, closest-to-mean-length (ties: expected value under random tie-break),
plus the distribution of the correct option's length rank and its displayed position (after the app shuffle).
Each strategy and each rank should stay <= 35% (random guessing gives 25-33%).

  python3 scripts/option_stats.py [FILES...]          aggregate report (default: both banks)
  python3 scripts/option_stats.py --targets FILES...  per question: current length rank of the correct option and a
                                                      target rank that spreads ranks evenly (for editors)
"""
import json
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from shuffle import display_order  # noqa: E402

LIMIT = 0.35
STRATS = ("longest", "second", "shortest", "closest_mean")


def _pick_prob(lengths, ci, position):
    """P(correct) when a strategy takes the option at `position` of the length-sorted (desc) list, random tie-break."""
    order = sorted(range(len(lengths)), key=lambda i: -lengths[i])
    target_len = lengths[order[position]]
    group = [i for i in range(len(lengths)) if lengths[i] == target_len]
    return (1 / len(group)) if ci in group else 0.0


def question_cues(q):
    lengths = [len(o["text"]) for o in q["options"]]
    ci = next(i for i, o in enumerate(q["options"]) if o["correct"])
    n = len(lengths)
    mean = sum(lengths) / n
    dist = [abs(x - mean) for x in lengths]
    closest = [i for i in range(n) if dist[i] == min(dist)]
    rank = 1 + sum(1 for x in lengths if x > lengths[ci]) + (sum(1 for x in lengths if x == lengths[ci]) - 1) / 2
    return {
        "longest": _pick_prob(lengths, ci, 0),
        "second": _pick_prob(lengths, ci, 1),
        "shortest": _pick_prob(lengths, ci, n - 1),
        "closest_mean": (1 / len(closest)) if ci in closest else 0.0,
        "rank": rank, "n": n,
    }


def stats(units):
    n = 0
    acc = {s: 0.0 for s in STRATS}
    ranks = {1: 0, 2: 0, 3: 0, 4: 0}
    shown = [0, 0, 0, 0]
    longest_list = []
    for u in units:
        for q in u["questions"]:
            n += 1
            c = question_cues(q)
            for s in STRATS:
                acc[s] += c[s]
            r = int(round(c["rank"]))
            ranks[min(4, max(1, r))] += 1
            if c["longest"] > 0:
                longest_list.append(f"{u['id']}/{q['id']}")
            order = display_order(u["id"], q)
            shown[[q["options"][i]["correct"] for i in order].index(True)] += 1
    share = {s: round(acc[s] / max(1, n), 3) for s in STRATS}
    return {"questions": n, "strategy_accuracy": share, "rank_counts": ranks,
            "rank_shares": {k: round(v / max(1, n), 3) for k, v in ranks.items()},
            "correct_longest": round(acc["longest"], 1), "correct_longest_share": share["longest"],
            "displayed_positions": shown}, longest_list


def problems(st):
    out = []
    for s, v in st["strategy_accuracy"].items():
        if v > LIMIT:
            out.append(f"strategy '{s}' finds the key in {v:.0%} of questions (limit {LIMIT:.0%})")
    for r, v in st["rank_shares"].items():
        if v > LIMIT:
            out.append(f"correct option has length rank {r} in {v:.0%} of questions (limit {LIMIT:.0%})")
    if max(st["displayed_positions"]) > 0.40 * st["questions"]:
        out.append("one displayed position holds > 40% of correct answers")
    return out


def target_rank(uid, q):
    """Deterministic spread of target ranks 1..n over questions (crc32 of the id)."""
    return 1 + zlib.crc32(f"{uid}/{q['id']}".encode()) % len(q["options"])


def load(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d["units"] if isinstance(d, dict) else d


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--targets":
        for f in args[1:]:
            for u in load(f):
                for q in u["questions"]:
                    c = question_cues(q)
                    t = target_rank(u["id"], q)
                    lens = [len(o["text"]) for o in q["options"]]
                    flag = "" if abs(c["rank"] - t) < 0.75 else "  <-- change"
                    print(f"{u['id']}/{q['id']}: correct rank {c['rank']:.1f} of {c['n']}, target {t}, lengths {lens}{flag}")
        sys.exit(0)
    files = args or [ROOT / "data/bank.kk.json", ROOT / "data/bank.ru.json"]
    bad = 0
    units_all = []
    for f in files:
        units_all += load(f)
    st = stats(units_all)[0]
    print(json.dumps(st, ensure_ascii=False))
    for p in problems(st):
        print("PROBLEM:", p)
        bad += 1
    sys.exit(1 if bad else 0)
