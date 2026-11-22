#!/usr/bin/env python3
"""Render the overlay in headless Chromium and check that it really drew content.

Used by CI; also handy locally:  python3 scripts/smoke_test.py
Saves screenshots to logs/ (one per scene and theme).
"""
import json
import pathlib
import shutil
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server  # noqa: E402

LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
DATA = ROOT / "web" / "data.json"


def main() -> int:
    had_data = DATA.exists()
    if not had_data:
        shutil.copy(ROOT / "web" / "demo.json", DATA)   # same shape the agent writes
    srv = server.make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    failures = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            panels = json.loads(DATA.read_text())["panels"]

            page.goto(f"{base}/index.html?rotate=600")
            page.wait_for_selector("#scene li, #scene .card, #scene .big p", timeout=10000)
            if not page.inner_text("#title").strip():
                failures.append("title is empty")
            for i, pnl in enumerate(panels):
                page.goto(f"{base}/index.html?scene={pnl['id']}")
                page.wait_for_selector("#scene > *", timeout=10000)
                page.wait_for_timeout(1500)
                if not page.inner_text("#scene").strip():
                    failures.append(f"scene {pnl['id']} rendered empty")
                page.screenshot(path=str(LOGS / f"overlay-{i}-{pnl['type']}.png"))

            for theme in ("daylight", "neon", "terminal"):
                page.goto(f"{base}/index.html?theme={theme}")
                page.wait_for_timeout(800)
                if page.evaluate("document.getElementById('stage').dataset.theme") != theme:
                    failures.append(f"theme {theme} not applied")
                page.screenshot(path=str(LOGS / f"overlay-theme-{theme}.png"))

            # banner via control API
            page.goto(f"{base}/index.html")
            page.request.post(f"{base}/api/state", data=json.dumps({"message": "Smoke banner", "message_seconds": 30}),
                              headers={"Content-Type": "application/json"})
            page.wait_for_timeout(2200)
            if "show" not in (page.get_attribute("#banner", "class") or ""):
                failures.append("banner did not show")
            page.request.post(f"{base}/api/state", data=json.dumps({"message": ""}),
                              headers={"Content-Type": "application/json"})

            # 1080p scaling: the stage must fill the viewport width
            page.set_viewport_size({"width": 1920, "height": 1080})
            page.wait_for_timeout(300)
            width = page.evaluate("document.getElementById('stage').getBoundingClientRect().width")
            if abs(width - 1920) > 2:
                failures.append(f"stage did not scale to 1080p (width {width})")
            failures += [f"JS error: {e}" for e in errors]
            browser.close()
    finally:
        srv.shutdown()
        if not had_data:
            DATA.unlink(missing_ok=True)
    if failures:
        print("FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("smoke test OK — screenshots in logs/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
