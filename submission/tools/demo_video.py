"""Record the demo walkthrough on the production site (phone 390x844 @2x, Kazakh UI) with CDP screencast.
Writes build/demo/frames/*.jpg, build/demo/phone.mp4 (exact frame timing) and build/demo/marks.json (step start times).
Then tools/demo_compose.py puts the phone into a 1920x1080 frame with captions -> submission/demo.mp4."""
import asyncio, base64, json, re, subprocess, sys, time
from pathlib import Path
from playwright.async_api import async_playwright

SITE = next((a for a in sys.argv[1:] if a.startswith('http')), 'https://izden.vercel.app')
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/demo'
FR = OUT / 'frames'
DATA = ROOT.parent / 'data'

TOUCH = """(() => { addEventListener('pointerdown', e => { const r = document.createElement('div');
  r.style.cssText = `position:fixed;left:${e.clientX-22}px;top:${e.clientY-22}px;width:44px;height:44px;border-radius:50%;background:rgba(242,179,61,.55);border:3px solid #f2b33d;z-index:99999;pointer-events:none;transition:transform .45s ease-out,opacity .45s ease-out`;
  document.documentElement.appendChild(r); requestAnimationFrame(() => { r.style.transform = 'scale(1.9)'; r.style.opacity = '0'; }); setTimeout(() => r.remove(), 520); }, true); })();"""


class Rec:
    def __init__(self, page):
        self.page, self.frames, self.marks = page, [], []

    async def start(self):
        FR.mkdir(parents=True, exist_ok=True)
        for f in FR.glob('*.jpg'):
            f.unlink()
        self.cdp = await self.page.context.new_cdp_session(self.page)
        async def on_frame(p):
            f = FR / f'{len(self.frames):05d}.jpg'
            f.write_bytes(base64.b64decode(p['data']))
            self.frames.append((time.monotonic(), f))
            try:
                await self.cdp.send('Page.screencastFrameAck', {'sessionId': p['sessionId']})
            except Exception:
                pass
        self.cdp.on('Page.screencastFrame', lambda p: asyncio.ensure_future(on_frame(p)))
        await self.cdp.send('Page.startScreencast', {'format': 'jpeg', 'quality': 92, 'maxWidth': 780, 'maxHeight': 1688})
        self.t0 = time.monotonic()

    def mark(self, key):
        self.marks.append([key, round(time.monotonic() - self.t0, 2)])
        print(f'{self.marks[-1][1]:6.2f}s  {key}')

    async def stop(self):
        await asyncio.sleep(0.6)
        await self.cdp.send('Page.stopScreencast')
        await asyncio.sleep(0.3)
        dur = time.monotonic() - self.t0
        fr = [(max(0, ts - self.t0), f) for ts, f in self.frames]
        lines = []
        for i, (t, f) in enumerate(fr):
            nxt = fr[i + 1][0] if i + 1 < len(fr) else dur
            d = max(0.001, nxt - t) + (t if i == 0 else 0)
            lines += [f"file '{f}'", f'duration {d:.4f}']
        lines.append(f"file '{fr[-1][1]}'")
        (OUT / 'frames.txt').write_text('\n'.join(lines) + '\n')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(OUT / 'frames.txt'),
                        '-vf', 'scale=780:1688:flags=lanczos,fps=30,format=yuv420p', '-c:v', 'libx264', '-crf', '16', '-preset', 'medium',
                        str(OUT / 'phone.mp4')], check=True)
        (OUT / 'marks.json').write_text(json.dumps({'duration': round(dur, 2), 'marks': self.marks}, ensure_ascii=False, indent=1))
        print('frames', len(self.frames), 'duration', round(dur, 1))


async def tap(page, sel, nth=0, pause=0.5):
    loc = page.locator(sel).nth(nth)
    await loc.scroll_into_view_if_needed()
    box = await loc.bounding_box()
    await page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    await page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    await asyncio.sleep(pause)


async def scroll_to(page, sel, top=70, ms=700):
    await page.evaluate("""([s, top, ms]) => new Promise(res => { const e = document.querySelector(s); if (!e) return res();
      const y0 = scrollY, y1 = Math.max(0, e.getBoundingClientRect().top + scrollY - top), t0 = performance.now();
      const st = now => { const k = Math.min(1, (now - t0) / ms), q = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2; scrollTo(0, y0 + (y1 - y0) * q); k < 1 ? requestAnimationFrame(st) : res(); };
      requestAnimationFrame(st); })""", [sel, top, ms])
    await asyncio.sleep(0.25)


async def panel_scroll(page, y, ms=600):
    await page.evaluate("""([y, ms]) => new Promise(res => { const p = document.querySelector('#qpanel'); if (!p) return res();
      const y0 = p.scrollTop, t0 = performance.now();
      const st = now => { const k = Math.min(1, (now - t0) / ms); p.scrollTop = y0 + (y - y0) * k; k < 1 ? requestAnimationFrame(st) : res(); }; requestAnimationFrame(st); })""", [y, ms])


async def tap_word(page, sel, word):
    await scroll_to(page, sel, top=90)
    xy = await page.evaluate("""([s, w]) => { const el = document.querySelector(s); const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let n;
      while ((n = tw.nextNode()) && n.textContent.indexOf(w) < 0); if (!n) return null; const i = n.textContent.indexOf(w);
      const r = document.createRange(); r.setStart(n, i + 2); r.setEnd(n, i + 3); const b = r.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; }""", [sel, word])
    await page.mouse.move(*xy)
    await page.mouse.click(*xy)


def math_unit(lang, grade, topic):
    units = [u for u in json.loads((DATA / f'math.{lang}.json').read_text())['units'] if u['grade'] == grade and u['topic'] == topic]
    num = lambda u: int(re.search(r'(\d+)$', u['id']).group(1))
    return sorted(units, key=lambda u: (num(u), u['id']))[0]


async def main():
    mu = math_unit('kk', 8, 'percent')
    mq = mu['questions'][0]
    m_wrong = next(o for o in mq['options'] if not o['correct'])
    print('maths unit', mu['id'], mu['title'], '| evidence', mq['evidence'])
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, locale='kk-KZ', has_touch=False)
        await ctx.add_init_script(TOUCH)
        page = await ctx.new_page()
        await page.goto(SITE + '/')
        await page.evaluate("""() => { localStorage.clear(); localStorage.setItem('izden.theme', '"light"');
          localStorage.setItem('izden.words', JSON.stringify([{lang:'ru',w:'райцентр',lemma:'райцентр',tr:'аудан орталығы',ctx:'Из села Акбулак в райцентр и обратно ходит рейсовый автобус.',box:1,due:0,added:1}])); }""")
        await page.reload()
        await page.evaluate("navigator.serviceWorker.ready")
        await asyncio.sleep(2.5)                      # let the service worker cache everything
        await ctx.set_offline(True)                   # airplane mode
        await page.reload()
        await page.wait_for_selector('#onb')
        await asyncio.sleep(1.0)
        r = Rec(page); await r.start()

        # 1. offline + onboarding
        r.mark('offline'); await asyncio.sleep(2.2)
        await tap(page, '[data-lang="kk"]', pause=0.8)
        await tap(page, '#onb input[name=name]', pause=0.2)
        await page.keyboard.type('Айгерім', delay=90)
        await asyncio.sleep(0.4)
        await tap(page, '#onb button[type=submit]', pause=1.4)

        # 2. evidence first: Q1 bus timetable, tap row 107, answer 107
        r.mark('evidence')
        await scroll_to(page, 'tr[data-ev="b2:r4"]', top=150)
        await asyncio.sleep(1.2)
        await tap(page, 'tr[data-ev="b2:r4"]', pause=1.0)
        await tap(page, '#qpanel [data-opt="a"]', pause=0.7)
        await tap(page, '#check', pause=0.4)
        r.mark('trap')
        await panel_scroll(page, 0); await asyncio.sleep(2.6)
        await panel_scroll(page, 260); await asyncio.sleep(1.8)
        await tap(page, '#show-ev', pause=1.2)
        await tap(page, '#qpanel [data-opt="b"]', pause=0.6)
        await tap(page, '#check', pause=1.6)

        # 3. guessed? prove it: Q2
        await tap(page, '#next', pause=1.0)
        r.mark('prove')
        await scroll_to(page, '[data-ev="b4:s1"]', top=110)
        await tap(page, '[data-ev="b4:s1"]', pause=0.8)
        await tap(page, '#qpanel [data-opt="c"]', pause=0.6)
        await tap(page, '#check', pause=2.4)
        await scroll_to(page, 'tr[data-ev="b3:r1"]', top=130)
        await tap(page, 'tr[data-ev="b3:r1"]', pause=2.4)

        # 4. word translation + same text in Russian
        await scroll_to(page, '#xlate-btn', top=80)
        r.mark('word')
        await tap(page, '#xlate-btn', pause=0.9)
        await tap_word(page, '[data-ev="b4:s1"]', 'жеңілдікпен')
        await page.wait_for_selector('.wsheet .w-tr')
        await asyncio.sleep(1.8)
        await tap(page, '.wsheet [data-w="save"]', pause=1.6)   # the sheet closes by itself after saving
        await scroll_to(page, '#twin-btn', top=80)
        r.mark('twin')
        await tap(page, '#twin-btn', pause=2.2)
        await page.evaluate("() => { const d = document.getElementById('twin-dlg'); d.scrollTo({top: 260, behavior: 'smooth'}); }")
        await asyncio.sleep(1.6)
        await tap(page, '#twin-dlg .w-x', pause=0.5)
        await tap(page, '#xlate-btn', pause=0.6)

        # 5. maths: same principle
        await page.evaluate("localStorage.setItem('izden.mtopic', '\"percent\"')")
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})"); await asyncio.sleep(0.7)
        r.mark('math')
        await tap(page, '.practice [data-subj="math"]', pause=1.6)
        ev = mq['evidence'][0]
        await scroll_to(page, f'[data-ev="{ev}"]', top=150)
        await asyncio.sleep(0.8)
        await tap(page, f'[data-ev="{ev}"]', pause=0.8)
        await tap(page, f'#qpanel [data-opt="{m_wrong["id"]}"]', pause=0.6)
        await tap(page, '#check', pause=2.2)

        # 6. online: AI helper does not give the answer
        await ctx.set_offline(False)
        await page.evaluate("dispatchEvent(new Event('online'))")
        await asyncio.sleep(0.4)
        await page.evaluate("document.querySelector('#ai-open').scrollIntoView({block: 'center'})")
        r.mark('ai')
        await tap(page, '#ai-open', pause=0.8)
        await tap(page, '[data-ask]', nth=1, pause=0.3)
        await page.wait_for_selector('.ai-assistant', timeout=40000)
        await page.evaluate("[...document.querySelectorAll('.ai-msg')].pop().scrollIntoView({block: 'center', behavior: 'smooth'})")
        await asyncio.sleep(4.2)
        await ctx.set_offline(True)
        await page.evaluate("dispatchEvent(new Event('offline'))")

        # 7. teacher: class picture and what to do tomorrow
        await page.evaluate("location.hash = '#/teacher'"); await asyncio.sleep(1.0)
        r.mark('teacher')
        await tap(page, '#demo', pause=1.6)
        await page.evaluate("window.scrollTo({top: document.querySelector('.class-table, table')?.getBoundingClientRect().top + scrollY - 70, behavior: 'smooth'})")
        await asyncio.sleep(2.4)
        await page.evaluate("document.querySelector('a[href^=\"#/trap/\"]').scrollIntoView({block: 'center', behavior: 'smooth'})")
        await asyncio.sleep(2.0)
        r.mark('tomorrow')
        await tap(page, 'a[href^="#/trap/"]', pause=2.2)
        await page.evaluate("window.scrollBy({top: 420, behavior: 'smooth'})")
        await asyncio.sleep(2.4)

        # 8. dictionary review
        await page.evaluate("location.hash = '#/dict'"); await asyncio.sleep(0.9)
        r.mark('dict')
        await asyncio.sleep(1.0)
        await tap(page, '#w-review', pause=1.2)
        await tap(page, '#w-show', pause=1.4)
        await tap(page, '#w-yes', pause=1.0)
        r.mark('end')
        await r.stop()
        await b.close()

asyncio.run(main())
