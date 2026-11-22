#!/usr/bin/env bash
# Start everything (virtual screen, audio, web server, data agent, browser) and stream with FFmpeg.
#
#   ./run.sh                 stream using .env
#   ./run.sh --dry-run       no stream key needed: records logs/dry-run.mkv instead (test your layout)
#   ./run.sh --minutes 30    override MINUTES for this run (0 = until stopped)
#   ./run.sh --help
#
# Every setting lives in .env (see .env.example).
cd "$(dirname "$0")" || exit 1
mkdir -p logs

DRY=0; MIN_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --minutes) MIN_OVERRIDE="${2:?--minutes needs a number}"; shift ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)"; exit 2 ;;
  esac
  shift
done

if [ -f .env ]; then set -a; . ./.env; set +a; fi

# ---------- settings (all overridable in .env) ----------
PLATFORM="${PLATFORM:-twitch}"
case "$PLATFORM" in
  twitch)   PRESET_URL="rtmp://live.twitch.tv/app" ;;
  youtube)  PRESET_URL="rtmp://a.rtmp.youtube.com/live2" ;;
  facebook) PRESET_URL="rtmps://live-api-s.facebook.com:443/rtmp/" ;;
  kick|custom) PRESET_URL="" ;;
  *) echo "Unknown PLATFORM '$PLATFORM' (twitch, youtube, facebook, kick, custom)"; exit 2 ;;
esac
RTMP="${RTMP_URL:-$PRESET_URL}"
KEY="${STREAM_KEY:-}"
MINUTES="${MIN_OVERRIDE:-${MINUTES:-10}}"
RESOLUTION="${RESOLUTION:-1280x720}"
WIDTH="${RESOLUTION%x*}"; HEIGHT="${RESOLUTION#*x}"
FPS="${FPS:-30}"
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
AUDIO_BITRATE="${AUDIO_BITRATE:-128k}"
PRESET="${X264_PRESET:-veryfast}"
AUTO_RESTART="${AUTO_RESTART:-1}"
PORT="${PORT:-8080}"
export WIDTH HEIGHT PORT

[[ "$WIDTH" =~ ^[0-9]+$ && "$HEIGHT" =~ ^[0-9]+$ ]] || { echo "RESOLUTION must look like 1280x720"; exit 2; }
[[ "$MINUTES" =~ ^[0-9]+$ ]] || { echo "MINUTES must be a whole number (0 = no limit)"; exit 2; }
if [ "$DRY" = 0 ]; then
  [ -n "$KEY" ] && [ "$KEY" != "your_stream_key_here" ] || { echo "Set STREAM_KEY in .env (or try ./run.sh --dry-run)"; exit 1; }
  [ -n "$RTMP" ] || { echo "Set RTMP_URL in .env (required for PLATFORM=$PLATFORM)"; exit 1; }
fi

# one instance at a time
if [ -f logs/run.pid ] && kill -0 "$(cat logs/run.pid)" 2>/dev/null; then
  echo "Already running (pid $(cat logs/run.pid)). Use ./stop.sh first."; exit 1
fi
echo $$ > logs/run.pid

# What to show FIRST. PAGE_URL in .env only sets the starting source: the browser always opens
# stage.html, which follows the source chosen live in the control panel (no restart needed).
# server.py turns a YouTube link into the player.html wrapper (direct embeds give Error 153).
START_SOURCE="${PAGE_URL:-}"
[ -z "$START_SOURCE" ] && [ "${VTUBER:-0}" = "1" ] && START_SOURCE="vtuber"   # VTUBER=1 starts on the VTuber stage
export START_SOURCE
export PAGE_URL="http://127.0.0.1:$PORT/stage.html"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
DNUM="${DISPLAY_NUM:-99}"
PIDS=()

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  echo; echo "Shutting down..."
  kill "${PIDS[@]}" 2>/dev/null
  pkill -f chrome-live 2>/dev/null
  sleep 1
  kill -9 "${PIDS[@]}" 2>/dev/null
  rm -f logs/run.pid "/tmp/.X${DNUM}-lock"
  exit "$rc"
}
trap cleanup EXIT INT TERM

# mask the stream key in anything we print
mask() {
  while IFS= read -r line; do
    if [ -n "$KEY" ]; then echo "${line//"$KEY"/***}"; else echo "$line"; fi
  done
}

# 0. clean leftovers from earlier crashed runs
pkill -f chrome-live 2>/dev/null
rm -f "/tmp/.X${DNUM}-lock" "/tmp/.X11-unix/X${DNUM}" 2>/dev/null

# 1. audio (set up before DISPLAY is exported so pulseaudio does not try X11)
AUDIO=(-f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100)
if [ "${SILENT_AUDIO:-0}" = "1" ]; then
  echo "Audio: silent (SILENT_AUDIO=1)"
elif command -v pulseaudio >/dev/null 2>&1; then
  pulseaudio --start --exit-idle-time=-1 >logs/pulse.log 2>&1
  sleep 1
  pactl list short sinks 2>/dev/null | grep -q vsink || pactl load-module module-null-sink sink_name=vsink >/dev/null 2>&1
  if pactl list short sinks 2>/dev/null | grep -q vsink; then
    pactl set-default-sink vsink
    export PULSE_SINK=vsink
    AUDIO=(-f pulse -thread_queue_size 1024 -i vsink.monitor)
    echo "Audio: virtual sink OK"
  else
    echo "Audio: pulse failed, using silence"
  fi
else
  echo "Audio: pulseaudio not installed, using silence"
fi

if [ "${VTUBER:-0}" = "1" ] && [[ "${AUDIO[*]}" == *anullsrc* ]]; then
  echo "WARNING: VTUBER=1 but the stream audio is silent, so viewers will only see subtitles (install pulseaudio, unset SILENT_AUDIO)"
fi

# 2. virtual screen
export DISPLAY=":$DNUM"
Xvfb ":$DNUM" -screen 0 "${WIDTH}x${HEIGHT}x24" -nolisten tcp -nocursor >logs/xvfb.log 2>&1 &
XPID=$!; PIDS+=("$XPID")
sleep 2
if ! kill -0 "$XPID" 2>/dev/null; then
  echo "ERROR: virtual screen (Xvfb) did not start:"; cat logs/xvfb.log; exit 1
fi
echo "Screen: Xvfb OK (${WIDTH}x${HEIGHT})"

# 3. web server + data agent
$PY server.py >logs/http.log 2>&1 & PIDS+=($!)
$PY agent.py >logs/agent.log 2>&1 & PIDS+=($!)
if [ "${VTUBER:-0}" = "1" ]; then
  VT_ARGS=(); [ "${VTUBER_NEWS:-0}" = "1" ] && VT_ARGS+=(--news)
  $PY -m vtuber "${VT_ARGS[@]}" >logs/vtuber.log 2>&1 & PIDS+=($!)
  echo "VTuber: on (log: logs/vtuber.log)"
fi
for _ in 1 2 3 4 5 6 7 8 9 10; do
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 1
done
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 || { echo "ERROR: web server did not start:"; tail -10 logs/http.log; exit 1; }
echo "Server: http://127.0.0.1:$PORT  (control panel: /control.html)"
echo "Tip: change the video/page live (no restart) in the control panel -> \"Video source\". PAGE_URL in .env is only the starting source."
sleep 2

# 4. browser, restarted automatically if it crashes
( while true; do $PY browser.py >>logs/browser.log 2>&1; sleep 3; done ) &
PIDS+=($!)
sleep 6
pgrep -f chrome-live >/dev/null && echo "Browser: OK" || { echo "ERROR: browser did not start:"; tail -15 logs/browser.log; }

# 5. can we capture the screen?
if timeout 20 ffmpeg -nostdin -loglevel error -y -f x11grab -video_size "${WIDTH}x${HEIGHT}" -i ":$DNUM" -frames:v 1 logs/screen.png 2>logs/grab.log; then
  echo "Capture: OK (logs/screen.png)"
else
  echo "ERROR: screen capture failed:"; cat logs/grab.log; exit 1
fi

# 6. stream, reconnecting with back-off if the connection drops
GOP=$((FPS * 2))
BUF=$(( ${VIDEO_BITRATE%k} * 2 ))k
if [ "$DRY" = 1 ]; then OUTPUT=(-f matroska logs/dry-run.mkv); DEST="logs/dry-run.mkv (dry run)"
else OUTPUT=(-f flv "${RTMP%/}/${KEY}"); DEST="${PLATFORM} (${RTMP})"; fi

START=$(date +%s); ATTEMPT=0
[ "$MINUTES" -gt 0 ] && echo "Streaming to $DEST for ${MINUTES} min. Ctrl+C to stop." || echo "Streaming to $DEST until stopped. Ctrl+C to stop."
: > logs/ffmpeg.log
while true; do
  LIMIT=()
  if [ "$MINUTES" -gt 0 ]; then
    LEFT=$(( MINUTES * 60 - ($(date +%s) - START) ))
    [ "$LEFT" -le 0 ] && break
    LIMIT=(timeout "$LEFT")
  fi
  "${LIMIT[@]}" ffmpeg -nostdin -loglevel warning -stats -stats_period 5 \
    -thread_queue_size 1024 -f x11grab -framerate "$FPS" -video_size "${WIDTH}x${HEIGHT}" -i ":$DNUM" \
    "${AUDIO[@]}" \
    -c:v libx264 -preset "$PRESET" -tune zerolatency -pix_fmt yuv420p \
    -b:v "$VIDEO_BITRATE" -maxrate "$VIDEO_BITRATE" -bufsize "$BUF" -g "$GOP" \
    -c:a aac -b:a "$AUDIO_BITRATE" "${OUTPUT[@]}" 2>&1 | tr '\r' '\n' | mask | tee -a logs/ffmpeg.log
  RC=${PIPESTATUS[0]}
  [ "$RC" = 124 ] && break                       # time limit reached
  [ "$AUTO_RESTART" = 1 ] && [ "$DRY" = 0 ] || { echo "ffmpeg exited (code $RC)."; break; }
  ATTEMPT=$((ATTEMPT + 1)); WAIT=$((ATTEMPT * 5)); [ "$WAIT" -gt 60 ] && WAIT=60
  echo "Connection lost (code $RC). Reconnecting in ${WAIT}s (attempt $ATTEMPT)..."
  sleep "$WAIT"
done
echo "Stream ended."
