"""Screenshots of the features added for the final (maths, word translation, other-language text, dictionary, AI helper).
Phone 390x844 @2x, light theme, from production. Output: build/shots_new/*.png"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SITE = next((a for a in sys.argv[1:] if a.startswith('http')), 'https://izden.vercel.app')
OUT = Path(__file__).resolve().parents[1] / 'build/shots_new'
OUT.mkdir(parents=True, exist_ok=True)

TAP_WORD = """([sel, re, nth]) => { const els = [...document.querySelectorAll(sel)]; const rx = new RegExp(re, 'u');
  const el = els.find(e => rx.test(e.textContent)); if (!el) return 'no el';
  el.scrollIntoView({block: 'start'}); window.scrollBy(0, -120);
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let tn; while ((tn = walker.nextNode()) && !rx.test(tn.textContent));
  const m = rx.exec(tn.textContent); const r = document.createRange(); r.setStart(tn, m.index + 1); r.setEnd(tn, m.index + 2);
  const b = r.getBoundingClientRect(); const x = b.x + b.width / 2, y = b.y + b.height / 2;
  const hit = document.elementFromPoint(x, y); hit.dispatchEvent(new MouseEvent('click', {clientX: x, clientY: y, bubbles: true, cancelable: true})); return 'hit ' + hit.className + ' ' + m[0] + ' xl=' + document.querySelector('.practice').className; }"""


def ctx_page(b, ls):
    c = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, locale='ru-RU', service_workers='block')
    c.add_init_script('(() => { const d = %s; if (!sessionStorage.getItem("seeded")) { localStorage.clear(); for (const [k, v] of Object.entries(d)) localStorage.setItem("izden." + k, JSON.stringify(v)); sessionStorage.setItem("seeded", "1"); } })();' % json.dumps(ls))
    return c, c.new_page()


def shot(p, name):
    p.wait_for_timeout(500)
    p.screenshot(path=str(OUT / f'{name}.png'))
    print('shot', name)


with sync_playwright() as pw:
    b = pw.chromium.launch()
    base = {'theme': 'light', 'profile': {'name': 'Айгерим', 'grade': 8, 'lang': 'ru'}, 'lang': 'ru'}

    if '--skip-math' not in sys.argv:
        # 1. maths: topic money, evidence -> wrong answer -> trap; then the AI helper
        c, p = ctx_page(b, {**base, 'subject': 'math', 'mtopic': 'money'})
        p.goto(SITE + '/#/practice'); p.wait_for_selector('#reader .tap')
        shot(p, 'm0_math_task')
        q = p.evaluate("() => document.querySelector('#qpanel .stem').textContent")
        print('q:', q)
        # tap the first evidence row of the question key, then a wrong option
        p.evaluate("() => { const t = document.querySelector('#reader tr.tap') || document.querySelector('#reader .tap'); t.click(); }")
        p.wait_for_timeout(300)
        p.evaluate("""() => { const opts = [...document.querySelectorAll('#qpanel [role=radio]')]; opts[0].click(); }""")
        p.wait_for_timeout(200)
        p.click('#check')
        p.wait_for_timeout(600)
        p.evaluate("() => document.querySelector('#qpanel').scrollTo(0, 0)")
        shot(p, 'm1_math_trap')
        if p.query_selector('#ai-open'):
            p.click('#ai-open'); p.wait_for_timeout(300)
            p.click('[data-ask]')
            p.wait_for_selector('.ai-assistant', timeout=30000)
            p.evaluate("() => { const e = [...document.querySelectorAll('.ai-msg')].pop(); e.scrollIntoView({block: 'end'}); }")
            shot(p, 'm2_math_ai')
        c.close()

    # 2. word translation in a Kazakh text + the same text in Russian
    c, p = ctx_page(b, {**base, 'profile': {'name': 'Айгерім', 'grade': 8, 'lang': 'kk'}, 'lang': 'kk', 'subject': 'read', 'xlate': True})
    p.goto(SITE + '/#/practice'); p.wait_for_selector('#reader .tap')
    print(p.evaluate(TAP_WORD, ['#reader .sent', 'жеңілдік\\w*', 0]))
    p.wait_for_selector('.wsheet .w-tr', timeout=10000)
    shot(p, 'w1_word_kk')
    p.evaluate("() => document.querySelector('.wsheet [data-w=save]')?.click()")
    p.evaluate("() => document.querySelector('.wsheet [data-w=close]')?.click()")
    p.evaluate("() => window.scrollTo(0, 0)")
    p.click('#twin-btn'); p.wait_for_selector('#twin-dlg[open]')
    shot(p, 'w2_twin_ru')
    c.close()

    # 3. dictionary: list and a review card
    words = [
        {'lang': 'kk', 'w': 'жеңілдікпен', 'lemma': 'жеңілдік', 'tr': 'скидка, льгота', 'ctx': 'Оқушылар мен зейнеткерлер кәдімгі рейстерде жеңілдікпен жүреді: олар үшін билет 400 теңге тұрады.', 'box': 0, 'due': 0, 'added': 3},
        {'lang': 'kk', 'w': 'жайылымда', 'lemma': 'жайылым', 'tr': 'пастбище', 'ctx': 'Сиырлар ауылдың сыртындағы жайылымда жайылды.', 'box': 2, 'due': 0, 'added': 2},
        {'lang': 'ru', 'w': 'райцентр', 'lemma': 'райцентр', 'tr': 'аудан орталығы', 'ctx': 'Из села Акбулак в райцентр и обратно ходит рейсовый автобус.', 'box': 4, 'due': 9e12, 'added': 1},
    ]
    c, p = ctx_page(b, {**base, 'words': words})
    p.goto(SITE + '/#/dict'); p.wait_for_selector('.wlist')
    shot(p, 'd1_dict_list')
    p.click('#w-review'); p.wait_for_selector('#w-show'); p.click('#w-show')
    shot(p, 'd2_dict_card')
    c.close()
    b.close()
