"""Write the morning test results into team.json and rebuild the deck and the defense notes.

  python3 tools/pilot_fill.py --n 5 --understood 4 --guessed-pct 24 --qr 5 --date "29.11" --quote "..." --role "ученица 8 класса"

--understood  how many of N found the "tap the evidence first" step without help
--guessed-pct the big number from the teacher screen ("N% of correct answers without evidence")
--qr          how many QR codes were read on the first try (optional)
Values are stored as shares (0..1); slides and DEFENSE.md show them as percentages.
"""
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
a = argparse.ArgumentParser()
a.add_argument('--n', type=int, required=True)
a.add_argument('--understood', type=int)
a.add_argument('--guessed-pct', type=float)
a.add_argument('--qr', type=int)
a.add_argument('--date', default='')
a.add_argument('--grades', default='')
a.add_argument('--quote', default='')
a.add_argument('--role', default='')
x = a.parse_args()
if x.n <= 0 or (x.understood is not None and not 0 <= x.understood <= x.n) or (x.qr is not None and not 0 <= x.qr <= x.n):
    sys.exit('check the numbers: 0 <= understood, qr <= n')
p = ROOT / 'team.json'
d = json.loads(p.read_text(encoding='utf-8'))
d['pilot'] = {
    'n': x.n, 'date': x.date, 'grades': x.grades,
    'guessed_share': round(x.guessed_pct / 100, 3) if x.guessed_pct is not None else None,
    'understood_mechanic_share': round(x.understood / x.n, 3) if x.understood is not None else None,
    'qr_first_try_share': round(x.qr / x.n, 3) if x.qr is not None else None,
    'teacher_quote': x.quote, 'teacher_role': x.role,
}
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
print('team.json pilot =', d['pilot'])
for cmd in (['python3', 'tools/render_docs.py'], ['python3', 'tools/build_slides.py']):
    subprocess.run(cmd, cwd=ROOT, check=True)
print('done: slides.pdf and DEFENSE.md updated')
