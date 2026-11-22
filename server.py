#!/usr/bin/env python3
"""Tiny web server: serves web/ and a small control API (standard library only).

    GET  /api/health   -> {"ok": true}
    GET  /api/state    -> live overrides (banner message, pinned scene, pause, theme)
    POST /api/state    -> change them (JSON body; needs the admin token, see below)
    GET  /api/status   -> stream health: uptime, ffmpeg fps/bitrate, data age

Security:
  * Binds to 127.0.0.1 by default.
  * POST needs header `X-Admin-Token: $ADMIN_TOKEN` when ADMIN_TOKEN is set; without a token
    only loopback clients may POST. Binding to a non-loopback address REQUIRES ADMIN_TOKEN.
"""
from __future__ import annotations

import hmac
import json
import os
import pathlib
import re
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
WEB = ROOT / "web"
LOGS = ROOT / "logs"
THEMES = ("midnight", "daylight", "neon", "terminal")
MAX_BODY = 8 * 1024
STARTED = time.time()

_lock = threading.Lock()
STATE: dict = {"message": "", "message_until": 0, "scene": "", "paused": False, "theme": "", "rev": 0}


def sanitize_state(patch: dict) -> dict:
    """Validate a state patch from the control panel; raises ValueError on bad input."""
    out: dict = {}
    if "message" in patch:
        msg = str(patch["message"]).strip()
        if len(msg) > 200:
            raise ValueError("message too long (max 200 chars)")
        out["message"] = msg
        seconds = int(patch.get("message_seconds", 20))
        out["message_until"] = int(time.time()) + max(1, min(seconds, 3600)) if msg else 0
    if "scene" in patch:
        scene = str(patch["scene"])
        if scene and not re.fullmatch(r"p\d{1,3}", scene):
            raise ValueError("bad scene id")
        out["scene"] = scene
    if "paused" in patch:
        out["paused"] = bool(patch["paused"])
    if "theme" in patch:
        theme = str(patch["theme"])
        if theme and theme not in THEMES:
            raise ValueError(f"theme must be one of {THEMES}")
        out["theme"] = theme
    return out


def apply_state(patch: dict) -> dict:
    clean = sanitize_state(patch)
    with _lock:
        STATE.update(clean)
        STATE["rev"] += 1
        return dict(STATE)


def read_state() -> dict:
    with _lock:
        s = dict(STATE)
    if s["message_until"] and s["message_until"] < time.time():
        s["message"], s["message_until"] = "", 0
    return s


FFMPEG_RE = re.compile(r"frame=\s*(\d+)\s+fps=\s*([\d.]+).*?bitrate=\s*([\d.]+)kbits/s.*?speed=\s*([\d.]+)x")


def ffmpeg_stats() -> dict:
    """Parse the most recent stats line from logs/ffmpeg.log."""
    log = LOGS / "ffmpeg.log"
    try:
        with open(log, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 4096))
            tail = f.read().decode("utf-8", "replace")
        age = time.time() - log.stat().st_mtime
    except OSError:
        return {"running": False}
    for line in reversed(tail.replace("\r", "\n").splitlines()):
        m = FFMPEG_RE.search(line)
        if m:
            return {"running": age < 30, "frames": int(m[1]), "fps": float(m[2]),
                    "bitrate_kbps": float(m[3]), "speed": float(m[4]), "log_age_s": round(age, 1)}
    return {"running": False, "log_age_s": round(age, 1)}


def status() -> dict:
    data_age = None
    panels = 0
    try:
        p = WEB / "data.json"
        data_age = round(time.time() - p.stat().st_mtime, 1)
        panels = len(json.loads(p.read_text(encoding="utf-8")).get("panels", []))
    except (OSError, ValueError):
        pass
    return {"server_uptime_s": int(time.time() - STARTED), "data_age_s": data_age, "panels": panels,
            "ffmpeg": ffmpeg_stats(), "state": read_state()}


class Handler(SimpleHTTPRequestHandler):
    server_version = "livestream-proto"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    # ---- plumbing
    def log_message(self, fmt, *args):  # quiet: ffmpeg/agent logs matter more
        if os.environ.get("HTTP_VERBOSE"):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def list_directory(self, path):  # no directory listings
        self.send_error(HTTPStatus.NOT_FOUND)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self) -> bool:
        token = os.environ.get("ADMIN_TOKEN", "")
        if token:
            return hmac.compare_digest(self.headers.get("X-Admin-Token", ""), token)
        return self.client_address[0] in ("127.0.0.1", "::1")

    # ---- routes
    def do_GET(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/health":
            return self._json({"ok": True})
        if route == "/api/state":
            return self._json(read_state())
        if route == "/api/status":
            return self._json(status())
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/state":
            return self._json({"error": "not found"}, 404)
        if not self._authorised():
            return self._json({"error": "unauthorised: send X-Admin-Token"}, 401)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BODY:
                raise ValueError("body must be 1-8192 bytes")
            patch = json.loads(self.rfile.read(length))
            if not isinstance(patch, dict):
                raise ValueError("body must be a JSON object")
            return self._json(apply_state(patch))
        except (ValueError, json.JSONDecodeError) as e:
            return self._json({"error": str(e)}, 400)


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("ADMIN_TOKEN"):
        raise SystemExit("Refusing to bind to a public address without ADMIN_TOKEN set.")
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    host = os.environ.get("BIND", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    srv = make_server(host, port)
    print(f"serving {WEB} on http://{host}:{port}  (control panel: /control.html)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
