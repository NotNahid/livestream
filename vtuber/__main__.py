#!/usr/bin/env python3
"""VTuber director: decides what the character says next and publishes it for the web page.

    python3 -m vtuber                    loop forever over vtuber/lines.txt
    python3 -m vtuber --news             riff on the headlines in web/data.json (falls back to the script)
    python3 -m vtuber --build            only (re)write the face + config, then exit
    python3 -m vtuber --say "hello" --emotion happy --out output/hello.wav     render one WAV to listen to

Each line is rendered to web/vtuber/audio/line_N.wav and announced in web/vtuber/now.json. The page
(web/vtuber.html) plays the audio, moves the mouth from the cues and shows karaoke subtitles.
Script format, one line each:   emotion | text with optional [laugh] tags      (# starts a comment)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import random
import sys
import time

from . import face, voice

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
VT = WEB / "vtuber"
AUDIO = VT / "audio"
DEFAULT_SCRIPT = pathlib.Path(__file__).resolve().parent / "lines.txt"
KEEP_AUDIO = 8

log = logging.getLogger("vtuber")


# --------------------------------------------------------------------------- script + news
def parse_script(text: str) -> list:
    """'happy | Hello!' -> [('happy', 'Hello!')]. Unknown emotions fall back to neutral."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        emo, sep, body = line.partition("|")
        if sep and emo.strip().lower() in face.EMOTIONS:
            out.append((emo.strip().lower(), body.strip()))
        else:
            out.append(("neutral", (body if sep else line).strip()))
    return [x for x in out if x[1]]


def load_script(path: pathlib.Path) -> list:
    return parse_script(path.read_text(encoding="utf-8"))


NEWS_OPEN = [
    ("happy", "Ooh, {panel}! My favourite part of the show."),
    ("smug", "Time for {panel}. I read it so you do not have to."),
    ("surprised", "Wait, we have {panel} now?!"),
]
NEWS_ITEM = [
    ("neutral", "Number {n}: {title}. {meta}"),
    ("surprised", "{title}?! {meta}"),
    ("smug", "{title}. Yes. I knew that already."),
    ("sad", "{title}. That is a lot of feelings for one headline."),
    ("panic", "{title}! Is that bad? That sounds bad. [gasp]"),
]


def news_lines(data: dict, rng: random.Random, per_panel: int = 2) -> list:
    """Make up a few reactions to the panels the data agent wrote (web/data.json)."""
    out = []
    for panel in data.get("panels", [])[:6]:
        items = panel.get("items") or []
        if not items:
            continue
        emo, tpl = rng.choice(NEWS_OPEN)
        out.append((emo, tpl.format(panel=panel.get("title", "the news"))))
        for n, it in enumerate(items[:per_panel], 1):
            emo, tpl = rng.choice(NEWS_ITEM)
            title = " ".join(str(it.get("title", "")).split())[:90]
            meta = " ".join(str(it.get("meta", "")).split())[:40]
            out.append((emo, " ".join(tpl.format(n=n, title=title, meta=meta).split())))
    return out


# --------------------------------------------------------------------------- publishing
def write_assets() -> None:
    VT.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)
    (VT / "face.svg").write_text(face.build_svg(), encoding="utf-8")
    (VT / "emotions.json").write_text(face.emotions_json(), encoding="utf-8")


def atomic_json(path: pathlib.Path, obj: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj), encoding="utf-8")
    os.replace(tmp, path)


def prune_audio() -> None:
    files = sorted(AUDIO.glob("line_*.wav"), key=lambda p: p.stat().st_mtime)
    for old in files[:-KEEP_AUDIO]:
        old.unlink(missing_ok=True)


def speak(seq: int, emotion: str, text: str, name: str, pitch: float) -> float:
    """Render + publish one line. Returns its duration in seconds."""
    r = voice.render_line(text, emotion, base_pitch=pitch, seed=seq)
    wav = AUDIO / f"line_{seq}.wav"
    voice.write_wav(wav, r.samples)
    atomic_json(VT / "now.json", {
        "id": seq, "name": name, "emotion": emotion, "text": r.text, "audio": f"vtuber/audio/line_{seq}.wav",
        "duration": round(r.duration, 3), "started_ms": int(time.time() * 1000) + 250,
        "cues": r.cues, "words": r.words,
    })
    prune_audio()
    log.info("#%d [%s] %s", seq, emotion, r.text)
    return r.duration


def load_config() -> dict:
    """Optional \"vtuber\" block in config.json: {\"name\": ..., \"pitch\": ..., \"gap_seconds\": ...}"""
    for c in (os.environ.get("CONFIG"), ROOT / "config.json", ROOT / "config.example.json"):
        if c and pathlib.Path(c).is_file():
            try:
                return json.loads(pathlib.Path(c).read_text(encoding="utf-8")).get("vtuber", {}) or {}
            except (OSError, ValueError):
                return {}
    return {}


def read_data() -> dict:
    try:
        return json.loads((WEB / "data.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(args: argparse.Namespace) -> int:
    cfg = load_config()
    name = str(os.environ.get("VTUBER_NAME") or cfg.get("name") or "Pyon")[:24]
    pitch = float(os.environ.get("VOICE_PITCH") or cfg.get("pitch") or 150)
    gap = float(cfg.get("gap_seconds", 1.4))
    script_path = pathlib.Path(os.environ.get("VTUBER_SCRIPT") or args.script or DEFAULT_SCRIPT)
    if not script_path.is_absolute():
        script_path = ROOT / script_path
    script = load_script(script_path)
    if not script:
        log.error("no usable lines in %s", script_path)
        return 1
    write_assets()
    log.info("%s is live. voice effects available: %s", name, ", ".join(voice.available_sfx()))
    rng = random.Random()  # noqa: S311 (just picks jokes)
    seq = int(time.time()) % 100000
    while True:
        lines = list(script)
        if args.news:
            news = news_lines(read_data(), rng)
            if news:  # one script line, then reactions to the news
                lines = [rng.choice(script)] + news
        for emo, text in lines:
            seq += 1
            dur = speak(seq, emo, text, name, pitch)
            time.sleep(dur + gap)
        if args.once:
            return 0


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vtuber", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", help="script file (default vtuber/lines.txt, or $VTUBER_SCRIPT)")
    ap.add_argument("--news", action="store_true", help="react to the headlines in web/data.json")
    ap.add_argument("--once", action="store_true", help="play the script once and exit")
    ap.add_argument("--build", action="store_true", help="write face.svg + emotions.json and exit")
    ap.add_argument("--say", help="render this text to a WAV (use with --out) and exit")
    ap.add_argument("--emotion", default="neutral", choices=sorted(face.EMOTIONS))
    ap.add_argument("--out", default="output/say.wav", help="WAV path for --say (default output/say.wav)")
    ap.add_argument("--pitch", type=float, default=150.0, help="base voice pitch in Hz for --say")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        if args.build:
            write_assets()
            print(f"wrote {VT / 'face.svg'} and {VT / 'emotions.json'}")
            return 0
        if args.say:
            r = voice.render_line(args.say, args.emotion, base_pitch=args.pitch)
            out = pathlib.Path(args.out)
            voice.write_wav(out if out.is_absolute() else ROOT / out, r.samples)
            print(f"wrote {args.out}: {r.duration:.2f}s, {len(r.cues)} mouth cues, subtitle: {r.text}")
            return 0
        return run(args)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as e:
        log.error("vtuber stopped: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
