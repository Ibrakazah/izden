"""Inline screenshots into slides.html, then render slides.pdf and per-slide PNGs (for the video).

Run after record_demo.py with DSF=2 (screenshots in build/shots_hi/).
"""
import base64, io, re
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def data_uri(rel):
    im = Image.open(BUILD / rel).convert("RGB")
    im = im.resize((600, round(im.height * 600 / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=86, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


src = (ROOT / "tools/slides_src.html").read_text()
html = re.sub(r"\{\{IMG:([^}]+)\}\}", lambda m: data_uri(m.group(1)), src)
out = ROOT / "slides.html"
out.write_text(html)
print("slides.html", round(out.stat().st_size / 1024), "KB")

png_dir = BUILD / "slides_png"
png_dir.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1920, "height": 1080})
    page.goto(out.as_uri())
    page.wait_for_timeout(500)
    page.pdf(path=str(ROOT / "slides.pdf"), width="1920px", height="1080px", print_background=True)
    n = page.locator(".slide").count()
    for variant in ("full", "video"):
        if variant == "video":  # placeholders are for the team; the draft video hides them
            page.add_style_tag(content=".ph{display:none!important}")
        for i in range(n):
            page.locator(".slide").nth(i).screenshot(path=str(png_dir / f"{variant}_{i + 1:02d}.png"))
    # overflow check: content must not spill beyond a slide
    over = page.evaluate("""() => [...document.querySelectorAll('.slide')].map((s, i) => {
        const r = s.getBoundingClientRect();
        const bad = [...s.querySelectorAll('*')].filter(e => { const q = e.getBoundingClientRect();
            return q.width && (q.right > r.right + 1 || q.bottom > r.bottom + 1); });
        return bad.length ? (i + 1) + ':' + bad.slice(0, 3).map(e => e.tagName + '.' + e.className).join(',') : null; }).filter(Boolean)""")
    print("slides:", n, "overflow:", over)
    b.close()
