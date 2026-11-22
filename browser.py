#!/usr/bin/env python3
"""Open PAGE_URL in Chromium (app + kiosk mode) on the virtual display and wait for it."""
import os
import shutil
import subprocess
import sys

URL = os.environ.get("PAGE_URL", "http://127.0.0.1:8080/index.html")
W = int(os.environ.get("WIDTH", "1280"))
H = int(os.environ.get("HEIGHT", "720"))


def find_chromium():
    # Playwright is only used to locate its bundled Chromium; we launch it ourselves
    # so we get a true kiosk window with no tabs or address bar.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        if exe and os.path.exists(exe):
            return exe
    except Exception as e:  # noqa: BLE001
        print("playwright lookup failed:", e, flush=True)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    return None


def main():
    exe = find_chromium()
    if not exe:
        sys.exit("Chromium not found. Run ./setup.sh")
    proc = subprocess.Popen([
        exe, "--no-sandbox", "--disable-dev-shm-usage",
        f"--app={URL}", "--kiosk",
        f"--window-size={W},{H}", "--window-position=0,0",
        "--force-device-scale-factor=1", "--hide-scrollbars",
        "--user-data-dir=/tmp/chrome-live",
        "--no-first-run", "--no-default-browser-check",
        "--disable-infobars", "--noerrdialogs", "--disable-session-crashed-bubble",
        "--autoplay-policy=no-user-gesture-required",
    ])
    try:
        proc.wait()
    finally:
        proc.kill()


if __name__ == "__main__":
    main()
