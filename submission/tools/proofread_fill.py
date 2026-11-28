"""Record the native-speaker proofreading of the demo texts and rebuild the deck and the defense notes.

  python3 tools/proofread_fill.py --by "Имя" --texts 4 --notes "12 правок: окончания, 2 кальки"
"""
import argparse, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
a = argparse.ArgumentParser()
a.add_argument('--by', required=True)
a.add_argument('--texts', type=int, required=True)
a.add_argument('--notes', default='')
x = a.parse_args()
p = ROOT / 'team.json'
d = json.loads(p.read_text(encoding='utf-8'))
d['kk_proofread'] = {'by': x.by, 'texts': x.texts, 'notes': x.notes}
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
print('team.json kk_proofread =', d['kk_proofread'])
for cmd in (['python3', 'tools/render_docs.py'], ['python3', 'tools/build_slides.py']):
    subprocess.run(cmd, cwd=ROOT, check=True)
print('done: slides.pdf and DEFENSE.md updated; corrections from PROOFREAD_KK.md still have to be applied to data/bank.kk.json and data/math.kk.json')
