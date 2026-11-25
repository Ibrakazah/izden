#!/usr/bin/env python3
"""Short code (16 symbols, Luhn mod 32) and IZ1 payload round-trip, run through js/qr.js in macOS JavaScriptCore.
Checks: round trip, every single-symbol typo rejected, adjacent swaps rejected (>=95%), all-zero code rejected."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HARNESS = r"""
var SKILLS = ['locate','understand','evaluate'];
var TRAPS = ['word_match','near_detail','outside_knowledge','overgeneralize','opposite','misread_table'];
var DIAGNOSES = ['understood','guessed','found_wrong','not_found'];
var st = {skills:{locate:{p:0.62,n:9,c:6},understand:{p:0.48,n:7,c:3},evaluate:{p:0.31,n:6,c:2}},
          traps:{word_match:1,near_detail:4,outside_knowledge:0,overgeneralize:1,opposite:2,misread_table:3},
          diag:{understood:9,guessed:3,found_wrong:2,not_found:4}, exposure:{word_match:10,near_detail:14,outside_knowledge:9,overgeneralize:6,opposite:8,misread_table:11}, done:{a:1,b:1}};
var prof = {name:'Айгерім', grade:8, lang:'kk'};
var code = encodeShortCode(prof, st);
var back = decodeShortCode(code, 'Айгерім');
var raw = code.replace(/-/g,'');
var B = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
var typos = 0, typosCaught = 0, swaps = 0, swapsCaught = 0;
for (var i = 0; i < raw.length; i++) for (var k = 0; k < 32; k++) {
  if (B[k] === raw[i]) continue;
  typos++; if (!decodeShortCode(raw.slice(0,i) + B[k] + raw.slice(i+1), 'x')) typosCaught++;
}
for (var i = 0; i + 1 < raw.length; i++) {
  if (raw[i] === raw[i+1]) continue;
  swaps++; if (!decodeShortCode(raw.slice(0,i) + raw[i+1] + raw[i] + raw.slice(i+2), 'x')) swapsCaught++;
}
var payload = encodePayload(prof, st, new Date(2026, 10, 26));
JSON.stringify({code: code, back: back, typos: typos, typosCaught: typosCaught, swaps: swaps, swapsCaught: swapsCaught,
  zero: decodeShortCode('0000-0000-0000-0000', 'x'), payload: payload, payloadBytes: unescape(encodeURIComponent(payload)).length,
  payloadBack: decodePayload(payload), tampered: decodePayload(payload.replace('|8|', '|9|'))});
"""


def test_short_code_and_payload():
    if not shutil.which("osascript"):
        raise SystemExit("FAILED: osascript (macOS JavaScriptCore) not found - the JS side was NOT verified")
    src = (ROOT / "js/qr.js").read_text(encoding="utf-8")
    src = re.sub(r"^import .*$", "", src, flags=re.M)
    src = re.sub(r"^export\s+", "", src, flags=re.M)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(src + HARNESS)
    out = subprocess.run(["osascript", "-l", "JavaScript", f.name], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    b = r["back"]
    assert b and b["p"] == [62, 48, 31] and b["grade"] == 8 and b["traps"] == [1, 4, 0, 1, 2, 3] and b["diag"][1] == 3
    assert r["typosCaught"] == r["typos"], f"single-symbol typos accepted: {r['typos'] - r['typosCaught']}"
    assert r["swapsCaught"] >= 0.95 * r["swaps"], f"adjacent swaps caught {r['swapsCaught']}/{r['swaps']}"
    assert r["zero"] is None, "all-zero code must be rejected"
    assert r["payloadBytes"] <= 300 and r["payloadBack"]["name"].startswith("А.#") and "Айгерім" not in r["payload"] and r["tampered"] is None
    assert r["payloadBack"]["exposure"] == [10, 14, 9, 6, 8, 11]
    print(f"OK: short code {r['code']}; typos caught {r['typosCaught']}/{r['typos']}, adjacent swaps "
          f"{r['swapsCaught']}/{r['swaps']}; zero code rejected; IZ1 payload {r['payloadBytes']} bytes, checksum works")


if __name__ == "__main__":
    test_short_code_and_payload()
