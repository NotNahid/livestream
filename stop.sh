#!/usr/bin/env bash
# Stop the stream. Asks nicely first, then force-kills anything left (use if the terminal froze).
cd "$(dirname "$0")" || exit 1
if [ -f logs/run.pid ] && kill -0 "$(cat logs/run.pid)" 2>/dev/null; then
  kill "$(cat logs/run.pid)" 2>/dev/null
  for _ in 1 2 3 4 5 6; do kill -0 "$(cat logs/run.pid 2>/dev/null)" 2>/dev/null || break; sleep 1; done
fi
pkill -9 -f "bash.*run\.sh" 2>/dev/null
pkill -9 -f "server.py" 2>/dev/null
pkill -9 -f "agent.py" 2>/dev/null; pkill -9 -f -- "-m vtuber" 2>/dev/null; pkill -9 -f "browser.py" 2>/dev/null
pkill -9 -f chrome-live 2>/dev/null
pkill -9 -x ffmpeg 2>/dev/null; pkill -9 -x Xvfb 2>/dev/null
rm -f logs/run.pid
echo "Stopped."
