#!/usr/bin/env python3
"""Project checks for Izden.

Usage:
  python3 scripts/check.py                 # full check: banks, sw.js cache list, no external URLs
  python3 scripts/check.py FILE.json ...   # validate only the given bank/staging files
  python3 scripts/check.py --show FILE.json  # print units with numbered sentences/rows (for reviewers)
  python3 scripts/check.py --stamp           # set CACHE in sw.js to a hash of all cached files (run before deploy)

Sentence rule (shared with js/text.js): a paragraph is split into sentences by
the regex (?<=[.!?…])\\s+ ; sentences are numbered from 1 (b3:s1).
Table rows: rows[0] is the header, data rows are numbered from 1 (b2:r1 == rows[1]).
Chart rows: numbered from 1 (b4:r1 == rows[0]). List items: from 1 (b5:i1 == items[0]).
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SENT_RE = re.compile(r"(?<=[.!?…])\s+")

FORMATS = {"table", "continuous", "notice", "chart", "mixed"}
CONTEXTS = {"rural", "urban", "everyday"}
PROCESSES = {"locate", "understand", "evaluate"}
TRAPS = {"word_match", "near_detail", "outside_knowledge", "overgeneralize", "opposite", "misread_table"}
BLOCK_TYPES = {"h", "p", "list", "table", "chart"}
NON_CONTINUOUS = {"table", "notice", "chart", "mixed"}


def sentences(text):
    return [s for s in SENT_RE.split(text.strip()) if s]


def evidence_targets(block):
    """Return dict of valid evidence suffixes for a block."""
    t = block.get("type")
    if t == "p":
        return {f"s{i}" for i in range(1, len(sentences(block.get("text", ""))) + 1)}
    if t == "list":
        return {f"i{i}" for i in range(1, len(block.get("items", [])) + 1)}
    if t == "table":
        return {f"r{i}" for i in range(1, len(block.get("rows", [])))}
    if t == "chart":
        return {f"r{i}" for i in range(1, len(block.get("rows", [])) + 1)}
    return set()


def nonempty_str(x):
    return isinstance(x, str) and x.strip() != ""


def validate_unit(u, errs, expect_lang=None):
    uid = u.get("id", "?")
    e = lambda m: errs.append(f"{uid}: {m}")
    for k in ("id", "grade", "title", "format", "context", "blocks", "questions"):
        if k not in u:
            e(f"missing field '{k}'")
    if errs and any(x.startswith(f"{uid}: missing") for x in errs):
        return
    if expect_lang and not uid.startswith(expect_lang + "-"):
        e(f"id must start with '{expect_lang}-'")
    if u["grade"] not in (7, 8, 9):
        e("grade must be 7, 8 or 9")
    if not nonempty_str(u["title"]):
        e("empty title")
    if u["format"] not in FORMATS:
        e(f"bad format {u['format']!r}")
    if u["context"] not in CONTEXTS:
        e(f"bad context {u['context']!r}")
    blocks = u["blocks"]
    if not isinstance(blocks, list) or not blocks:
        e("blocks must be a non-empty list")
        return
    bmap = {}
    for b in blocks:
        bid = b.get("id")
        if not nonempty_str(bid) or not re.fullmatch(r"b\d+", bid):
            e(f"bad block id {bid!r}")
            continue
        if bid in bmap:
            e(f"duplicate block id {bid}")
        bmap[bid] = b
        t = b.get("type")
        if t not in BLOCK_TYPES:
            e(f"{bid}: bad block type {t!r}")
        elif t in ("h", "p"):
            if not nonempty_str(b.get("text")):
                e(f"{bid}: empty text")
        elif t == "list":
            items = b.get("items")
            if not isinstance(items, list) or not items or not all(nonempty_str(i) for i in items):
                e(f"{bid}: list needs non-empty items")
        elif t == "table":
            rows = b.get("rows")
            if not isinstance(rows, list) or len(rows) < 2:
                e(f"{bid}: table needs header + >=1 row")
            else:
                w = len(rows[0])
                for i, r in enumerate(rows):
                    if not isinstance(r, list) or len(r) != w:
                        e(f"{bid}: row {i} has {len(r) if isinstance(r, list) else '?'} cells, header has {w}")
                    elif not all(isinstance(c, (str, int, float)) for c in r):
                        e(f"{bid}: row {i} has non-scalar cell")
        elif t == "chart":
            rows = b.get("rows")
            if not nonempty_str(b.get("caption", "")):
                e(f"{bid}: chart needs caption")
            if not isinstance(rows, list) or len(rows) < 2:
                e(f"{bid}: chart needs >=2 rows")
            else:
                for r in rows:
                    if not (isinstance(r, list) and len(r) == 2 and nonempty_str(str(r[0]))
                            and isinstance(r[1], (int, float)) and not isinstance(r[1], bool)):
                        e(f"{bid}: chart row must be [label, number], got {r!r}")
    qs = u["questions"]
    if not isinstance(qs, list) or not (3 <= len(qs) <= 5):
        e("needs 3-5 questions")
        return
    qids = set()
    for q in qs:
        qid = q.get("id", "?")
        qe = lambda m: e(f"{qid}: {m}")
        for k in ("id", "process", "difficulty", "stem", "options", "evidence", "hint_steps", "explain"):
            if k not in q:
                qe(f"missing field '{k}'")
        if qid in qids:
            qe("duplicate question id")
        qids.add(qid)
        if q.get("process") not in PROCESSES:
            qe(f"bad process {q.get('process')!r}")
        if q.get("difficulty") not in (1, 2, 3):
            qe("difficulty must be 1, 2 or 3")
        if not nonempty_str(q.get("stem")):
            qe("empty stem")
        if not nonempty_str(q.get("explain")):
            qe("empty explain")
        hs = q.get("hint_steps")
        if not isinstance(hs, list) or not (2 <= len(hs) <= 3) or not all(nonempty_str(h) for h in hs):
            qe("hint_steps must be 2-3 non-empty strings")
        opts = q.get("options")
        if not isinstance(opts, list) or not (3 <= len(opts) <= 4):
            qe("needs 3-4 options")
        else:
            ncorrect = 0
            oids = set()
            texts = set()
            for o in opts:
                oid = o.get("id")
                if oid in oids:
                    qe(f"duplicate option id {oid}")
                oids.add(oid)
                if not nonempty_str(o.get("text")):
                    qe(f"option {oid}: empty text")
                elif o["text"].strip().lower() in texts:
                    qe(f"option {oid}: duplicate text")
                else:
                    texts.add(o["text"].strip().lower())
                if o.get("correct") is True:
                    ncorrect += 1
                    if "trap" in o:
                        qe(f"option {oid}: correct option must not have trap")
                elif o.get("correct") is False:
                    if o.get("trap") not in TRAPS:
                        qe(f"option {oid}: bad/missing trap {o.get('trap')!r}")
                    if not nonempty_str(o.get("why")):
                        qe(f"option {oid}: missing why")
                else:
                    qe(f"option {oid}: 'correct' must be true/false")
            if ncorrect != 1:
                qe(f"must have exactly one correct option, has {ncorrect}")
        ev = q.get("evidence")
        if not isinstance(ev, list) or not ev:
            qe("evidence must be a non-empty list")
        else:
            for ref in ev:
                m = re.fullmatch(r"(b\d+)(?::([sri]\d+))?", str(ref))
                if not m:
                    qe(f"bad evidence ref {ref!r}")
                    continue
                bid, part = m.group(1), m.group(2)
                if bid not in bmap:
                    qe(f"evidence {ref}: no block {bid}")
                elif part and part not in evidence_targets(bmap[bid]):
                    qe(f"evidence {ref}: {part} not in block {bid} (type {bmap[bid].get('type')}, "
                       f"valid: {sorted(evidence_targets(bmap[bid]), key=lambda s: int(s[1:]))})")


def load_units(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, None
    return data.get("units", []), data


def validate_file(path, expect_lang=None):
    errs = []
    try:
        units, data = load_units(path)
    except Exception as ex:  # noqa: BLE001
        return [f"{path}: cannot parse JSON: {ex}"], []
    if data is not None and expect_lang:
        if data.get("lang") != expect_lang:
            errs.append(f"{path}: lang must be {expect_lang!r}")
        if data.get("version") != 1:
            errs.append(f"{path}: version must be 1")
    seen = set()
    for u in units:
        if u.get("id") in seen:
            errs.append(f"duplicate unit id {u.get('id')}")
        seen.add(u.get("id"))
        validate_unit(u, errs, expect_lang)
    return errs, units


def stats(units):
    q = [x for u in units for x in u["questions"]]
    fmt = Counter(u["format"] for u in units)
    ctx = Counter(u["context"] for u in units)
    grade = Counter(u["grade"] for u in units)
    proc = Counter(x["process"] for x in q)
    diff = Counter(x["difficulty"] for x in q)
    traps = Counter(o["trap"] for x in q for o in x["options"] if not o["correct"])
    nc = sum(v for k, v in fmt.items() if k in NON_CONTINUOUS)
    return {
        "units": len(units), "questions": len(q),
        "non_continuous_share": round(nc / max(1, len(units)), 3),
        "rural_share": round(ctx.get("rural", 0) / max(1, len(units)), 3),
        "format": dict(fmt), "context": dict(ctx), "grade": dict(sorted(grade.items())),
        "process": dict(proc), "difficulty": dict(sorted(diff.items())), "traps": dict(traps),
    }


def show(path):
    units, _ = load_units(path)
    for u in units:
        print(f"=== {u['id']} | grade {u['grade']} | {u['format']} | {u['context']} | {u['title']}")
        for b in u["blocks"]:
            t = b["type"]
            if t == "h":
                print(f"[{b['id']}] # {b['text']}")
            elif t == "p":
                for i, s in enumerate(sentences(b["text"]), 1):
                    print(f"[{b['id']}:s{i}] {s}")
            elif t == "list":
                for i, s in enumerate(b["items"], 1):
                    print(f"[{b['id']}:i{i}] - {s}")
            elif t == "table":
                if b.get("caption"):
                    print(f"[{b['id']}] table: {b['caption']}")
                print(f"[{b['id']}:header] " + " | ".join(map(str, b["rows"][0])))
                for i, r in enumerate(b["rows"][1:], 1):
                    print(f"[{b['id']}:r{i}] " + " | ".join(map(str, r)))
            elif t == "chart":
                print(f"[{b['id']}] chart: {b['caption']} ({b.get('unit', '')})")
                for i, r in enumerate(b["rows"], 1):
                    print(f"[{b['id']}:r{i}] {r[0]}: {r[1]}")
        print()


EXTERNAL_RE = re.compile(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//|@import\s+url\(\s*["']?(?:https?:)?//|"""
                         r"""import\s+[^;]*?from\s+["']https?://|fetch\(\s*["']https?://|url\(\s*["']?https?://""",
                         re.I)


def check_external():
    errs = []
    for p in list(ROOT.glob("*.html")) + list(ROOT.glob("js/*.js")) + list(ROOT.glob("css/*.css")) + [ROOT / "sw.js"]:
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8")
        for m in EXTERNAL_RE.finditer(txt):
            line = txt.count("\n", 0, m.start()) + 1
            errs.append(f"{p.relative_to(ROOT)}:{line}: external URL reference: {m.group(0)!r}")
    return errs


def sw_assets(txt):
    m = re.search(r"const\s+ASSETS\s*=\s*\[(.*?)\];", txt, re.S)
    return re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)) if m else None


def assets_hash(assets):
    h = hashlib.sha256()
    for a in sorted(a.lstrip("./") for a in assets):
        if a and (ROOT / a).is_file():
            h.update(a.encode())
            h.update((ROOT / a).read_bytes())
    return h.hexdigest()[:10]


def stamp_sw():
    sw = ROOT / "sw.js"
    txt = sw.read_text(encoding="utf-8")
    cache = f"izden-{assets_hash(sw_assets(txt))}"
    txt = re.sub(r"const\s+CACHE\s*=\s*['\"][^'\"]*['\"]", f"const CACHE = '{cache}'", txt, count=1)
    sw.write_text(txt, encoding="utf-8")
    print(f"sw.js CACHE = {cache}")


def check_sw():
    errs = []
    sw = ROOT / "sw.js"
    if not sw.exists():
        return ["sw.js missing"]
    txt = sw.read_text(encoding="utf-8")
    m = re.search(r"const\s+ASSETS\s*=\s*\[(.*?)\];", txt, re.S)
    if not m:
        return ["sw.js: cannot find `const ASSETS = [...]`"]
    assets = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
    cm = re.search(r"const\s+CACHE\s*=\s*['\"]([^'\"]*)['\"]", txt)
    want = f"izden-{assets_hash(assets)}"
    if not cm or cm.group(1) != want:
        errs.append(f"sw.js: CACHE is {cm.group(1) if cm else None!r} but cached files hash to {want!r} - "
                    f"run `python3 scripts/check.py --stamp` so phones fetch the new version")
    for a in assets:
        rel = a.lstrip("./")
        if rel in ("", "/"):
            continue
        if not (ROOT / rel).exists():
            errs.append(f"sw.js ASSETS: missing file {a}")
    # every local js module / css / data referenced by the app should be cached
    must = [p for p in ROOT.glob("js/*.js")] + list(ROOT.glob("css/*.css")) + list(ROOT.glob("vendor/*.js")) \
        + [ROOT / "data/bank.kk.json", ROOT / "data/bank.ru.json", ROOT / "data/bkt_params.json", ROOT / "data/passport.json", ROOT / "data/trap_cards.json", ROOT / "index.html",
           ROOT / "manifest.webmanifest"]
    norm = {a.lstrip("./") for a in assets}
    for p in must:
        rel = str(p.relative_to(ROOT))
        if p.exists() and rel not in norm:
            errs.append(f"sw.js ASSETS: {rel} exists but is not cached")
    return errs


def main(argv):
    if argv and argv[0] == "--stamp":
        stamp_sw()
        return 0
    if argv and argv[0] == "--show":
        for f in argv[1:]:
            show(f)
        return 0
    if argv:
        bad = 0
        for f in argv:
            errs, units = validate_file(f)
            for x in errs:
                print("ERR", x)
            print(f"{f}: {len(units)} units, {len(errs)} errors")
            if units and not errs:
                print(json.dumps(stats(units), ensure_ascii=False))
            bad += len(errs)
        return 1 if bad else 0

    all_errs = []
    for lang in ("kk", "ru"):
        p = ROOT / f"data/bank.{lang}.json"
        if not p.exists():
            all_errs.append(f"{p.relative_to(ROOT)} missing")
            continue
        errs, units = validate_file(p, lang)
        all_errs += errs
        if not errs:
            s = stats(units)
            print(f"bank.{lang}: {s['units']} units, {s['questions']} questions, "
                  f"non-continuous {s['non_continuous_share']:.0%}, rural {s['rural_share']:.0%}, process {s['process']}")
            if s["units"] < 12:
                all_errs.append(f"bank.{lang}: needs >=12 units, has {s['units']}")
            if s["non_continuous_share"] < 0.4:
                all_errs.append(f"bank.{lang}: non-continuous share < 40%")
            if s["rural_share"] < 0.5:
                all_errs.append(f"bank.{lang}: rural share < 50%")
            # answer-shape cues: warn (not fail) above thresholds
            from option_stats import stats as ostats
            o = ostats(units)[0]
            pos = o["displayed_positions"]
            print(f"bank.{lang}: correct option is the longest in {o['correct_longest']}/{o['questions']} "
                  f"({o['correct_longest_share']:.0%}), displayed positions A-D {pos}")
            if o["correct_longest_share"] > 0.30:
                print(f"WARN bank.{lang}: correct option is the longest in more than 30% of questions")
            if max(pos) > 0.40 * o["questions"]:
                print(f"WARN bank.{lang}: one answer position holds more than 40% of correct answers")
    params = ROOT / "data/bkt_params.json"
    if params.exists():
        json.loads(params.read_text(encoding="utf-8"))
    all_errs += check_sw()
    all_errs += check_external()
    for x in all_errs:
        print("ERR", x)
    print("OK" if not all_errs else f"FAILED: {len(all_errs)} problem(s)")
    return 1 if all_errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
