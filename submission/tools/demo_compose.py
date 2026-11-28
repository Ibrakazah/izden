"""Compose build/demo/phone.mp4 + marks.json into submission/demo.mp4 (1920x1080): phone in a frame, captions on the right, end card."""
import json, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'build/demo'
M = json.loads((D / 'marks.json').read_text())
END_HOLD = 4.5
PX, PY, PW, PH = 250, 51, 452, 978          # screen rectangle

CAP = {
    'offline': ('Работает без интернета', 'Сайт открыли один раз — дальше всё работает в режиме полёта. Язык — казахский или русский.'),
    'evidence': ('Сначала доказательство', 'Айгерим нажимает в расписании строку, где, по её мнению, ответ, — и только потом выбирает вариант.'),
    'trap': ('Место верное, вывод — нет', 'Ізден называет ловушку: смотрела на отправление, а важно прибытие. Дальше — подсказка-шаг, а не готовый ответ. Подсветка ответа засчитывается «с&nbsp;помощью».'),
    'prove': ('Угадал? Докажи', 'Ответ верный, но доказательство не там. Обычный тест поставил бы плюс — Ізден просит найти место в тексте.'),
    'word': ('Перевод слова по нажатию', 'Незнакомое слово — нажал и увидел перевод, даже без интернета. Слово уходит в личный словарь.'),
    'twin': ('Тот же текст на русском', 'Каждый текст есть на двух языках — с теми же доказательствами и ответами.'),
    'math': ('Математика — тот же принцип', 'Сначала покажи в условии нужные данные, потом считай. 50 задач, 5 тем.'),
    'ai': ('С интернетом — ИИ-помощник', 'Наводит на ход решения, но не говорит ответ: до конца вопроса модель не видит ключ.'),
    'teacher': ('Учитель видит класс', 'Результаты собираются по QR без интернета: навыки, кто отвечает верно без доказательства, главная ловушка класса.'),
    'tomorrow': ('Что делать завтра', 'Готовый приём на 10 минут и мини-лист для печати — под ошибку, которую делает весь класс.'),
    'dict': ('Словарь с повторением', 'Слова из прочитанных текстов возвращаются карточками «помню / не помню».'),
}
marks = [m for m in M['marks'] if m[0] in CAP]
end_t = dict(M['marks'])['end']
segs = []
for i, (k, t) in enumerate(marks):
    t1 = marks[i + 1][1] if i + 1 < len(marks) else end_t + 0.6
    segs.append((k, t, t1))
TOTAL = M['duration'] + END_HOLD

FONT = "font-family: system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', 'Helvetica Neue', Arial, sans-serif;"
BG = f"""<html><body style="margin:0;width:1920px;height:1080px;background:#f7f2e8;{FONT}">
<div style="position:absolute;left:{PX-14}px;top:{PY-14}px;width:{PW+28}px;height:{PH+28}px;border-radius:58px;box-shadow:0 40px 80px -30px rgba(29,42,41,.55)"></div>
<div style="position:absolute;left:860px;top:70px;display:flex;align-items:center;gap:18px"><div style="width:64px;height:64px;border-radius:16px;background:#16524d;color:#f6cf6a;font-size:40px;font-weight:900;display:flex;align-items:center;justify-content:center">І</div>
<div><div style="font-size:40px;font-weight:800;color:#1d2a29">Ізден</div><div style="font-size:22px;color:#6b7672;letter-spacing:.12em;text-transform:uppercase">демо · izden.vercel.app</div></div></div>
<div style="position:absolute;left:860px;bottom:64px;font-size:24px;color:#6b7672">Запись с прода, телефон в режиме полёта · казахский интерфейс</div>
</body></html>"""
BEZEL = f"""<html><body style="margin:0;width:1920px;height:1080px;background:transparent">
<div style="position:absolute;left:{PX-14}px;top:{PY-14}px;width:{PW}px;height:{PH}px;border:14px solid #1d2a29;border-radius:58px"></div></body></html>"""


def cap_html(i, k):
    title, text = CAP[k]
    n = len(segs)
    dots = ''.join(f'<span style="width:{40 if j == i else 14}px;height:14px;border-radius:7px;background:{"#16524d" if j <= i else "#d9cfbc"};display:inline-block"></span>' for j in range(n))
    return f"""<html><body style="margin:0;width:960px;height:700px;background:transparent;{FONT}">
<div style="font-size:28px;font-weight:700;letter-spacing:.12em;color:#20756d;margin-bottom:18px">{i + 1:02d} / {n:02d}</div>
<div style="font-size:66px;font-weight:800;line-height:1.08;color:#1d2a29;letter-spacing:-.01em;margin-bottom:28px">{title}</div>
<div style="font-size:38px;line-height:1.38;color:#3b4a48;max-width:900px">{text}</div>
<div style="display:flex;gap:10px;margin-top:44px">{dots}</div></body></html>"""


END = f"""<html><body style="margin:0;width:1920px;height:1080px;background:#16524d;{FONT};display:flex;align-items:center;justify-content:center">
<div style="text-align:center;color:#fff"><div style="display:inline-flex;align-items:center;gap:28px;margin-bottom:36px"><div style="width:120px;height:120px;border-radius:30px;background:#f6cf6a;color:#16524d;font-size:76px;font-weight:900;display:flex;align-items:center;justify-content:center">І</div>
<div style="font-size:130px;font-weight:800;letter-spacing:-.03em">Ізден</div></div>
<div style="font-size:64px;font-weight:700;margin-bottom:26px">Сначала докажи — потом ответь</div>
<div style="font-size:36px;opacity:.85">Чтение и математика · казахский и русский · без интернета</div>
<div style="font-size:46px;font-weight:800;color:#f6cf6a;margin-top:40px">izden.vercel.app</div></div></body></html>"""

with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={'width': 1920, 'height': 1080})
    for name, html, transparent in (('bg', BG, False), ('bezel', BEZEL, True), ('end', END, False)):
        pg.set_content(html); pg.wait_for_timeout(150)
        pg.screenshot(path=str(D / f'{name}.png'), omit_background=transparent)
    pc = b.new_page(viewport={'width': 960, 'height': 700})
    for i, (k, _, _) in enumerate(segs):
        pc.set_content(cap_html(i, k)); pc.wait_for_timeout(100)
        pc.screenshot(path=str(D / f'cap_{i:02d}.png'), omit_background=True)
    b.close()

inputs = ['-loop', '1', '-t', f'{TOTAL:.2f}', '-i', str(D / 'bg.png'), '-i', str(D / 'phone.mp4'),
          '-loop', '1', '-t', f'{TOTAL:.2f}', '-i', str(D / 'bezel.png')]
for i in range(len(segs)):
    inputs += ['-loop', '1', '-t', f'{TOTAL:.2f}', '-i', str(D / f'cap_{i:02d}.png')]
inputs += ['-loop', '1', '-t', f'{TOTAL:.2f}', '-i', str(D / 'end.png')]
f = [f'[1:v]tpad=stop_mode=clone:stop_duration={END_HOLD},scale={PW}:{PH}:flags=lanczos,setsar=1[ph]',
     f'[0:v][ph]overlay={PX}:{PY}[v0]', '[v0][2:v]overlay=0:0[v1]']
cur = 'v1'
for i, (k, a, z) in enumerate(segs):
    idx = 3 + i
    fi = 0.3 if i else 0.0
    f.append(f'[{idx}:v]format=rgba,fade=in:st={max(0, a - 0.05):.2f}:d={fi or 0.01}:alpha=1,fade=out:st={z - 0.3:.2f}:d=0.3:alpha=1[c{i}]')
    f.append(f'[{cur}][c{i}]overlay=860:200[w{i}]')
    cur = f'w{i}'
e = 3 + len(segs)
f.append(f'[{e}:v]format=rgba,fade=in:st={end_t + 0.6:.2f}:d=0.6:alpha=1[ec]')
f.append(f'[{cur}][ec]overlay=0:0,format=yuv420p[out]')
out = ROOT / 'demo.mp4'
subprocess.run(['ffmpeg', '-y', '-v', 'error', *inputs, '-filter_complex', ';'.join(f), '-map', '[out]', '-t', f'{TOTAL:.2f}',
                '-r', '30', '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', str(out)], check=True)
print(out, round(out.stat().st_size / 1e6, 1), 'MB', round(TOTAL, 1), 's')
