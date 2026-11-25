"""Record the Izden demo from production with headless Playwright.

Student phone (kk, Aigerim, grade 8) -> flight mode -> trap -> "guessed? prove" -> QR;
teacher phone scans the QR through Chromium's fake camera -> demo class -> trap card -> print sheet.
Output: submission/build/rec/*.webm + marks.json (segment start/end in seconds of each video),
and phone screenshots in submission/build/shots/.
"""
import json, subprocess, time, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://izden.vercel.app/"
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
REC = BUILD / "rec"
SHOTS = BUILD / "shots"
FFMPEG = str(Path.home() / ".local/bin/ffmpeg")
for d in (REC, SHOTS):
    d.mkdir(parents=True, exist_ok=True)

import os
W, H = 390, 844
DSF = int(os.environ.get("DSF", "1"))  # video: 1 (Chromium screencast mixes 1x/2x frames at DSF 2); screenshots: run with DSF=2
marks = {}


class Clock:
    def __init__(self, name):
        self.name, self.t0 = name, time.monotonic()
        marks[name] = {}

    def mark(self, key):
        marks[self.name][key] = round(time.monotonic() - self.t0, 2)
        print(self.name, key, marks[self.name][key], flush=True)


def shot(page, name):
    page.screenshot(path=str(SHOTS / f"{name}.png"))


def slow_click(page, sel, pause=700):
    loc = page.locator(sel).first
    loc.scroll_into_view_if_needed()
    loc.hover()
    page.wait_for_timeout(250)
    loc.click()
    page.wait_for_timeout(pause)


def opt(page, letter_id):
    return f'#qpanel [data-opt="{letter_id}"]'


def ev(ref):
    return f'#reader [data-ev="{ref}"]'


def new_ctx(browser, name):
    ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=DSF,
                              is_mobile=True, has_touch=False, locale="kk-KZ",
                              record_video_dir=str(REC / name), record_video_size={"width": W * DSF, "height": H * DSF})
    return ctx


def student(p):
    browser = p.chromium.launch()
    ctx = new_ctx(browser, "student")
    page = ctx.new_page()
    c = Clock("student")
    page.goto(URL, wait_until="networkidle")
    page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null", timeout=20000)
    page.wait_for_selector("#net.ok", state="attached", timeout=20000)
    page.wait_for_timeout(1200)
    c.mark("online_home")
    shot(page, "s01_home_online")
    # flight mode
    ctx.set_offline(True)
    page.reload(wait_until="load")
    page.wait_for_selector("#net.off", state="attached", timeout=10000)
    page.wait_for_timeout(1500)
    c.mark("offline_home")
    shot(page, "s02_home_offline")
    # onboarding (kk)
    slow_click(page, '[data-pick="kk"]', 500)
    page.locator('#onb input[name="name"]').click()
    page.locator('#onb input[name="name"]').type("Айгерім", delay=90)
    page.select_option('#onb select[name="grade"]', "8")
    page.wait_for_timeout(500)
    shot(page, "s03_onboarding")
    slow_click(page, '#onb button[type="submit"]', 1500)
    page.wait_for_selector("#qpanel .stem")
    c.mark("q1_start")
    shot(page, "s04_q1")
    unit_id = page.evaluate("JSON.parse(localStorage.getItem('izden.session.kk') || localStorage.getItem('session.kk') || 'null')")
    print("session", unit_id)
    # Q1: tap row of bus 107, choose 107 -> found but wrong inference + trap
    slow_click(page, ev("b2:r4"), 900)
    slow_click(page, opt(page, "a"), 700)
    shot(page, "s05_q1_picked")
    slow_click(page, "#check", 400)
    page.wait_for_selector("#qpanel .trap")
    page.locator("#qpanel").scroll_into_view_if_needed()
    page.wait_for_timeout(3500)
    c.mark("q1_trap")
    shot(page, "s06_q1_trap")
    page.evaluate("window.scrollBy(0, 400)")
    page.wait_for_timeout(2500)
    shot(page, "s06b_q1_hint")
    slow_click(page, "#show-ev", 1800)
    shot(page, "s07_q1_highlight")
    slow_click(page, opt(page, "b"), 600)
    slow_click(page, "#check", 1200)
    page.locator("#qpanel .diag").scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    c.mark("q1_done")
    shot(page, "s08_q1_second_help")
    # Q2: tap a sentence not about trips, choose the correct option -> "guessed? prove"
    slow_click(page, "#next", 1200)
    c.mark("q2_start")
    slow_click(page, ev("b4:s3"), 700)
    slow_click(page, opt(page, "c"), 600)
    slow_click(page, "#check", 600)
    page.wait_for_selector("#qpanel.ph-prove")
    page.locator("#qpanel").scroll_into_view_if_needed()
    page.wait_for_timeout(3500)
    c.mark("q2_prove")
    shot(page, "s09_q2_prove")
    page.locator(ev("b3:r1")).scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    slow_click(page, ev("b3:r1"), 1200)
    page.locator("#qpanel .diag").scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    c.mark("q2_proved")
    shot(page, "s10_q2_proved")
    # rest of the unit: answer correctly with the first evidence ref
    bank = page.evaluate("fetch('data/bank.kk.json').then(r => r.json())")
    unit = next(u for u in bank["units"] if u["id"] == "kk-bus-01")
    for _ in range(6):
        if page.locator("#next").count() == 0:
            break
        last = "→" in page.locator("#next").inner_text()
        page.locator("#next").click()
        page.wait_for_timeout(500)
        if last:
            break
        stem = page.locator("#qpanel .stem").inner_text()
        q = next(q for q in unit["questions"] if q["stem"] == stem)
        ref = q["evidence"][0]
        if ":" not in ref:
            ref = page.evaluate(f"document.querySelector('#reader [data-ev^=\"{ref}:\"]').dataset.ev")
        page.locator(ev(ref)).click()
        page.wait_for_timeout(250)
        cid = next(o["id"] for o in q["options"] if o["correct"])
        page.locator(opt(page, cid)).click()
        page.locator("#check").click()
        page.wait_for_timeout(500)
    page.wait_for_selector("#next-unit")
    page.locator("#qpanel").scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    c.mark("unit_summary")
    shot(page, "s11_unit_summary")
    slow_click(page, "#next-unit", 1500)
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(2500)
    c.mark("next_unit_reason")
    shot(page, "s12_reason")
    slow_click(page, "#pass-btn", 2500)
    c.mark("passport")
    shot(page, "s13_passport")
    page.locator("#pass-dlg button").click()
    page.wait_for_timeout(400)
    # progress + QR
    page.goto(URL + "#/progress")
    page.wait_for_selector("#qr svg")
    page.wait_for_timeout(1500)
    c.mark("progress")
    shot(page, "s14_progress")
    page.locator("#share").scroll_into_view_if_needed()
    page.wait_for_timeout(3000)
    c.mark("qr")
    shot(page, "s15_qr")
    page.locator("#qr").screenshot(path=str(BUILD / "qr.png"))
    code = page.locator("#scode").inner_text()
    (BUILD / "short_code.txt").write_text(code)
    # Russian toggle
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(600)
    c.mark("ru_start")
    slow_click(page, '#lang-switch [data-lang="ru"]', 600)
    page.goto(URL + "#/practice")
    page.wait_for_selector("#qpanel .stem")
    page.wait_for_timeout(3000)
    c.mark("ru_practice")
    shot(page, "s16_ru_practice")
    c.mark("end")
    vid = page.video
    ctx.close()
    browser.close()
    return vid.path()


def make_camera_feed():
    # white 640x480 frame with the student's QR in the middle, as a webcam would see a phone screen
    y4m = BUILD / "qr.y4m"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", str(BUILD / "qr.png"),
                    "-vf", "scale=380:-1,pad=640:480:(ow-iw)/2:(oh-ih)/2:white", "-t", "4", "-r", "15",
                    "-pix_fmt", "yuv420p", str(y4m)], check=True)
    return y4m


def teacher(p, y4m):
    browser = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                      f"--use-file-for-fake-video-capture={y4m}"])
    ctx = new_ctx(browser, "teacher")
    ctx.grant_permissions(["camera"], origin=URL.rstrip("/"))
    page = ctx.new_page()
    c = Clock("teacher")
    page.goto(URL + "#/teacher", wait_until="networkidle")
    page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null", timeout=20000)
    ctx.set_offline(True)
    page.reload(wait_until="load")
    page.wait_for_selector("#scan")
    page.wait_for_timeout(1500)
    c.mark("teacher_home")
    shot(page, "t01_teacher")
    slow_click(page, "#scan", 300)
    try:
        page.wait_for_selector("#report table", timeout=15000)
        via = "camera"
    except Exception:
        via = "code"
    print("transfer via", via)
    page.wait_for_timeout(1800)
    c.mark("scanned")
    shot(page, "t02_scanned")
    if page.locator("#stop").is_visible():
        page.locator("#stop").click()
    if via == "code":
        page.locator("details.manual summary").click()
        page.fill('#codeform input[name="name"]', "Айгерім")
        page.locator('#codeform input[name="code"]').type((BUILD / "short_code.txt").read_text(), delay=40)
        page.locator('#codeform button[type="submit"]').click()
        page.wait_for_selector("#report table")
        page.wait_for_timeout(1500)
    page.locator("#report").scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    slow_click(page, "#demo", 1500)
    page.locator("#report").scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    c.mark("class_table")
    shot(page, "t03_class")
    page.locator(".class-traps").scroll_into_view_if_needed()
    page.wait_for_timeout(3000)
    c.mark("class_traps")
    shot(page, "t04_traps")
    slow_click(page, ".class-traps li.top a", 1500)
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(2500)
    c.mark("trap_card")
    shot(page, "t05_trapcard")
    page.evaluate("window.scrollBy({top: 500, behavior: 'smooth'})")
    page.wait_for_timeout(2500)
    shot(page, "t06_trapcard_plan")
    page.locator("#paper").scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    c.mark("mini_sheet")
    shot(page, "t07_minisheet")
    page.goto(URL + "#/print")
    page.wait_for_selector("#paper .sheet-unit")
    page.wait_for_timeout(1500)
    c.mark("print")
    shot(page, "t08_print")
    page.locator("#paper .sheet-answers").scroll_into_view_if_needed()
    page.wait_for_timeout(2000)
    shot(page, "t09_answers")
    c.mark("end")
    vid = page.video
    ctx.close()
    browser.close()
    return vid.path(), via


def desktop(p):
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle")
    page.evaluate("""() => { localStorage.clear(); }""")
    page.reload(wait_until="networkidle")
    page.locator('[data-pick="kk"]').click()
    page.fill('#onb input[name="name"]', "Айгерім")
    page.locator('#onb button[type="submit"]').click()
    page.wait_for_selector("#qpanel .stem")
    page.locator('#reader [data-ev="b4:s3"]').click()
    page.locator('#qpanel [data-opt="b"]').click()
    page.locator('#check').click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(SHOTS / "d01_practice_desktop.png"))
    page.goto(URL + "#/teacher")
    page.wait_for_selector("#demo")
    page.locator("#demo").click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(SHOTS / "d02_teacher_desktop.png"), full_page=True)
    browser.close()


if __name__ == "__main__":
    with sync_playwright() as p:
        s_vid = student(p)
        y4m = make_camera_feed()
        t_vid, via = teacher(p, y4m)
        desktop(p)
    marks["files"] = {"student": str(s_vid), "teacher": str(t_vid), "transfer": via}
    (BUILD / "marks.json").write_text(json.dumps(marks, ensure_ascii=False, indent=1))
    print(json.dumps(marks, ensure_ascii=False, indent=1))
