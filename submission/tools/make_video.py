"""Assemble the pitch video and write pitch_script.md from the same segment list.

Inputs: build/marks.json + build/rec/*.webm (record_demo.py, DSF=1), build/shots_hi (DSF=2),
build/slides_png/video_*.png (build_slides.py), team.json (via tools/team.py), optional live voice
submission/voice/<segment id>.m4a|wav|mp3|aiff (used instead of the macOS voice Milena).
Output: submission/pitch.mp4, submission/pitch_script.md, build/timeline.json.

Rules (D24): opens on a live product clip with the phone large; a slide/table stays on screen <= 8.5 s,
then the narration continues over product footage; ends on a light title card with the link; <= 2:55.
"""
import base64, json, subprocess, html, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import team  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
SEG = BUILD / "seg"
SEG.mkdir(parents=True, exist_ok=True)
VOICE = ROOT / "voice"
FF = str(Path.home() / ".local/bin/ffmpeg")
FP = str(Path.home() / ".local/bin/ffprobe")
marks = json.loads((BUILD / "marks.json").read_text())
VID = {"student": marks["files"]["student"], "teacher": marks["files"]["teacher"]}
RATE = "172"        # words per minute for `say`
GAP = 0.35          # silence after each block
SLIDE_MAX = 8.5     # a slide never stays longer than this
END_HOLD = 1.8      # final title card stays after the last word
LIMIT = 175.0       # 2:55
T = team.load()

# Phone placement in the 1920x1080 frame: normal and large ("крупно": lower part of the screen, zoomed)
PX, PY, PW, PH = 330, 64, 440, 952
S = marks["student"]
TT = marks["teacher"]

PILOT_SAY = ("[[if pilot.n]]На пилоте с {{t:pilot.n}} учениками [[if pilot.guessed_pct]]{{t:pilot.guessed_pct}} верных ответов "
             "были без доказательства — обычный тест засчитал бы их как понимание.[[else]]механика «сначала докажи» прошла проверку.[[/if]]"
             "[[else]]Это симуляция, а не дети, поэтому следующий шаг — пилот в школе.[[/if]]")

SEGMENTS = [
    dict(id="01_hook", clip=("student", S["q2_start"] + 0.2, S["q2_prove"] + 0.6), big=True,
         eyebrow="Ізден · живой экран", title="Ответ верный.<br>А доказательство?",
         kk="«Жауап дұрыс, бірақ дәлел басқа жерде»",
         say="[[if pilot.guessed_num]]В нашем пилоте {{t:pilot.guessed_num}} процентов правильных ответов дети дали, не найдя "
             "доказательства в тексте. Обычный тест засчитал бы это как «умеет читать». Изден — нет.[[else]]"
             "Айгерим ответила правильно. Но в тексте нажала не то место — значит, могла угадать. "
             "Обычный тест этого не видит. Изден говорит: докажи.[[/if]]"),
    dict(id="02_problem", slide=2, broll=("student", S["q1_start"], S["q1_done"]),
         eyebrow="Кейс 3 · читать и понимать", title="Тест с вариантами не видит,<br>какую ошибку делает класс",
         kk="«Автобус кестесі» · 8-сынып",
         say="По данным пиза две тысячи двадцать пятого года, базового уровня по чтению достигли только тридцать шесть "
             "процентов казахстанских подростков. А по чтению в пиза две тысячи двадцать второго года сельские школы отстают от "
             "городских на тридцать семь баллов. В сельской школе слабый "
             "интернет, а телефон на уроке разрешён только для задания педагога. Значит, решение должно работать без сети "
             "и встраиваться в урок."),
    dict(id="03_offline", clip=("student", 0.6, S["q1_start"]),
         eyebrow="Демо · ученик", title="Открыли один раз —<br>работает в режиме полёта",
         kk="«Офлайн» · Интернет жоқ — сақталған деректермен жұмыс істейміз",
         say="Изден — это сайт, который достаточно открыть один раз. Включаем режим полёта, обновляем страницу — "
             "приложение работает на сохранённых данных. Айгерим выбирает казахский язык и восьмой класс."),
    dict(id="04_trap", clip=("student", S["q1_start"], S["q1_done"]),
         eyebrow="Шаг 1 · сначала доказательство", title="Нашла место, но вывела неверно → ловушка",
         kk="«Дәлелді таптың, бірақ қорытынды қате» · Қақпан: «Кестенің басқа жолы немесе бағаны»",
         say="Правило одно: сначала нажми в тексте доказательство, потом выбери ответ. Айгерим нажимает рейс сто семь и "
             "выбирает его. Место верное, а вывод нет: она посмотрела на время отправления, а спрашивали время прибытия. "
             "Изден называет ловушку и даёт подсказку-шаг. Подсветить ответ можно только кнопкой, и тогда он засчитывается "
             "«с помощью»."),
    dict(id="05_prove", clip=("student", S["q2_start"] - 0.3, S["q2_proved"]),
         eyebrow="Шаг 2 · угадал? докажи", title="Верный ответ без доказательства<br>не считается пониманием",
         kk="«Жауап дұрыс, бірақ дәлел басқа жерде» → «Енді дәлелденді!»",
         say="Второй вопрос. Ответ верный, но нажато не то место. Это не засчитывается как понимание. "
             "Айгерим находит нужную строку — теперь доказано."),
    dict(id="06_adaptive", clip=("student", S["unit_summary"] - 2.0, S["progress"] - 0.5),
         eyebrow="Модель навыков", title="Следующий текст — под самый слабый навык",
         kk="«Неге осы мәтін?» · «Тапсырма туралы»",
         say="Модель навыков обновляет три навыка — найти, понять, оценить — и подбирает следующий текст под самый слабый, "
             "объясняя выбор. У каждого текста есть паспорт: как его создали и проверили нейросети."),
    dict(id="07_qr", clip=("student", S["progress"] - 0.3, S["qr"]),
         eyebrow="Передача учителю", title="QR-код или короткий код,<br>без интернета",
         kk="«Мұғалімге жіберу»",
         say="Результат уходит учителю без интернета — через кью-ар код или короткий код."),
    dict(id="08_teacher", clip=("teacher", 0.8, TT["class_traps"]),
         eyebrow="Демо · учитель", title="Ловушка класса видна сразу",
         kk="«Сынып есебі» · «Сыныптың жиі қақпандары» · демо-сынып помечен «демо»",
         say="Телефон учителя сканирует код. Добавим демо-класс: виден самый слабый навык, кто отвечает верно без "
             "доказательства и в какую ловушку чаще всего попадает класс."),
    dict(id="09_tomorrow", clip=("teacher", TT["class_traps"], TT["end"]),
         eyebrow="Что делать завтра", title="Приём на 10 минут<br>и лист для печати",
         kk="«Ертең не істеу керек» · «Тапсырмалар парағы»",
         say="Одна кнопка — и у учителя карточка «что делать завтра»: приём на десять минут и мини-лист для печати. "
             "Ученик без телефона получает лист заданий с бланком и ключом."),
    dict(id="10_ru", clip=("student", S["ru_start"], S["ru_practice"]),
         eyebrow="Қаз / Рус", title="Русский — одним переключателем",
         kk="Тексты на русском написаны отдельно, не переводом",
         say="Всё то же есть на русском: тексты написаны отдельно, а не переводом."),
    dict(id="11_proof", slide=7, broll=("student", S["unit_summary"] - 2.0, S["progress"] - 0.3),
         eyebrow="Где ИИ", title="Паспорт задания:<br>как текст сделан и проверен",
         kk="«Тапсырма туралы»",
         say="Где здесь искусственный интеллект? До урока. Нейросеть написала тридцать шесть текстов и сто шестьдесят пять "
             "вопросов. Другая нейросеть решила их вслепую — все сто шестьдесят пять совпали с ключом. Четыре виртуальных "
             "ученика откалибровали сложность. " + PILOT_SAY),
    dict(id="12_scale", slide=9, broll=("student", 0.6, S["q1_start"]),
         eyebrow="Масштаб", title="0 ₸ за сервер, 0 МБ трафика,<br>один телефон на класс",
         kk="izden.vercel.app",
         say="Для школы это ноль тенге за сервер и ноль мегабайт трафика после первого открытия. Урок сорок пять минут без телефона "
             "у каждого: бумажный лист и один телефон учителя."),
    dict(id="13_call", endcard=True,
         say="Изден: сначала докажи, потом ответь. Нам нужны учителя казахского и русского для вычитки и пилота. "
             "Откройте изден точка версел точка эпп."),
]
SCREEN_SAY = {  # how the voice text should be written in the script for live readers (numbers/brands readable)
    "пиза": "PISA", "изден точка версел точка эпп": "izden.vercel.app", "кью-ар код": "QR-код",
}

CSS = """
body{margin:0;width:1920px;height:1080px;background:#f7f2e8;font-family:system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;color:#1d2a29;overflow:hidden;position:relative}
.right{position:absolute;left:900px;right:110px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center}
.right.big{left:1060px}
.eyebrow{font-size:28px;letter-spacing:.12em;text-transform:uppercase;color:#20756d;font-weight:700;margin:0 0 22px}
h1{font-size:72px;line-height:1.1;margin:0 0 40px;letter-spacing:-.015em}
.kk{font-size:32px;line-height:1.4;color:#3b4a48;border-left:8px solid #f6cf6a;padding:6px 0 6px 26px;margin:0}
.foot{position:absolute;left:900px;bottom:44px;font-size:24px;color:#6b7672}.foot b{color:#16524d}
.bezel{position:absolute;border:14px solid #1d2a29;border-radius:52px;margin:-14px;box-shadow:0 40px 80px -30px rgba(29,42,41,.5);background:#fff}
.end{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.logo{font-size:200px;font-weight:800;letter-spacing:-.03em;color:#16524d;line-height:1}
.tag{font-size:64px;margin:30px 0 50px}.tag span{background:linear-gradient(transparent 55%,#f6cf6a 55%);padding:0 6px}
.url{font-size:72px;font-weight:700;color:#1d2a29}
.sub{font-size:34px;color:#6b7672;margin-top:30px}
"""
# big layout: crop the lower 520 px of the 390x844 phone video, scale x2 -> 780x1040
BIG = dict(crop=(0, 844 - 520, 390, 520), x=150, y=20, w=780, h=1040)


def frame_html(seg):
    if seg.get("endcard"):
        team_line = team.render("[[if team]]Команда «{{t:team}}» · [[/if]]Órleu Hack 2026 · кейс 3", T)
        return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style><div class="end">
<div class="logo">Ізден</div><p class="tag">Сначала <span>докажи</span> — потом ответь</p>
<p class="url">izden.vercel.app</p><p class="sub">{html.escape(team_line)}</p></div>"""
    if seg.get("big"):
        x, y, w, h = BIG["x"], BIG["y"], BIG["w"], BIG["h"]
        bez = f'<div class="bezel" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:40px 40px 0 0;border-bottom:0"></div>'
        cls = "right big"
    else:
        bez = f'<div class="bezel" style="left:{PX}px;top:{PY}px;width:{PW}px;height:{PH}px"></div>'
        cls = "right"
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style>{bez}
<div class="{cls}"><p class="eyebrow">{html.escape(seg['eyebrow'])}</p>
<h1>{seg['title']}</h1><p class="kk" lang="kk">{html.escape(seg['kk'])}</p></div>
<p class="foot" style="{'left:1060px' if seg.get('big') else ''}"><b>Ізден</b> · izden.vercel.app</p>"""


def dur(path):
    return float(subprocess.check_output([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))


def run(args):
    subprocess.run([FF, "-y", "-v", "error"] + args, check=True)


ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30", "-pix_fmt", "yuv420p"]


def still_part(png, length, out):
    run(["-loop", "1", "-framerate", "30", "-i", str(png), "-vf", "scale=1920:1080,format=yuv420p",
         "-t", f"{length:.3f}"] + ENC + ["-an", str(out)])


def clip_part(who, a, z, length, bg, out, big=False):
    L = z - a
    f = min(max(length / L, 0.45), 1.3)  # pts multiplier: slow down / speed up the screen recording
    pad = max(0.0, length - L * f) + 0.1
    if big:
        cx, cy, cw, ch = BIG["crop"]
        scale = f"crop={cw}:{ch}:{cx}:{cy},scale={BIG['w']}:{BIG['h']}:flags=lanczos"
        pos = f"{BIG['x']}:{BIG['y']}"
    else:
        scale = f"scale={PW}:{PH}:flags=lanczos"
        pos = f"{PX}:{PY}"
    vf = (f"[0:v]trim=start={a:.2f}:end={z:.2f},setpts=(PTS-STARTPTS)*{f:.4f},fps=30,{scale},"
          f"tpad=stop_mode=clone:stop_duration={pad:.2f}[ph];[1:v][ph]overlay={pos}:shortest=0,"
          f"trim=duration={length:.3f},format=yuv420p[v]")
    run(["-i", VID[who], "-loop", "1", "-framerate", "30", "-i", str(bg), "-filter_complex", vf, "-map", "[v]",
         "-t", f"{length:.3f}"] + ENC + ["-an", str(out)])
    return f


def voice_for(seg, text):
    """Live recording from submission/voice/<id>.* wins over the synthetic voice."""
    for ext in ("m4a", "wav", "mp3", "aiff"):
        live = VOICE / f"{seg['id']}.{ext}"
        if live.exists():
            out = SEG / f"{seg['id']}_live.wav"
            run(["-i", str(live), "-ac", "1", "-ar", "48000", str(out)])
            return out, "live"
    out = SEG / f"{seg['id']}.aiff"
    subprocess.run(["say", "-v", "Milena", "-r", RATE, "-o", str(out), text], check=True)
    return out, "Milena"


def main():
    for seg in SEGMENTS:
        seg["say"] = team.render(seg["say"], T)
        seg["audio_file"], seg["voice"] = voice_for(seg, seg["say"])
        seg["A"] = dur(seg["audio_file"]) + GAP + (END_HOLD if seg.get("endcard") else 0)
    total = sum(s["A"] for s in SEGMENTS)
    print(f"voice total {total:.1f}s; live voice: {[s['id'] for s in SEGMENTS if s['voice'] == 'live']}")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for seg in SEGMENTS:
            if seg.get("clip") or seg.get("broll") or seg.get("endcard"):
                pg.set_content(frame_html(seg))
                pg.wait_for_timeout(200)
                seg["bg"] = SEG / f"{seg['id']}_bg.png"
                pg.screenshot(path=str(seg["bg"]))
        b.close()
    parts, timeline, t = [], [], 0.0
    for seg in SEGMENTS:
        A = seg["A"]
        vis = []
        if seg.get("clip"):
            who, a, z = seg["clip"]
            f = clip_part(who, a, z, A, seg["bg"], SEG / f"{seg['id']}_v0.mp4", big=seg.get("big"))
            vis.append(SEG / f"{seg['id']}_v0.mp4")
            note = f"{'BIG ' if seg.get('big') else ''}clip {who} {a:.1f}-{z:.1f}s x{f:.2f}"
        elif seg.get("slide"):
            png = BUILD / "slides_png" / f"video_{seg['slide']:02d}.png"
            first = min(A, SLIDE_MAX)
            still_part(png, first, SEG / f"{seg['id']}_v0.mp4")
            vis.append(SEG / f"{seg['id']}_v0.mp4")
            note = f"slide {seg['slide']} {first:.1f}s"
            if A - first > 0.2:
                who, a, z = seg["broll"]
                clip_part(who, a, z, A - first, seg["bg"], SEG / f"{seg['id']}_v1.mp4")
                vis.append(SEG / f"{seg['id']}_v1.mp4")
                note += f" + clip {who} {a:.1f}-{z:.1f}s {A - first:.1f}s"
        else:  # end card
            still_part(seg["bg"], A, SEG / f"{seg['id']}_v0.mp4")
            vis.append(SEG / f"{seg['id']}_v0.mp4")
            note = "end card (title + link)"
        vlist = SEG / f"{seg['id']}_vlist.txt"
        vlist.write_text("".join(f"file '{v}'\n" for v in vis))
        out = SEG / f"{seg['id']}.mp4"
        run(["-f", "concat", "-safe", "0", "-i", str(vlist), "-i", str(seg["audio_file"]),
             "-filter_complex", f"[1:a]aresample=48000,apad=whole_dur={A:.3f}[a]", "-map", "0:v", "-map", "[a]",
             "-t", f"{A:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", str(out)])
        parts.append(out)
        timeline.append({"id": seg["id"], "start": round(t, 1), "end": round(t + A, 1), "visual": note,
                         "voice": seg["voice"], "words": len(seg["say"].split()), "say": seg["say"]})
        t += A
    lst = SEG / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(ROOT / "pitch.mp4")])
    (BUILD / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1))
    d = dur(ROOT / "pitch.mp4")
    write_script(timeline, d)
    print("pitch.mp4", round(d, 2), "s", "OK" if d <= LIMIT else "TOO LONG")
    assert d <= LIMIT, f"video {d:.1f}s > {LIMIT}s"


def mmss(x):
    return f"{int(x // 60)}:{int(x % 60):02d}"


def readable(text):
    for k, v in SCREEN_SAY.items():
        text = text.replace(k, v)
    return text


def write_script(timeline, total):
    seg_by = {s["id"]: s for s in SEGMENTS}
    rows = []
    for x in timeline:
        s = seg_by[x["id"]]
        shown = x["visual"]
        if s.get("title"):
            shown += " · " + s["title"].replace("<br>", " ")
        rows.append(f"| {mmss(x['start'])}–{mmss(x['end'])} | `{x['id']}` | {shown} | {readable(x['say'])} |")
    words = sum(x["words"] for x in timeline)
    text = f"""<!-- Сгенерировано tools/make_video.py — правьте тексты там, затем пересоберите видео. -->
# Ізден — сценарий питч-видео

Видео `pitch.mp4` — {mmss(total)} ({total:.1f} с по ffprobe). Запись демо — с прода https://izden.vercel.app в Playwright,
телефон 390×844 в кадре 1920×1080. Начало — живой экран продукта крупно («угадал — докажи»); слайд с цифрами стоит не дольше
{SLIDE_MAX:g} с, дальше голос идёт поверх кадров продукта; конец — светлая карточка с названием и ссылкой.
Голос по умолчанию — macOS Milena (синтез, {words} слов). «PISA» в тексте синтеза записано как «пиза», адрес — «изден точка версел точка эпп».
Данные команды и пилота берутся из `submission/team.json`: пустые поля не показываются.

## Живая озвучка вместо синтеза

1. Запишите каждый блок отдельным файлом (телефон, тихая комната, 20–30 см от микрофона, без музыки).
2. Назовите файл по ключу блока из таблицы и положите в `submission/voice/`, например `submission/voice/01_hook.m4a`
   (подходят `.m4a`, `.wav`, `.mp3`, `.aiff`). Можно записать только часть блоков — остальные останутся синтезом.
3. Читайте текст из таблицы своими словами, но держите длину: блок не должен стать длиннее, чем в колонке «Время», иначе
   видео превысит 2:55 (скрипт остановится с ошибкой).
4. Пересоберите: `python3 tools/make_video.py` (в `build/timeline.json` поле `voice` покажет, где живой голос).

| Время | Ключ | Что в кадре | Текст голоса |
|---|---|---|---|
{chr(10).join(rows)}

## Как пересобрать всё

```bash
cd submission
DSF=2 python3 tools/record_demo.py && rm -rf build/shots_hi && mv build/shots build/shots_hi   # скриншоты для слайдов
python3 tools/record_demo.py                                          # запись видео с прода (DSF=1)
python3 tools/render_docs.py                                          # DEFENSE.md, DESCRIPTION.md из team.json
python3 tools/build_slides.py                                         # slides.html, slides.pdf, кадры слайдов
python3 tools/make_video.py                                           # озвучка + склейка → pitch.mp4, этот сценарий
```
Нужны Playwright (Chromium), `~/.local/bin/ffmpeg`, macOS `say`. Учительский телефон сканирует QR через виртуальную камеру
Chromium; если камера не сработает, скрипт вводит короткий код.
"""
    (ROOT / "pitch_script.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
