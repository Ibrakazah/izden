#!/usr/bin/env python3
"""Calibrate question difficulty and BKT parameters from AI-student runs.

Input : evals/ai_students/raw/<lang>_<persona>.json (personas: weak, below, average, strong; see personas.md)
Output: evals/ai_students/calibration.json  (per-question stats; merged into banks by scripts/build_bank.py)
        data/bkt_params.json                (slip/guess/evidence parameters, estimated + clamped)
        evals/ai_students_report.md

Method (simple and transparent, 4 personas x 2 languages):
- p_ai(question) = share of personas answering correctly; cal_difficulty = 1 if all 4 correct,
  2 if 3 of 4, 3 if 2 or fewer.
- guess[d] = accuracy of the `weak` persona on author-difficulty d   (proxy for "does not know the skill");
  slip[d]  = 1 - accuracy of `average`+`strong` on difficulty d       (proxy for "knows the skill").
  Both are shrunk toward the hand-set prior with 8 pseudo-observations and clamped to sane ranges.
- evidence_guess = share of right evidence taps by `weak`; evidence_miss = share of wrong taps by `average`+`strong`.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from pipeline import letter_to_id  # noqa: E402
RAW = ROOT / "evals/ai_students/raw"
PERSONAS = ["weak", "below", "average", "strong"]
PRIOR = {"slip": [0.05, 0.1, 0.15], "guess": [0.3, 0.22, 0.15], "evidence_miss": 0.1, "evidence_guess": 0.35}
K = 8  # pseudo-observations for shrinkage


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def shrink(successes, n, prior):
    return (successes + K * prior) / (n + K)


def ev_ok(tap, refs):
    tap = str(tap or "")
    for e in refs:
        if tap == e:
            return True
        if ":" not in e and tap.split(":")[0] == e:  # block-level evidence: any part of the block
            return True
    return False


def main():
    per_q = {}
    by_d = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # by_d[group][d] = [correct, n]
    ev = defaultdict(lambda: [0, 0])  # ev[group] = [right taps, n]
    trap_offered, trap_picked = Counter(), Counter()
    persona_acc = {}
    for lang in ("kk", "ru"):
        units = json.loads((ROOT / f"data/bank.{lang}.json").read_text(encoding="utf-8"))["units"]
        qmap = {(u["id"], q["id"]): q for u in units for q in u["questions"]}
        answers = {}
        for p in PERSONAS:
            f = RAW / f"{lang}_{p}.json"
            answers[p] = {}
            for a in json.loads(f.read_text(encoding="utf-8"))["answers"]:
                q = qmap.get((a["unit"], a["q"]))
                if q is None:
                    continue
                a = dict(a, answer=letter_to_id(a["unit"], q, a.get("answer")))  # shuffled A-D -> option id
                answers[p][(a["unit"], a["q"])] = a
        for p in PERSONAS:
            ok = sum(1 for k, q in qmap.items() if k in answers[p] and
                     answers[p][k]["answer"] == next(o["id"] for o in q["options"] if o["correct"]))
            evr = sum(1 for k, q in qmap.items() if k in answers[p] and ev_ok(answers[p][k].get("evidence"), q["evidence"]))
            persona_acc[f"{lang}_{p}"] = {"acc": ok / len(qmap), "evidence": evr / len(qmap), "n": len(qmap)}
        for k, q in qmap.items():
            corr = next(o["id"] for o in q["options"] if o["correct"])
            picks = Counter()
            n_ok = 0
            for p in PERSONAS:
                a = answers[p].get(k)
                if not a:
                    continue
                right = a["answer"] == corr
                n_ok += right
                if not right:
                    picks[a["answer"]] += 1
                grp = "weak" if p == "weak" else ("know" if p in ("average", "strong") else None)
                if grp:
                    by_d[grp][q["difficulty"]][0] += right
                    by_d[grp][q["difficulty"]][1] += 1
                    ev[grp][0] += ev_ok(a.get("evidence"), q["evidence"])
                    ev[grp][1] += 1
            for o in q["options"]:
                if not o["correct"]:
                    trap_offered[o["trap"]] += len(PERSONAS)
                    trap_picked[o["trap"]] += picks.get(o["id"], 0)
            p_ai = n_ok / len(PERSONAS)
            cal = 1 if n_ok == 4 else (2 if n_ok == 3 else 3)
            per_q[f"{k[0]}/{k[1]}"] = {"p_ai": p_ai, "cal_difficulty": cal, "author_difficulty": q["difficulty"],
                                       "wrong_picks": dict(picks)}
    params = json.loads((ROOT / "data/bkt_params.json").read_text(encoding="utf-8"))
    guess, slip = [], []
    for d in (1, 2, 3):
        c, n = by_d["weak"][d]
        guess.append(round(clamp(shrink(c, n, PRIOR["guess"][d - 1]), 0.1, 0.45), 3))
        c, n = by_d["know"][d]
        slip.append(round(clamp(shrink(n - c, n, PRIOR["slip"][d - 1]), 0.03, 0.2), 3))
    eg = round(clamp(shrink(ev["weak"][0], ev["weak"][1], PRIOR["evidence_guess"]), 0.15, 0.7), 3)
    # Floor 0.15: real pupils mis-tap neighbouring sentences far more often than AI personas, and a right
    # answer with wrong evidence must stay weak positive evidence ("guessed - prove it"), not a penalty.
    em = round(clamp(shrink(ev["know"][1] - ev["know"][0], ev["know"][1], PRIOR["evidence_miss"]), 0.15, 0.3), 3)
    params.update({"slip_by_difficulty": slip, "guess_by_difficulty": guess, "evidence_guess": eg, "evidence_miss": em,
                   "calibrated_from": "evals/ai_students (4 AI-student personas x 2 languages); see evals/ai_students_report.md"})
    params["comment"] = ("BKT parameters shared by js/engine.js and evals/engine.py. slip/guess/evidence estimated from "
                         "AI-student runs with shrinkage to hand-set priors; p_init/p_learn are priors (no real data yet).")
    (ROOT / "data/bkt_params.json").write_text(json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out = {"per_question": per_q, "persona_accuracy": persona_acc,
           "trap_attractiveness": {t: {"picked": trap_picked[t], "offered": trap_offered[t]} for t in trap_offered},
           "by_difficulty": {g: {d: v for d, v in m.items()} for g, m in by_d.items()},
           "evidence": dict(ev), "params": {k: params[k] for k in ("slip_by_difficulty", "guess_by_difficulty",
                                                                    "evidence_guess", "evidence_miss")}}
    (ROOT / "evals/ai_students/calibration.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    report(out)
    print(json.dumps(out["params"]), json.dumps(persona_acc))


def report(out):
    pq = out["per_question"]
    L = ["# ИИ-ученики: калибровка сложности, ловушек и параметров BKT\n",
         "> Это **имитация** учеников ИИ-агентами, а не данные реальных детей. Она нужна, чтобы стартовые сложности "
         "и параметры модели были оценены по поведению, а не заданы с потолка. После пилота (docs/PILOT.md) "
         "параметры пересчитываются по реальным ответам тем же скриптом.\n",
         "Метод: 4 персоны (`evals/ai_students/personas.md`) — слабый, ниже среднего, средний, сильный читатель — "
         "решают **все** вопросы банка вслепую (без ключей), сначала отмечая место-доказательство, потом вариант. "
         "Слабых играет Claude Haiku, средних и сильных — Claude Sonnet. "
         "Скрипт: `python3 evals/ai_students/calibrate.py`.\n",
         "## Точность персон\n", "| Персона | kk: верно | kk: доказательство | ru: верно | ru: доказательство |",
         "|---|---|---|---|---|"]
    pa = out["persona_accuracy"]
    for p in PERSONAS:
        L.append(f"| {p} | {pa[f'kk_{p}']['acc']:.0%} | {pa[f'kk_{p}']['evidence']:.0%} | "
                 f"{pa[f'ru_{p}']['acc']:.0%} | {pa[f'ru_{p}']['evidence']:.0%} |")
    L.append("\nУровни различаются, как и задумано: точность растёт от слабой персоны к сильной. "
             "Оговорка: слабая персона на казахском — это ещё и более слабая модель на казахском языке, "
             "поэтому часть её ошибок может быть ошибками модели, а не «читательскими».\n")
    L.append("## Сложность: оценка автора против ИИ-учеников\n")
    L.append("| Сложность автора | Вопросов | Средняя доля верных у ИИ-учеников |")
    L.append("|---|---|---|")
    for d in (1, 2, 3):
        xs = [v["p_ai"] for v in pq.values() if v["author_difficulty"] == d]
        L.append(f"| {d} | {len(xs)} | {sum(xs) / max(1, len(xs)):.0%} |")
    cal = Counter(v["cal_difficulty"] for v in pq.values())
    agree = sum(1 for v in pq.values() if v["cal_difficulty"] == v["author_difficulty"])
    L.append(f"\nКалиброванная сложность (1 — все 4 персоны верно, 2 — три из четырёх, 3 — две и меньше): "
             f"1 — {cal[1]}, 2 — {cal[2]}, 3 — {cal[3]} вопросов. Совпадает с оценкой автора в {agree} из {len(pq)} "
             f"случаев. Приложение подбирает текст по калиброванной сложности (`cal_difficulty`).\n")
    L.append("## Привлекательность ловушек\n")
    L.append("Доля выборов неверного варианта данного типа среди всех предъявлений этого варианта персонам.\n")
    L.append("| Тип ловушки | Выбрано | Предъявлено | Привлекательность |")
    L.append("|---|---|---|---|")
    ta = sorted(out["trap_attractiveness"].items(), key=lambda kv: -kv[1]["picked"] / max(1, kv[1]["offered"]))
    for t, v in ta:
        L.append(f"| `{t}` | {v['picked']} | {v['offered']} | {v['picked'] / max(1, v['offered']):.1%} |")
    dead = sum(1 for v in pq.values() if not v["wrong_picks"])
    L.append(f"\nВопросов, где ни одна персона не ошиблась: {dead} из {len(pq)} — кандидаты на усиление дистракторов.\n")
    L.append("## Параметры BKT после калибровки\n")
    p = out["params"]
    L.append(f"- guess по сложности 1/2/3: {p['guess_by_difficulty']} (точность слабой персоны, сжатие к априорным [0.3, 0.22, 0.15]);")
    L.append(f"- slip по сложности 1/2/3: {p['slip_by_difficulty']} (ошибки средней+сильной, сжатие к [0.05, 0.1, 0.15]);")
    L.append(f"- evidence_guess = {p['evidence_guess']} — вероятность ткнуть в верное доказательство, не владея навыком;")
    L.append(f"- evidence_miss = {p['evidence_miss']} — вероятность промахнуться с доказательством, владея навыком. "
             "У ИИ-персон она почти нулевая, поэтому стоит нижний порог 0,15: дети чаще промахиваются соседним "
             "предложением, а верный ответ без доказательства должен оставаться слабым плюсом, а не штрафом.")
    L.append("\nОграничения: 4 персоны — мало; персоны — модели, а не дети; p_init и p_learn остаются априорными. "
             "Цель — разумный старт, а не точная психометрия.")
    (ROOT / "evals/ai_students_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
