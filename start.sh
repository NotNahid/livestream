#!/usr/bin/env bash
# One command: installs what's missing, asks a few questions once, then streams.
cd "$(dirname "$0")" || exit 1
chmod +x ./*.sh

if [ ! -d .venv ] || ! command -v Xvfb >/dev/null 2>&1 || ! command -v pulseaudio >/dev/null 2>&1; then
  ./setup.sh || { echo "Setup failed"; exit 1; }
fi

# first run (or .env is still the template): ask questions
if [ ! -f .env ] || grep -q 'your_stream_key_here' .env; then
  echo
  echo "Where are you streaming?"
  echo "  1) Twitch   2) YouTube   3) Kick   4) Facebook   5) Other RTMP server   6) Just test (no key)"
  read -r -p "Choose 1-6 [1]: " P
  case "${P:-1}" in
    2) PLAT=youtube ;; 3) PLAT=kick ;; 4) PLAT=facebook ;; 5) PLAT=custom ;; 6) PLAT=dry ;; *) PLAT=twitch ;;
  esac
  if [ "$PLAT" = dry ]; then
    exec ./run.sh --dry-run
  fi
  K=""; U=""
  if [ "$PLAT" = kick ] || [ "$PLAT" = custom ]; then
    read -r -p "RTMP ingest URL (from your platform's dashboard): " U
  fi
  read -r -s -p "Paste your stream key (hidden): " K; echo
  case "$K$U" in *\'*|*\ *) echo "Key/URL must not contain spaces or quotes."; exit 1 ;; esac
  read -r -p "Minutes to stream, 0 = until stopped [10]: " M
  [[ "${M:-10}" =~ ^[0-9]+$ ]] || { echo "Minutes must be a number."; exit 1; }
  read -r -p "YouTube video link to play instead of the dashboard (Enter to skip): " V
  umask 077
  {
    echo "PLATFORM=$PLAT"
    echo "STREAM_KEY='$K'"
    [ -n "$U" ] && echo "RTMP_URL='$U'"
    echo "MINUTES=${M:-10}"
  } > .env
  if [ -n "$V" ]; then
    ID=$(python3 - "$V" <<'PY'
import re, sys
m = re.search(r'(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})', sys.argv[1])
print(m.group(1) if m else "")
PY
)
    if [ -n "$ID" ]; then
      echo "PAGE_URL='https://www.youtube.com/embed/$ID?autoplay=1&loop=1&playlist=$ID&controls=0'" >> .env
    else
      echo "Could not read a video ID from that link, using the dashboard."
    fi
  fi
  echo "Saved to .env (readable only by you)."
fi

exec ./run.sh
