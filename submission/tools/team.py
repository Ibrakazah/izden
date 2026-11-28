"""Team data for all submission materials (single source: submission/team.json).

Template syntax used in tools/*.src.md, tools/slides_src.html and video segment texts:
  {{t:path}}                      value (dot path; members_line, pilot.guessed_pct ... are derived)
  [[if path]] ... [[/if]]         shown only when the value is filled
  [[if path]] ... [[else]] ... [[/if]]        (may be nested)
Empty = "", null, [] or missing. render() refuses to leave any {…} placeholder or [[…]] tag behind.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    d = json.loads((ROOT / "team.json").read_text(encoding="utf-8"))
    m = [x for x in d.get("members") or [] if x.get("name")]
    d["members_line"] = "; ".join(f"{x['name']} — {x['role']}" if x.get("role") else x["name"] for x in m)
    d["members_names"] = ", ".join(x["name"] for x in m)
    import html as _h
    d["members_cards"] = "".join(f'<div class="card" style="flex:1 1 40%;padding:34px 38px"><h3 style="font-size:46px;margin-bottom:8px">{_h.escape(x["name"])}</h3><p style="margin:0;font-size:32px">{_h.escape(x.get("role") or "")}</p></div>' for x in m)
    p = d.get("pilot") or {}
    for k in ("guessed_share", "understood_mechanic_share", "qr_first_try_share"):
        v = p.get(k)
        p[k.replace("_share", "_pct")] = (f"{round(v * 100) if v <= 1 else round(v)}%" if isinstance(v, (int, float)) else None)
    g = p.get("guessed_share")
    p["guessed_num"] = (str(round(g * 100) if g <= 1 else round(g)) if isinstance(g, (int, float)) else None)
    d["pilot"] = p
    return d


def get(d, path):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def filled(v):
    return v not in (None, "", [], {})


# innermost blocks first (bodies without another [[if), so nesting works
_NO_IF = r"(?:(?!\[\[if ).)*?"
IF_RE = re.compile(r"\[\[if ([\w.]+)\]\](" + _NO_IF + r")(?:\[\[else\]\](" + _NO_IF + r"))?\[\[/if\]\]", re.S)
VAL_RE = re.compile(r"\{\{t:([\w.]+)\}\}")


def render(text, d=None):
    d = d or load()
    prev = None
    while prev != text:  # resolve innermost blocks until nothing changes
        prev = text
        text = IF_RE.sub(lambda m: m.group(2) if filled(get(d, m.group(1))) else (m.group(3) or ""), text)
    text = VAL_RE.sub(lambda m: str(get(d, m.group(1)) or ""), text)
    left = re.findall(r"(?<!\{)\{[А-ЯЁA-Z][^{}]*\}(?!\})|\[\[[^\]]*\]\]", text)  # {{IMG:..}} is not a placeholder
    assert not left, f"unfilled placeholders left: {left[:5]}"
    return text
