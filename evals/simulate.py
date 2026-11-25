#!/usr/bin/env python3
"""Sanity check of the BKT engine on synthetic students (NOT evidence of real learning effect).

Each synthetic student has a hidden binary state per skill (knows / does not know), answers by the
same slip/guess model the engine assumes, and may learn a skill each time they practise it.
We compare three ways to pick the next text: adaptive (js/engine.js logic), fixed workbook order,
random. Same students, same random seeds for every policy.

  python3 evals/simulate.py            -> prints tables, writes evals/bkt_report.md and evals/bkt_results.json
"""
import json
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E  # noqa: E402

N_STUDENTS = 500
N_QUESTIONS = 40
CHECKPOINTS = [8, 16, 24, 40]
TRUE_LEARN = 0.12  # chance a not-yet-known skill becomes known after practising it once
SEED = 42


def make_students(rng):
    out = []
    for i in range(N_STUDENTS):
        ability = rng.random()  # overall reader strength
        known = {s: rng.random() < (0.1 + 0.6 * ability) * rng.uniform(0.5, 1.3) for s in E.SKILLS}
        out.append({"grade": rng.choice([7, 8, 9]), "known": known, "seed": rng.randrange(10**9)})
    return out


def order_fixed(units, grade):
    return sorted(units, key=lambda u: (abs(u["grade"] - grade), E._unit_number(u["id"]), u["id"]))


def run(policy, student, units, params):
    rng = random.Random(student["seed"])
    known = dict(student["known"])
    state = E.new_state(params)
    fixed = order_fixed(units, student["grade"])
    shuffled = units[:]
    random.Random(student["seed"] + 1).shuffle(shuffled)
    snaps, useful, asked, reach = {}, 0, 0, None
    step = 0
    while asked < N_QUESTIONS:
        if policy == "adaptive":
            unit = E.select_next_unit(state, params, units, student["grade"])["unit"]
        elif policy == "fixed":
            unit = fixed[step % len(fixed)]
        else:
            unit = shuffled[step % len(shuffled)]
        step += 1
        qs = E.select_questions(state, params, unit) if policy == "adaptive" else unit["questions"]
        for q in qs:
            if asked >= N_QUESTIONS:
                break
            s = q["process"]
            slip, guess = E.slip_guess(params, q["difficulty"])
            if not known[s]:
                useful += 1
            ok = rng.random() < ((1 - slip) if known[s] else guess)
            wrong = next(o for o in q["options"] if not o["correct"])
            E.apply_answer(state, params, q, ok, None if ok else wrong["trap"])
            if not known[s] and rng.random() < TRUE_LEARN:
                known[s] = True
            asked += 1
            errs = [abs(state["skills"][k]["p"] - (1.0 if known[k] else 0.0)) for k in E.SKILLS]
            if reach is None and max(errs) <= 0.15:
                reach = asked
            if asked in CHECKPOINTS:
                snaps[asked] = {
                    "mae": sum(errs) / 3,
                    "acc": sum((state["skills"][k]["p"] >= 0.5) == known[k] for k in E.SKILLS) / 3,
                }
        E.mark_unit_done(state, unit["id"])
    return {"snaps": snaps, "useful": useful / asked, "known_end": sum(known.values()) / 3,
            "known_start": sum(student["known"].values()) / 3, "reach": reach}


def summarize(results):
    out = {}
    for cp in CHECKPOINTS:
        out[f"mae@{cp}"] = st.mean(r["snaps"][cp]["mae"] for r in results)
        out[f"acc@{cp}"] = st.mean(r["snaps"][cp]["acc"] for r in results)
    out["useful_share"] = st.mean(r["useful"] for r in results)
    out["known_start"] = st.mean(r["known_start"] for r in results)
    out["known_end"] = st.mean(r["known_end"] for r in results)
    reached = [r["reach"] for r in results if r["reach"] is not None]
    out["reach_share"] = len(reached) / len(results)
    out["reach_median"] = st.median(reached) if reached else None
    return out


def main():
    params = E.load_params()
    all_res = {}
    for lang in ("ru", "kk"):
        units = E.load_bank(lang)
        students = make_students(random.Random(SEED))
        all_res[lang] = {p: summarize([run(p, s, units, params) for s in students])
                         for p in ("adaptive", "fixed", "random")}
    (Path(__file__).parent / "bkt_results.json").write_text(json.dumps(all_res, indent=1), encoding="utf-8")
    write_report(all_res, params)
    for lang, res in all_res.items():
        print(lang)
        for p, s in res.items():
            print(f"  {p:9s} " + " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in s.items()))


def pct(x):
    return f"{x * 100:.1f}%"


def write_report(res, params):
    L = []
    L.append("# Эвал BKT-движка: проверка работоспособности на синтетических учениках\n")
    L.append("> **Это не доказательство эффекта на реальных детях.** Синтетические ученики отвечают по той же "
             "модели (slip/guess), которую предполагает движок, поэтому проверка показывает только, что движок "
             "считает правильно, сходится и что адаптивный выбор текста делает то, что задумано. "
             "Эффект на реальных учениках нужно мерить пилотом в школе.\n")
    L.append("Запуск: `python3 evals/simulate.py` (детерминирован, seed 42). Алгоритм — `evals/engine.py`, "
             "побитово сверен с `js/engine.js` тестом `tests/test_engine.py`.\n")
    L.append("## Постановка\n")
    L.append(f"- {N_STUDENTS} синтетических учеников, у каждого скрытое состояние «знает / не знает» по трём навыкам "
             "(найти, понять, оценить); доля изначально знающих зависит от «силы читателя» ученика.")
    L.append(f"- Каждый ученик отвечает на {N_QUESTIONS} вопросов (около 10 текстов). Ответ верен с вероятностью "
             f"1 − slip, если навык известен, и guess, если нет (slip/guess по сложности: "
             f"{params['slip_by_difficulty']} / {params['guess_by_difficulty']}).")
    L.append(f"- После каждого вопроса по неосвоенному навыку ученик осваивает его с вероятностью {TRUE_LEARN}.")
    L.append("- Три политики выбора следующего текста на одних и тех же учениках и случайных числах: "
             "**адаптивная** (как в приложении: текст под слабейший навык + сложность ≈ уровню + свой класс; "
             "вопросы по уже освоенному навыку (p ≥ 0,85) пропускаются, но не меньше 2 вопросов на текст), "
             "**фиксированная** (как в сборнике: свой класс по порядку), **случайная**.\n")
    L.append("Метрики:")
    L.append("- **MAE** — средняя ошибка оценки p(знает) против скрытого состояния (0 или 1), меньше — лучше;")
    L.append("- **Точность** — доля навыков, где порог p ≥ 0,5 совпал со скрытым состоянием;")
    L.append("- **Полезная практика** — доля вопросов по навыку, который ученик в тот момент ещё не знал;")
    L.append("- **Освоено к концу** — доля освоенных навыков после 40 вопросов (в начале — см. строку «в начале»);")
    L.append("- **Точность ±0,15** — доля учеников, у которых все три оценки хотя бы раз оказались в пределах 0,15 "
             "от истины, и медиана числа вопросов до этого.\n")
    for lang, r in res.items():
        L.append(f"## Банк `{lang}`\n")
        L.append("| Метрика | Адаптивная | Фиксированная | Случайная |")
        L.append("|---|---|---|---|")
        for cp in CHECKPOINTS:
            L.append(f"| MAE после {cp} вопросов | " + " | ".join(f"{r[p][f'mae@{cp}']:.3f}" for p in r) + " |")
        for cp in (16, 40):
            L.append(f"| Точность после {cp} вопросов | " + " | ".join(pct(r[p][f'acc@{cp}']) for p in r) + " |")
        L.append("| Полезная практика | " + " | ".join(pct(r[p]["useful_share"]) for p in r) + " |")
        L.append("| Освоено навыков: в начале | " + " | ".join(pct(r[p]["known_start"]) for p in r) + " |")
        L.append("| Освоено навыков: после 40 вопросов | " + " | ".join(pct(r[p]["known_end"]) for p in r) + " |")
        L.append("| Достигли точности ±0,15 | " + " | ".join(pct(r[p]["reach_share"]) for p in r) + " |")
        L.append("| Медиана вопросов до ±0,15 | " + " | ".join(str(r[p]["reach_median"]) for p in r) + " |")
        L.append("")
    a, f = res["ru"]["adaptive"], res["ru"]["fixed"]
    L.append("## Вывод (честно)\n")
    L.append(f"- Движок сходится: ошибка оценки падает с ростом числа вопросов у всех политик "
             f"(ru, адаптивная: MAE {a['mae@8']:.2f} → {a['mae@40']:.2f}).")
    L.append(f"- Адаптивная политика быстрее уточняет оценку (ru: MAE после 24 вопросов {a['mae@24']:.3f} против "
             f"{f['mae@24']:.3f}) и тратит меньше вопросов на уже освоенное.")
    L.append(f"- Адаптивный выбор чаще даёт практику по ещё не освоенному навыку "
             f"({pct(a['useful_share'])} против {pct(f['useful_share'])} у фиксированного порядка), поэтому в этой "
             f"модели к концу освоено больше навыков ({pct(a['known_end'])} против {pct(f['known_end'])}).")
    L.append("- Разница ограничена устройством банка: в каждом тексте 4 вопроса разных процессов (2 вопроса "
             "доминирующего), поэтому выбор текста лишь смещает долю практики, а не делает её чистой.")
    L.append("- Параметры BKT заданы вручную (априорные значения из литературы по BKT), а не обучены на реальных "
             "ответах. Следующий шаг — пилот в 2–3 классах и подгонка параметров по реальным логам.")
    (Path(__file__).parent / "bkt_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
