# Changelog

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
