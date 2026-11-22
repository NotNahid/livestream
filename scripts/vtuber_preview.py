#!/usr/bin/env python3
"""Render the VTuber page in headless Chromium and save screenshots to output/.

    python3 scripts/vtuber_preview.py

Saves output/emotion_<name>.png for every emotion and output/talking.png (a real line being spoken,
mouth + subtitles in sync). Exits non-zero if the face did not draw or the mouth never moved.
"""
import pathlib
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server  # noqa: E402
from vtuber import __main__ as director  # noqa: E402
from vtuber import face  # noqa: E402

OUT = ROOT / "output"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    director.write_assets()
    srv = server.make_server("127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/vtuber.html?mute=1&blink=0"
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base)
        page.wait_for_selector("#vt-face", timeout=10000)
        for name, e in face.EMOTIONS.items():
            page.evaluate(
                "([n, m]) => { const s = document.getElementById('vt-face'); s.dataset.emo = n; s.dataset.mouth = m; }",
                [name, e["rest"]],
            )
            page.wait_for_timeout(350)
            page.screenshot(path=str(OUT / f"emotion_{name}.png"))
        # a real line, end to end: director -> now.json -> page
        dur = director.speak(1, "happy", "Hello hello! Is this thing on? [laugh]", "Pyon", 150.0)
        page.wait_for_timeout(1200)
        seen = set()
        for _ in range(12):
            seen.add(page.evaluate("document.getElementById('vt-face').dataset.mouth"))
            page.wait_for_timeout(120)
        page.screenshot(path=str(OUT / "talking.png"))
        words_on = page.evaluate("document.querySelectorAll('#line span.on').length")
        page.wait_for_timeout(int(max(0, dur - 1.5) * 1000) + 2500)
        subs_hidden = page.evaluate("!document.getElementById('subs').classList.contains('show')")
        browser.close()
    if errors:
        problems.append(f"page errors: {errors}")
    if len(seen) < 3:
        problems.append(f"mouth barely moved: {seen}")
    if words_on < 2:
        problems.append("subtitles did not light up")
    if not subs_hidden:
        problems.append("subtitles did not hide after the line")
    print("mouth shapes seen:", sorted(seen), "| words lit:", words_on, "| subs hid:", subs_hidden)
    print("PROBLEMS: " + "; ".join(problems) if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
