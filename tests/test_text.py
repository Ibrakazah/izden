#!/usr/bin/env python3
"""Sentence splitting must be identical in js/text.js (app) and scripts/check.py (validator),
otherwise evidence refs like b3:s2 would point to different sentences. Runs JS via macOS osascript."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from check import sentences  # noqa: E402


def paragraphs():
    out = []
    for lang in ("kk", "ru"):
        for u in json.loads((ROOT / f"data/bank.{lang}.json").read_text(encoding="utf-8"))["units"]:
            out += [b["text"] for b in u["blocks"] if b["type"] == "p"]
    return out


def test_split_matches_js():
    paras = paragraphs()
    py = [sentences(p) for p in paras]
    if not shutil.which("osascript"):
        print("osascript not found: JS side skipped")
        return
    js_src = (ROOT / "js/text.js").read_text(encoding="utf-8")
    js_src = re.sub(r"^export\s+", "", js_src, flags=re.M)
    src = js_src + f"\nvar P = {json.dumps(paras, ensure_ascii=False)};\nJSON.stringify(P.map(splitSentences));\n"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(src)
    out = subprocess.run(["osascript", "-l", "JavaScript", f.name], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    js = json.loads(out.stdout)
    bad = [i for i, (a, b) in enumerate(zip(py, js)) if a != b]
    assert not bad, f"{len(bad)} paragraphs split differently, first: {paras[bad[0]][:120]}"
    print(f"OK: {len(paras)} paragraphs, {sum(map(len, py))} sentences split identically in JS and Python")


if __name__ == "__main__":
    test_split_matches_js()
