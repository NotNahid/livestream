#!/usr/bin/env bash
# Install everything needed (Ubuntu/Debian). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
$SUDO apt-get update -y
$SUDO apt-get install -y xvfb ffmpeg python3-venv pulseaudio curl
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m playwright install-deps chromium
.venv/bin/python -m playwright install chromium
[ -f .env ] || cp .env.example .env
echo
echo "Setup done."
echo "  1. Edit .env and add your stream key   (or run ./run.sh --dry-run to test without one)"
echo "  2. Optional: cp config.example.json config.json   and choose your data sources"
echo "  3. ./run.sh"
