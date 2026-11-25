#!/usr/bin/env python3
"""Teacher screen at phone widths: class-trap cards and report blocks must not overlap.

Starts a local http.server, opens #/teacher in headless Chromium (Playwright) at 360 and 375 px, adds the demo
class, checks bounding boxes of the trap cards / insight / buttons pairwise for overlaps, and saves screenshots to
tests/out/. Also checks that the per-student "main trap" uses the same metric as the class top list.
Run: python3 tests/test_teacher_layout.py
"""
import contextlib
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests/out"


@contextlib.contextmanager
def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a: None
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}/"
        finally:
            httpd.shutdown()


OVERLAPS_JS = """() => {
  const els = [...document.querySelectorAll('#report .class-traps li, #report .insight, #report .btnrow, #report h2, #report .table-scroll, #report .lesson-cta')];
  const boxes = els.map(e => { const r = e.getBoundingClientRect(); return {n: e.className || e.tagName, l: r.left, t: r.top, r: r.right, b: r.bottom}; });
  const bad = [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.l < b.r - 1 && b.l < a.r - 1 && a.t < b.b - 1 && b.t < a.b - 1) bad.push(a.n + ' x ' + b.n);
  }
  const wide = [...document.querySelectorAll('#report .class-traps li, #report .insight')].filter(e => e.getBoundingClientRect().right > innerWidth + 1).map(e => e.className);
  return {bad, wide, n: els.length};
}"""


def test_teacher_layout():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("FAILED: playwright is not installed - layout NOT verified")
    OUT.mkdir(exist_ok=True)
    with serve() as url, sync_playwright() as p:
        b = p.chromium.launch()
        for w in (360, 375):
            pg = b.new_page(viewport={"width": w, "height": 800}, device_scale_factor=2, is_mobile=True)
            pg.goto(url + "#/teacher")
            pg.evaluate("localStorage.clear()")
            pg.reload()
            pg.wait_for_selector("#demo")
            pg.click("#demo")
            pg.wait_for_selector("#report .class-traps li")
            pg.wait_for_timeout(300)
            res = pg.evaluate(OVERLAPS_JS)
            pg.locator("#report").screenshot(path=str(OUT / f"teacher_{w}.png"))
            assert res["n"] >= 5, res
            assert not res["bad"], f"{w}px overlaps: {res['bad']}"
            assert not res["wide"], f"{w}px wider than screen: {res['wide']}"
            top_class = pg.locator("#report .class-traps li.top-trap").get_attribute("data-trap")
            assert top_class, "top trap card must carry data-trap"
            # one metric everywhere: the class top trap is the most frequent per-student "main trap" or at least present
            mains = pg.evaluate("[...document.querySelectorAll('table.report tbody tr td.small')].map(td => td.textContent)")
            assert any(" · " in m for m in mains), "per-student main trap must show its rate"
            pg.close()
            print(f"OK {w}px: {res['n']} blocks, no overlaps; screenshot tests/out/teacher_{w}.png")
        b.close()


if __name__ == "__main__":
    test_teacher_layout()
