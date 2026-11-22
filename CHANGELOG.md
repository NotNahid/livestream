# Changelog

## 2.4.0
- Change: GitHub Pages landing page (`docs/index.html`) redesigned in an editorial style: warm off-black, uppercase tight type, animated grain, hover list with full-screen zooming posters, frosted-glass gooey navigation. Config builder logic unchanged.

## 2.3.0
- New: GitHub Pages landing page (`docs/index.html`) redesigned in an Apple / macOS style: frosted sticky menu bar, traffic-light window frames around the live demo and theme preview, SF system font stack, light and dark mode, reduced-motion support, responsive down to phones.
- New: "VTuber mode" feature card; live-control card text updated.
- Fix: README and site links now point at `NotNahid/livestream` (were `YOUR_USER` / bare github.com).

## 2.2.0
- New: **live page switch.** `/control.html` -> "On air now" puts the overlay, the VTuber, or any link (YouTube links work) on air without restarting the stream. `POST /api/state {"embed": ...}`.
- New: **live settings editor.** `/control.html` -> "Settings" edits title, timings, ticker and data sources and saves `config.json` (`GET/POST /api/config`, validated, admin-token protected). The data agent reloads within ~1 s.
- New: `start.sh` setup wizard now asks about the VTuber (and news reactions) and writes `VTUBER=1` for you.
- Change: `run.sh` always loads the overlay; with `VTUBER=1` the VTuber layer starts on air and can be switched off live.
- Tests: 43 (5 new: embed validation, config save).

## 2.1.0
- New: **VTuber mode** (`VTUBER=1`). A character drawn entirely by Python (`vtuber/face.py`, 8 emotions), a babble voice
  synthesised in pure Python (`vtuber/voice.py`, no downloads) and karaoke subtitles, all on `web/vtuber.html`.
- New: sound effects `[laugh] [gasp] [boing] [ahem] [sigh]`, plus your own WAV files via `assets/sounds/<name>.wav`.
- New: `python3 -m vtuber --news` makes her react to the headlines in `web/data.json`; `--say` renders a WAV to listen to.
- New: `scripts/vtuber_preview.py` (screenshots of every emotion + a real talking frame), unit tests, CI step.

## 2.0.0
- New: pluggable data sources (RSS/Atom, Reddit, GitHub, crypto, weather, text, file) configured in `config.json`.
- New: scene-rotating overlay with ticker, progress bar, 4 themes, auto-scaling to any resolution.
- New: control panel and API (banner, pin scene, pause, theme, live stream stats).
- New: `./doctor.sh`, `./run.sh --dry-run`, `--minutes`, platform presets, resolution/fps/bitrate settings.
- New: auto-reconnect with back-off, browser auto-restart, stream key masked in logs.
- New: Dockerfile + compose, Makefile, unit tests, browser smoke test, GitHub Actions CI/Pages/Release.
- Fix: mouse cursor no longer appears in the stream.

## 1.0.0
- Initial prototype: Xvfb + Chromium + FFmpeg with a Hacker News dashboard.
