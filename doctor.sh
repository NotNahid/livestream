#!/usr/bin/env bash
# Preflight check: tells you exactly what is missing before you go live.
cd "$(dirname "$0")" || exit 1
BAD=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; BAD=1; }
have() { command -v "$1" >/dev/null 2>&1; }

echo "Tools"
for t in Xvfb ffmpeg python3 curl; do have "$t" && ok "$t" || bad "$t missing  → run ./setup.sh"; done
have pulseaudio && ok "pulseaudio (stream audio)" || warn "pulseaudio missing: stream will be silent (optional)"
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264 && ok "ffmpeg has libx264" || bad "ffmpeg lacks libx264"

echo "Browser"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
if $PY - <<'PY' 2>/dev/null
import os, sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    sys.exit(0 if os.path.exists(p.chromium.executable_path) else 1)
PY
then ok "Chromium (Playwright)"
elif have chromium || have chromium-browser || have google-chrome; then ok "system Chromium/Chrome"
else bad "no Chromium found  → run ./setup.sh"; fi

echo "Settings"
if [ -f .env ]; then set -a; . ./.env; set +a; ok ".env found"; else warn "no .env yet (fine for --dry-run). To go live: cp .env.example .env"; fi
if [ -z "${STREAM_KEY:-}" ] || [ "${STREAM_KEY:-}" = "your_stream_key_here" ]; then
  warn "STREAM_KEY not set (use ./run.sh --dry-run to test without it)"
else ok "STREAM_KEY set (${#STREAM_KEY} chars)"; fi
if [ "${VTUBER:-0}" = "1" ]; then
  $PY -m vtuber --build >/dev/null 2>&1 && ok "VTuber face builds" || bad "VTuber face failed to build (run: python3 -m vtuber --build)"
  have pulseaudio || warn "VTUBER=1 without pulseaudio: she will only have subtitles, no voice"
fi
[ -f config.json ] && ok "config.json found" || warn "no config.json: using config.example.json"
$PY -c "import json,sys;json.load(open('${CONFIG:-config.json}' if __import__('os').path.exists('${CONFIG:-config.json}') else 'config.example.json'))" 2>/dev/null \
  && ok "config is valid JSON" || bad "config is not valid JSON"

echo "Network"
case "${PLATFORM:-twitch}" in
  twitch) H=live.twitch.tv; P=1935 ;; youtube) H=a.rtmp.youtube.com; P=1935 ;;
  facebook) H=live-api-s.facebook.com; P=443 ;;
  *) H=$(echo "${RTMP_URL:-}" | sed -E 's#^[a-z]+://([^/:]+).*#\1#'); P=1935 ;;
esac
if [ -n "$H" ]; then
  if timeout 5 bash -c "exec 3<>/dev/tcp/$H/$P" 2>/dev/null; then ok "can reach $H:$P"
  else warn "cannot reach $H:$P from here (firewall? wrong RTMP_URL?)"; fi
fi
[ "$(df -Pk . | awk 'NR==2{print $4}')" -gt 500000 ] && ok "disk space" || warn "less than 500 MB free"

echo
[ "$BAD" = 0 ] && echo "All good. Run ./run.sh" || { echo "Fix the ✗ items above, then re-run ./doctor.sh"; exit 1; }
