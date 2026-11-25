"""Assemble the draft pitch video: macOS voice (Milena, ru) + phone demo clips + slides.

Inputs: build/marks.json + build/rec/*.webm (record_demo.py, DSF=1), build/shots_hi (DSF=2),
build/slides_png/video_*.png (build_slides.py). Output: submission/pitch.mp4, build/timeline.json.
"""
import base64, json, subprocess, html
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
SEG = BUILD / "seg"
SEG.mkdir(parents=True, exist_ok=True)
FF = str(Path.home() / ".local/bin/ffmpeg")
FP = str(Path.home() / ".local/bin/ffprobe")
marks = json.loads((BUILD / "marks.json").read_text())
VID = {"student": marks["files"]["student"], "teacher": marks["files"]["teacher"]}
RATE = "172"  # words per minute for `say`
GAP = 0.35    # silence after each block

# Phone screen placement in the 1920x1080 frame
PX, PY, PW, PH = 330, 64, 440, 952

S = marks["student"]
T = marks["teacher"]
SEGMENTS = [
    dict(id="01_hook", still="shots_hi/s09_q2_prove.png",
         eyebrow="Ізден · Órleu Hack 2026", title="Ответ верный.<br>Но поняла ли она текст?",
         kk="Экранда: «Жауап дұрыс, бірақ дәлел басқа жерде»",
         say="Айгерим, восьмой класс, ответила правильно. Но поняла ли она текст или угадала? Обычный тест этого не видит. Изден видит."),
    dict(id="02_problem", slide=2,
         say="По данным кейса, в ПИЗА две тысячи двадцать пятого года базового уровня по чтению достигли только тридцать шесть процентов казахстанских подростков. Разрыв между городом и селом — восемнадцать баллов. В сельской школе слабый интернет, а телефон на уроке разрешён только для задания педагога. Значит, решение должно работать без сети и встраиваться в урок."),
    dict(id="03_offline", clip=("student", 0.6, S["q1_start"]),
         eyebrow="Демо · ученик", title="Открыли один раз —<br>работает в режиме полёта",
         kk="«Интернет жоқ — бәрі жұмыс істейді» · Айгерім, 8-сынып",
         say="Изден — это сайт, который достаточно открыть один раз. Включаем режим полёта, обновляем страницу — всё работает. Айгерим выбирает казахский язык и восьмой класс."),
    dict(id="04_trap", clip=("student", S["q1_start"], S["q1_done"]),
         eyebrow="Шаг 1 · сначала доказательство", title="Нашла место, но вывела неверно → ловушка",
         kk="«Дәлелді таптың, бірақ қорытынды қате» · Қақпан: «Кестенің басқа жолы немесе бағаны»",
         say="Правило одно: сначала нажми в тексте доказательство, потом выбери ответ. Айгерим нажимает рейс сто семь и выбирает его. Место верное, а вывод нет: она посмотрела на время отправления, а спрашивали время прибытия. Изден называет ловушку и даёт подсказку-шаг. Подсветить ответ можно только кнопкой, и тогда он засчитывается «с помощью»."),
    dict(id="05_prove", clip=("student", S["q2_start"] - 0.3, S["q2_proved"]),
         eyebrow="Шаг 2 · угадал? докажи", title="Верный ответ без доказательства<br>не считается пониманием",
         kk="«Жауап дұрыс, бірақ дәлел басқа жерде» → «Енді дәлелденді!»",
         say="Второй вопрос. Ответ верный, но нажато не то место. Это не засчитывается как понимание: «Угадал? Докажи». Айгерим находит нужную строку — теперь доказано."),
    dict(id="06_adaptive", clip=("student", S["unit_summary"] - 2.0, S["progress"] - 0.5),
         eyebrow="Модель навыков", title="Следующий текст — под самый слабый навык",
         kk="«Неге осы мәтін?» · «Тапсырма паспорты»",
         say="Модель навыков обновляет три навыка — найти, понять, оценить — и подбирает следующий текст под самый слабый, объясняя выбор. У каждого текста есть паспорт: как его создали и проверили нейросети."),
    dict(id="07_qr", clip=("student", S["progress"] - 0.3, S["qr"]),
         eyebrow="Передача учителю", title="QR-код или короткий код,<br>без интернета",
         kk="«Мұғалімге жіберу»",
         say="Результат уходит учителю без интернета — через кью-ар код или короткий код."),
    dict(id="08_teacher", clip=("teacher", 0.8, T["class_traps"]),
         eyebrow="Демо · учитель", title="Ловушка класса видна сразу",
         kk="«Сынып есебі» · «Сыныптың жиі қақпандары» · демо-сынып помечен «демо»",
         say="Телефон учителя сканирует код. Добавим демо-класс: виден самый слабый навык, кто отвечает верно без доказательства и в какую ловушку чаще всего попадает класс."),
    dict(id="09_tomorrow", clip=("teacher", T["class_traps"], T["end"]),
         eyebrow="Что делать завтра", title="Приём на 10 минут<br>и лист для печати",
         kk="«Ертең не істеу керек» · «Тапсырмалар парағы»",
         say="Одна кнопка — и у учителя карточка «что делать завтра»: приём на десять минут и мини-лист для печати. Ученик без телефона получает лист заданий с бланком и ключом."),
    dict(id="10_ru", clip=("student", S["ru_start"], S["ru_practice"]),
         eyebrow="Қаз / Рус", title="Русский — одним переключателем",
         kk="Тексты на русском написаны отдельно, не переводом",
         say="Всё то же есть на русском: тексты написаны отдельно, а не переводом."),
    dict(id="11_proof", slide=7,
         say="Где здесь искусственный интеллект? До урока. Нейросеть написала тридцать шесть текстов и сто шестьдесят пять вопросов. Другая нейросеть решила их вслепую — все сто шестьдесят пять совпали с ключом. Четыре виртуальных ученика откалибровали сложность. Это симуляция, а не дети, поэтому следующий шаг — пилот в школе."),
    dict(id="12_scale", slide=9,
         say="Сервера нет: сайт весит меньше мегабайта и работает на обычном телефоне. Новый текст, по нашей оценке, стоит от двадцати пяти центов до полутора долларов плюс вычитка учителем."),
    dict(id="13_call", slide=1,
         say="Изден: сначала докажи, потом ответь. Нам нужны учителя казахского и русского для вычитки и пилота. Откройте изден точка версел точка эпп."),
]

FRAME_CSS = """
body{margin:0;width:1920px;height:1080px;background:#f7f2e8;font-family:system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;color:#1d2a29;overflow:hidden;position:relative}
.bezel{position:absolute;left:%dpx;top:%dpx;width:%dpx;height:%dpx;border:14px solid #1d2a29;border-radius:52px;margin:-14px;box-shadow:0 40px 80px -30px rgba(29,42,41,.5);background:#fff;overflow:hidden}
.bezel img{width:100%%;display:block}
.right{position:absolute;left:900px;right:110px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center}
.eyebrow{font-size:28px;letter-spacing:.12em;text-transform:uppercase;color:#20756d;font-weight:700;margin:0 0 22px}
h1{font-size:72px;line-height:1.1;margin:0 0 40px;letter-spacing:-.015em}
.kk{font-size:32px;line-height:1.4;color:#3b4a48;border-left:8px solid #f6cf6a;padding:6px 0 6px 26px;margin:0}
.foot{position:absolute;left:900px;bottom:44px;font-size:24px;color:#6b7672}.foot b{color:#16524d}
""" % (PX, PY, PW, PH)


def frame_html(seg):
    img = ""
    if seg.get("still"):  # set_content runs on about:blank, so file:// images are blocked -> inline
        b64 = base64.b64encode((BUILD / seg["still"]).read_bytes()).decode()
        img = f'<img src="data:image/png;base64,{b64}">'
    return f"""<!doctype html><meta charset="utf-8"><style>{FRAME_CSS}</style>
<div class="bezel">{img}</div><div class="right"><p class="eyebrow">{html.escape(seg['eyebrow'])}</p>
<h1>{seg['title']}</h1><p class="kk" lang="kk">{html.escape(seg['kk'])}</p></div>
<p class="foot"><b>Ізден</b> · izden.vercel.app</p>"""


def dur(path):
    return float(subprocess.check_output([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def run(args):
    subprocess.run([FF, "-y", "-v", "error"] + args, check=True)


def main():
    # 1. voice
    for seg in SEGMENTS:
        aiff = SEG / f"{seg['id']}.aiff"
        subprocess.run(["say", "-v", "Milena", "-r", RATE, "-o", str(aiff), seg["say"]], check=True)
        seg["audio"] = dur(aiff) + GAP
    total = sum(s["audio"] for s in SEGMENTS)
    words = sum(len(s["say"].split()) for s in SEGMENTS)
    print(f"voice total {total:.1f}s, {words} words")
    # 2. frames for demo segments
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for seg in SEGMENTS:
            if "slide" in seg:
                seg["bg"] = BUILD / "slides_png" / f"video_{seg['slide']:02d}.png"
                continue
            pg.set_content(frame_html(seg))
            pg.wait_for_timeout(200)
            seg["bg"] = SEG / f"{seg['id']}_bg.png"
            pg.screenshot(path=str(seg["bg"]))
        b.close()
    # 3. per-segment video
    parts = []
    timeline = []
    t = 0.0
    for seg in SEGMENTS:
        out = SEG / f"{seg['id']}.mp4"
        A = seg["audio"]
        aud = ["-i", str(SEG / f"{seg['id']}.aiff")]
        afilt = f"[1:a]aresample=48000,apad=whole_dur={A:.3f}[a]"
        if "clip" in seg:
            who, a, z = seg["clip"]
            L = z - a
            f = min(max(A / L, 0.45), 1.3)  # speed change factor (pts multiplier)
            pad = max(0.0, A - L * f) + 0.1
            vf = (f"[0:v]trim=start={a:.2f}:end={z:.2f},setpts=(PTS-STARTPTS)*{f:.4f},fps=30,"
                  f"scale={PW}:{PH}:flags=lanczos,tpad=stop_mode=clone:stop_duration={pad:.2f}[ph];"
                  f"[2:v][ph]overlay={PX}:{PY}:shortest=0,trim=duration={A:.3f},format=yuv420p[v];" + afilt)
            run(["-i", VID[who]] + aud + ["-loop", "1", "-framerate", "30", "-i", str(seg["bg"]),
                 "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{A:.3f}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30", "-c:a", "aac", "-b:a", "160k", str(out)])
            note = f"clip {who} {a:.1f}-{z:.1f}s x{f:.2f}"
        else:
            vf = (f"[0:v]scale=1920:1080,format=yuv420p,trim=duration={A:.3f}[v];" + afilt)
            run(["-loop", "1", "-framerate", "30", "-i", str(seg["bg"])] + aud +
                ["-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", f"{A:.3f}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30", "-c:a", "aac", "-b:a", "160k", str(out)])
            note = f"slide {seg.get('slide')}"
        parts.append(out)
        timeline.append({"id": seg["id"], "start": round(t, 1), "end": round(t + A, 1), "visual": note,
                         "words": len(seg["say"].split()), "say": seg["say"]})
        t += A
    lst = SEG / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(ROOT / "pitch.mp4")])
    (BUILD / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1))
    print("pitch.mp4", round(dur(ROOT / "pitch.mp4"), 2), "s")


if __name__ == "__main__":
    main()
