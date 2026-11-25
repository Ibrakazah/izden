"""Render DEFENSE.md and DESCRIPTION.md from tools/*.src.md + team.json (empty fields -> blocks disappear)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import team  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
d = team.load()
for name in ("DEFENSE", "DESCRIPTION"):
    out = team.render((ROOT / "tools" / f"{name}.src.md").read_text(encoding="utf-8"), d)
    (ROOT / f"{name}.md").write_text(out, encoding="utf-8")
    print(f"{name}.md", len(out), "chars")
