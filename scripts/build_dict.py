#!/usr/bin/env python3
"""Offline word dictionary for tap-to-translate.

  python3 scripts/build_dict.py todo     # list word forms from all banks that are not yet translated -> data/staging_dict/todo_<lang>_<N>.txt
  python3 scripts/build_dict.py build    # merge data/staging_dict/done_*.json into data/dict.<lang>.json {form: [lemma, translation]}
Word forms are lower-cased, ё -> е, the same tokenisation as js/dict.js (letters, marks and inner hyphens)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / "data/staging_dict"
TOK = re.compile(r"[^\W\d_](?:[^\W\d_]|-(?=[^\W\d_]))*", re.U)
CHUNK = 450


def norm(w):
    return w.lower().replace("ё", "е").strip("-")


def texts(u):
    out = [u["title"]]
    for b in u["blocks"]:
        if b["type"] in ("h", "p"):
            out.append(b["text"])
        elif b["type"] == "list":
            out += b["items"]
        elif b["type"] in ("table", "chart"):
            out.append(b.get("caption", "") + " " + b.get("unit", ""))
            out += [str(c) for r in b["rows"] for c in r]
    for q in u["questions"]:
        out.append(q["stem"])
        out += [o["text"] for o in q["options"]]
    return out


def forms(lang):
    f = set()
    for name in ("bank", "math"):
        p = ROOT / f"data/{name}.{lang}.json"
        if p.exists():
            for u in json.loads(p.read_text(encoding="utf-8"))["units"]:
                for t in texts(u):
                    f |= {norm(m.group(0)) for m in TOK.finditer(t) if len(m.group(0)) >= 2}
    return sorted(f)


def done(lang):
    d = {}
    for p in sorted(SD.glob(f"done_{lang}_*.json")):
        try:
            for k, v in json.loads(p.read_text(encoding="utf-8")).items():
                if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, str) and x.strip() for x in v[:2]):
                    d[norm(k)] = [v[0].strip(), v[1].strip()]
        except Exception as e:  # noqa: BLE001
            print("bad", p.name, e)
    return d


def todo():
    SD.mkdir(parents=True, exist_ok=True)
    for lang in ("ru", "kk"):
        have = done(lang)
        left = [w for w in forms(lang) if w not in have]
        n0 = len(list(SD.glob(f"todo_{lang}_*.txt")))
        for i in range(0, len(left), CHUNK):
            (SD / f"todo_{lang}_{n0 + i // CHUNK + 1:02d}.txt").write_text("\n".join(left[i:i + CHUNK]) + "\n", encoding="utf-8")
        print(lang, "forms", len(forms(lang)), "translated", len(have), "todo", len(left))


def build():
    for lang in ("ru", "kk"):
        have = done(lang)
        need = forms(lang)
        d = {w: have[w] for w in need if w in have}
        (ROOT / f"data/dict.{lang}.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"dict.{lang}: {len(d)}/{len(need)} forms covered")


if __name__ == "__main__":
    {"todo": todo, "build": build}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print(__doc__))()
