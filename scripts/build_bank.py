#!/usr/bin/env python3
"""Merge reviewed staging batches into data/bank.<lang>.json (units sorted by grade, then id)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = set(sys.argv[1:])  # unit ids rejected by the pipeline

for lang in ("kk", "ru"):
    units = []
    for f in sorted((ROOT / "data/staging").glob(f"{lang}_*.json")):
        units += json.loads(f.read_text(encoding="utf-8"))["units"]
    units = [u for u in units if u["id"] not in EXCLUDE]
    units.sort(key=lambda u: (u["grade"], u["id"]))
    out = {"version": 1, "lang": lang, "units": units}
    (ROOT / f"data/bank.{lang}.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"bank.{lang}: {len(units)} units")
