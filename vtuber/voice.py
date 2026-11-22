"""Voice engine: turns a line of text into babble audio + mouth cues + word timings.

Pure standard library (math / wave / struct), so it runs anywhere the rest of the project runs.

How it sounds: every letter becomes a short tone. The letter decides the pitch (so the same word always
sounds the same), vowels last longer, spaces and punctuation make pauses, a "?" makes the last word rise.
Think Animal Crossing / Undertale. Emotions change pitch, speed and "grit".

Sound effects: write [laugh] [gasp] [boing] [ahem] [sigh] inside a line. To add your own, drop a 16-bit PCM
WAV into assets/sounds/<name>.wav and write [<name>]. Your file wins over a built-in with the same name.
"""
from __future__ import annotations

import math
import pathlib
import random
import re
import struct
import wave
from dataclasses import dataclass, field

SR = 22050
ROOT = pathlib.Path(__file__).resolve().parent.parent
SOUNDS_DIR = ROOT / "assets" / "sounds"

TAG_RE = re.compile(r"\[([a-z0-9_]{1,24})\]")
VOWEL_MOUTH = {"a": "wide", "e": "small", "i": "small", "o": "o", "u": "o"}
LIPS_CLOSED = set("bmp")

# emotion -> (pitch multiplier, speed multiplier, grit 0..1)
EMOTION_VOICE = {
    "neutral": (1.00, 1.00, 0.10),
    "happy": (1.18, 1.10, 0.05),
    "surprised": (1.35, 1.15, 0.05),
    "sad": (0.82, 0.80, 0.00),
    "angry": (0.78, 1.15, 0.65),
    "smug": (0.95, 0.90, 0.20),
    "sleepy": (0.75, 0.65, 0.00),
    "panic": (1.45, 1.45, 0.15),
}


@dataclass
class Rendered:
    """Result of rendering one line."""

    samples: list = field(default_factory=list)  # floats in -1..1
    cues: list = field(default_factory=list)  # [start_s, end_s, mouth]
    words: list = field(default_factory=list)  # [start_s, word]
    text: str = ""  # text for the subtitle (sfx tags become *name*)

    @property
    def duration(self) -> float:
        return len(self.samples) / SR


# --------------------------------------------------------------------------- tiny synth helpers
def _env(i: int, n: int) -> float:
    """Soft attack/decay so each blip has no click."""
    x = i / max(1, n - 1)
    return min(1.0, i / (0.008 * SR)) * math.sin(math.pi * x) ** 0.55


def _tone(freq: float, dur: float, amp: float, grit: float, vowel: bool) -> list:
    n = max(1, int(dur * SR))
    out = []
    w = 2 * math.pi * freq / SR
    h2 = 0.55 if vowel else 0.3  # vowels are rounder, consonants thinner
    for i in range(n):
        s = math.sin(w * i) + h2 * math.sin(2 * w * i) + 0.25 * math.sin(3 * w * i)
        if grit:
            s = (1 - grit) * s + grit * math.tanh(3.0 * s)  # drive it a little for an angry buzz
        out.append(amp * _env(i, n) * s / 1.6)
    return out


def _silence(dur: float) -> list:
    return [0.0] * int(dur * SR)


def _noise(rng: random.Random, dur: float, amp: float, lowpass: float = 0.25) -> list:
    out, prev = [], 0.0
    n = int(dur * SR)
    for i in range(n):
        prev += lowpass * ((rng.random() * 2 - 1) - prev)
        out.append(amp * prev * _env(i, n))
    return out


def letter_freq(ch: str, base: float, rise: float = 0.0) -> float:
    """Deterministic pitch per character: same letter, same note."""
    if ch.isalpha():
        semitone = (ord(ch.lower()) * 7) % 13
    elif ch.isdigit():
        semitone = 3 + int(ch)
    else:
        semitone = 5
    return base * 2 ** (semitone / 12) * (1 + rise)


# --------------------------------------------------------------------------- built-in sound effects
def _sfx_laugh(rng: random.Random):
    s, cues, t = [], [], 0.0
    for k in range(4):
        d = 0.11
        s += _tone(330 - k * 25, d, 0.7, 0.1, True)
        cues.append([t, t + d, "wide"])
        t += d
        gap = 0.07
        s += _silence(gap)
        cues.append([t, t + gap, "small"])
        t += gap
    return s, cues


def _sfx_gasp(rng: random.Random):
    s = _noise(rng, 0.35, 1.4, 0.35)
    return s, [[0.0, 0.35, "o"]]


def _sfx_boing(rng: random.Random):
    n = int(0.55 * SR)
    s, phase = [], 0.0
    for i in range(n):
        x = i / n
        f = 220 + 160 * math.sin(x * 18) * (1 - x)
        phase += 2 * math.pi * f / SR
        s.append(0.6 * math.sin(phase) * (1 - x) ** 0.7)
    return s, [[0.0, 0.55, "wide"]]


def _sfx_ahem(rng: random.Random):
    s, cues, t = [], [], 0.0
    for d in (0.14, 0.18):
        s += _tone(120, d, 0.8, 0.6, False)
        cues.append([t, t + d, "small"])
        t += d
        s += _silence(0.1)
        cues.append([t, t + 0.1, "closed"])
        t += 0.1
    return s, cues


def _sfx_sigh(rng: random.Random):
    s = _noise(rng, 0.8, 1.0, 0.12)
    return s, [[0.0, 0.8, "o"]]


BUILTIN_SFX = {"laugh": _sfx_laugh, "gasp": _sfx_gasp, "boing": _sfx_boing, "ahem": _sfx_ahem, "sigh": _sfx_sigh}


# --------------------------------------------------------------------------- user samples
def load_wav(path: pathlib.Path) -> list:
    """Read a 16-bit PCM WAV, mix to mono, resample to SR. Raises ValueError for anything else."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: only 16-bit PCM WAV is supported")
        ch, rate, n = w.getnchannels(), w.getframerate(), w.getnframes()
        if n > rate * 30:
            raise ValueError(f"{path.name}: longer than 30 s")
        raw = w.readframes(n)
    vals = struct.unpack("<%dh" % (len(raw) // 2), raw)
    mono = [sum(vals[i:i + ch]) / (ch * 32768.0) for i in range(0, len(vals) - ch + 1, ch)]
    if rate == SR or not mono:
        return mono
    ratio, out = rate / SR, []
    for i in range(int(len(mono) / ratio)):  # linear resample
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        nxt = mono[min(j + 1, len(mono) - 1)]
        out.append(mono[j] * (1 - frac) + nxt * frac)
    return out


def auto_cues(samples: list, window: float = 0.06) -> list:
    """Cheap lip-sync for any sample: mouth opens when the sound is loud."""
    step = int(window * SR)
    if not samples:
        return []
    peak = max(abs(x) for x in samples) or 1.0
    cues = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        rms = math.sqrt(sum(x * x for x in chunk) / len(chunk)) / peak
        mouth = "wide" if rms > 0.35 else "small" if rms > 0.12 else "closed"
        cues.append([i / SR, (i + len(chunk)) / SR, mouth])
    return cues


def sfx(name: str, rng: random.Random):
    """Return (samples, cues) for [name], or None if unknown. Custom files in assets/sounds win."""
    if not re.fullmatch(r"[a-z0-9_]{1,24}", name):
        return None
    custom = SOUNDS_DIR / f"{name}.wav"
    if custom.is_file():
        samples = load_wav(custom)
        return samples, auto_cues(samples)
    if name in BUILTIN_SFX:
        return BUILTIN_SFX[name](rng)
    return None


def available_sfx() -> list:
    names = set(BUILTIN_SFX)
    if SOUNDS_DIR.is_dir():
        names |= {p.stem for p in SOUNDS_DIR.glob("*.wav") if re.fullmatch(r"[a-z0-9_]{1,24}", p.stem)}
    return sorted(names)


# --------------------------------------------------------------------------- the main entry point
def split_segments(text: str) -> list:
    """'Hi [laugh] there' -> [('text','Hi'), ('sfx','laugh'), ('text','there')]"""
    out, pos = [], 0
    for m in TAG_RE.finditer(text):
        if text[pos:m.start()].strip():
            out.append(("text", text[pos:m.start()].strip()))
        out.append(("sfx", m.group(1)))
        pos = m.end()
    if text[pos:].strip():
        out.append(("text", text[pos:].strip()))
    return out


def render_line(text: str, emotion: str = "neutral", base_pitch: float = 150.0, seed: int = 7) -> Rendered:
    """Render one line. Deterministic for the same input."""
    pitch_m, speed_m, grit = EMOTION_VOICE.get(emotion, EMOTION_VOICE["neutral"])
    base = base_pitch * pitch_m
    rng = random.Random(seed)  # noqa: S311 (audio noise, not security)
    r = Rendered()
    t = 0.0

    def add(samples: list, cues: list | None = None, shift: float = 0.0):
        nonlocal t
        r.samples += samples
        for c0, c1, m in cues or []:
            r.cues.append([round(t + c0, 3), round(t + c1, 3), m])
        t += len(samples) / SR + shift

    shown = []
    for kind, val in split_segments(text):
        if kind == "sfx":
            got = sfx(val, rng)
            if got is None:  # unknown tag: show it, make no sound
                shown.append(f"[{val}]")
                continue
            r.words.append([round(t, 3), f"*{val}*"])
            shown.append(f"*{val}*")
            add(got[0], got[1])
            add(_silence(0.12 / speed_m), [[0, 0.12 / speed_m, "closed"]])
            continue
        for token in val.split():
            r.words.append([round(t, 3), token])
            shown.append(token)
            question = token.rstrip('"\')').endswith("?")
            n_letters = sum(c.isalnum() for c in token)
            seen = 0
            for ch in token:
                if ch.isalnum():
                    vowel = ch.lower() in VOWEL_MOUTH
                    dur = (0.095 if vowel else 0.06) / speed_m
                    rise = 0.3 * seen / max(1, n_letters) if question else 0.0
                    seen += 1
                    f = letter_freq(ch, base, rise)
                    mouth = VOWEL_MOUTH.get(ch.lower(), "closed" if ch.lower() in LIPS_CLOSED else "small")
                    add(_tone(f, dur, 0.8, grit, vowel), [[0, dur, mouth]], 0.012 / speed_m)
                elif ch in ",;:":
                    add(_silence(0.17 / speed_m), [[0, 0.17 / speed_m, "closed"]])
                elif ch in ".!?…":
                    add(_silence(0.3 / speed_m), [[0, 0.3 / speed_m, "closed"]])
            add(_silence(0.055 / speed_m), [[0, 0.055 / speed_m, "closed"]])

    r.text = " ".join(shown)
    # normalise + fade out + a little tail so the audio never ends abruptly
    peak = max((abs(x) for x in r.samples), default=0.0)
    if peak > 0:
        k = 0.8 / peak if peak > 0.8 else 1.0
        r.samples = [x * k for x in r.samples]
    r.samples += _silence(0.2)
    return r


def write_wav(path: pathlib.Path, samples: list) -> None:
    """Write mono 16-bit PCM."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = struct.pack("<%dh" % len(samples), *[max(-32767, min(32767, int(x * 32767))) for x in samples])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)
