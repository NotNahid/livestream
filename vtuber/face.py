"""The VTuber's face, drawn by Python.

`build_svg()` returns one SVG string. Every eye / mouth / extra is a separate group with a class name
(e-open, m-wide, x-sweat ...). The CSS inside the SVG shows or hides them depending on two attributes
that the web page sets on the <svg>:

    data-emo="happy"     which emotion (changes eyes, brows, blush, extras)
    data-mouth="wide"    which mouth shape (closed | small | wide | o | smile | frown | flat | smug)

To change the character, edit the colours / shapes here and run:  python3 -m vtuber --build
To add an emotion, add an entry to EMOTIONS (and its voice settings in voice.py).
"""
from __future__ import annotations

import json

# eyes: which eye group is visible; rest: mouth shown when not talking (and for "closed" cues);
# brow: (angle for the LEFT brow in degrees, mirrored for the right; vertical shift in px);
# blush: 0..1; extras: x-* groups that appear.
EMOTIONS = {
    "neutral": {"eyes": "open", "rest": "flat", "brow": (0, 0), "blush": 0.25, "extras": []},
    "happy": {"eyes": "happy", "rest": "smile", "brow": (-4, -8), "blush": 0.75, "extras": ["sparkle"]},
    "surprised": {"eyes": "wide", "rest": "o", "brow": (0, -20), "blush": 0.2, "extras": []},
    "sad": {"eyes": "sad", "rest": "frown", "brow": (-14, 0), "blush": 0.1, "extras": ["tear"]},
    "angry": {"eyes": "narrow", "rest": "frown", "brow": (16, 2), "blush": 0.05, "extras": ["anger"]},
    "smug": {"eyes": "narrow", "rest": "smug", "brow": (-9, -4), "blush": 0.4, "extras": []},
    "sleepy": {"eyes": "closed", "rest": "flat", "brow": (-3, 2), "blush": 0.2, "extras": ["zzz"]},
    "panic": {"eyes": "wide", "rest": "small", "brow": (-10, -16), "blush": 0.0, "extras": ["sweat"]},
}
MOUTHS = ("closed", "small", "wide", "o", "smile", "frown", "flat", "smug")
EYE_KINDS = ("open", "happy", "wide", "sad", "narrow", "closed")
EXTRAS = ("sparkle", "tear", "anger", "zzz", "sweat")

INK = "#3a2a55"  # outline colour

# Hand-written pieces. Eye centres are (225, 305) and (375, 305); mouth centre is (300, 395).


def _eye(cx: int, cy: int, kind: str, left: bool) -> str:
    s = 1 if left else -1
    if kind in ("open", "wide", "sad", "narrow"):
        ry = {"open": 44, "wide": 52, "sad": 42, "narrow": 26}[kind]
        rx = {"open": 33, "wide": 38, "sad": 33, "narrow": 36}[kind]
        pupil = {"open": 12, "wide": 6, "sad": 14, "narrow": 10}[kind]
        lid = ""
        if kind == "sad":  # droopy lid, skin coloured
            lid = f'<path d="M{cx - 40} {cy - 50} L{cx + 40} {cy - 50} L{cx - 40 * s} {cy - 8} Z" fill="url(#skin)"/>'
        return (
            f'<g class="e-{kind}">'
            f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#fff" stroke="{INK}" stroke-width="5"/>'
            f'<ellipse cx="{cx}" cy="{cy + 4}" rx="{rx - 9}" ry="{ry - 8}" fill="url(#iris)"/>'
            f'<ellipse cx="{cx}" cy="{cy + 4}" rx="{pupil}" ry="{pupil + 8}" fill="{INK}"/>'
            f'<circle cx="{cx - 11}" cy="{cy - 12}" r="9" fill="#fff"/><circle cx="{cx + 10}" cy="{cy + 14}" r="4.5" fill="#fff"/>'
            f"{lid}</g>"
        )
    if kind == "happy":  # ^ ^
        return f'<path class="e-happy" d="M{cx - 34} {cy + 10} Q{cx} {cy - 42} {cx + 34} {cy + 10}" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>'
    # closed: a gentle downward curve
    return f'<path class="e-closed" d="M{cx - 34} {cy} Q{cx} {cy + 24} {cx + 34} {cy}" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>'


def _mouths() -> str:
    c = f'fill="none" stroke="{INK}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"'
    return (
        f'<path class="m-closed" d="M278 396 Q300 402 322 396" {c}/>'
        f'<ellipse class="m-small" cx="300" cy="398" rx="14" ry="10" fill="#7a2f4d" stroke="{INK}" stroke-width="6"/>'
        f'<g class="m-wide"><ellipse cx="300" cy="402" rx="30" ry="26" fill="#7a2f4d" stroke="{INK}" stroke-width="6"/>'
        f'<ellipse cx="300" cy="416" rx="16" ry="9" fill="#ff8fa6"/></g>'
        f'<ellipse class="m-o" cx="300" cy="402" rx="15" ry="19" fill="#7a2f4d" stroke="{INK}" stroke-width="6"/>'
        f'<path class="m-smile" d="M268 388 Q300 428 332 388" {c}/>'
        f'<path class="m-frown" d="M272 408 Q300 382 328 408" {c}/>'
        f'<path class="m-flat" d="M280 398 L320 398" {c}/>'
        f'<path class="m-smug" d="M272 400 Q292 408 310 398 Q322 392 334 380" {c}/>'
    )


def _extras() -> str:
    return (
        # sparkles around the head
        f'<g class="x-sparkle" fill="#ffe27a" stroke="{INK}" stroke-width="3">'
        '<path d="M92 190 l8 -22 l8 22 l22 8 l-22 8 l-8 22 l-8 -22 l-22 -8 Z"/>'
        '<path d="M505 150 l6 -16 l6 16 l16 6 l-16 6 l-6 16 l-6 -16 l-16 -6 Z"/></g>'
        # tear
        '<path class="x-tear" d="M163 360 q-16 30 0 42 q16 -12 0 -42 Z" fill="#8fd3ff" stroke="#3a2a55" stroke-width="3"/>'
        # anger vein
        f'<g class="x-anger" fill="none" stroke="#ff4b5c" stroke-width="7" stroke-linecap="round">'
        '<path d="M450 140 q16 -6 20 -22 M450 140 q-6 -16 -22 -20 M482 156 q-12 12 -28 8 M436 164 q4 16 -8 28"/></g>'
        # zzz
        f'<g class="x-zzz" fill="{INK}" font-family="ui-sans-serif,system-ui,sans-serif" font-weight="800">'
        '<text x="470" y="150" font-size="44">Z</text><text x="506" y="108" font-size="32">z</text>'
        '<text x="532" y="76" font-size="24">z</text></g>'
        # sweat drop
        '<path class="x-sweat" d="M470 190 q-24 40 0 56 q24 -16 0 -56 Z" fill="#8fd3ff" stroke="#3a2a55" stroke-width="4"/>'
    )


def build_css() -> str:
    rules = [
        "#vt-face{overflow:visible}",
        "#vt-face .blink-line{display:none}",
        "#vt-face [class^=e-],#vt-face [class^=m-],#vt-face [class^=x-]{display:none}",
        "#vt-face #brow-l,#vt-face #brow-r{transform-box:fill-box;transform-origin:center;transition:transform .18s ease-out}",
        "#vt-face #blush{transition:opacity .25s}",
        "#vt-face #ahoge{transform-box:fill-box;transform-origin:50% 100%;animation:ahoge 2.6s ease-in-out infinite}",
        "#vt-face.speaking #ahoge{animation-duration:.55s}",
        "@keyframes ahoge{0%,100%{transform:rotate(-7deg)}50%{transform:rotate(9deg)}}",
        "@keyframes shake{0%,100%{transform:translate(0,0)}25%{transform:translate(-4px,2px)}75%{transform:translate(4px,-2px)}}",
        '#vt-face[data-emo="panic"] #head-group{animation:shake .12s linear infinite}',
        '#vt-face[data-blink="1"] .e-open,#vt-face[data-blink="1"] .e-wide,#vt-face[data-blink="1"] .e-sad,'
        '#vt-face[data-blink="1"] .e-narrow{display:none !important}',
        '#vt-face[data-blink="1"] .blink-line{display:inline !important}',
    ]
    for m in MOUTHS:
        rules.append(f'#vt-face[data-mouth="{m}"] .m-{m}{{display:inline}}')
    for name, e in EMOTIONS.items():
        sel = f'#vt-face[data-emo="{name}"]'
        rules.append(f"{sel} .e-{e['eyes']}{{display:inline}}")
        ang, dy = e["brow"]
        rules.append(f"{sel} #brow-l{{transform:translateY({dy}px) rotate({ang}deg)}}")
        rules.append(f"{sel} #brow-r{{transform:translateY({dy}px) rotate({-ang}deg)}}")
        rules.append(f"{sel} #blush{{opacity:{e['blush']}}}")
        for x in e["extras"]:
            rules.append(f"{sel} .x-{x}{{display:inline}}")
    return "\n".join(rules)


def build_svg() -> str:
    eyes = "".join(_eye(cx, 305, k, left) for k in EYE_KINDS for cx, left in ((225, True), (375, False)))
    # a thin closed line shown while blinking (separate from e-closed so happy/sleepy eyes are not affected)
    blink = (
        f'<path class="blink-line" d="M191 305 Q225 325 259 305" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>'
        f'<path class="blink-line" d="M341 305 Q375 325 409 305" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" id="vt-face" viewBox="0 0 600 620" data-emo="neutral" data-mouth="flat">
<defs>
  <linearGradient id="skin" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff3ee"/><stop offset="1" stop-color="#ffd2d8"/></linearGradient>
  <linearGradient id="hair" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7c5cff"/><stop offset="1" stop-color="#ff6fb1"/></linearGradient>
  <radialGradient id="iris" cx=".5" cy=".35" r=".8"><stop offset="0" stop-color="#8be9ff"/><stop offset="1" stop-color="#4b6bff"/></radialGradient>
  <filter id="soft"><feGaussianBlur stdDeviation="9"/></filter>
</defs>
<style>
{build_css()}
</style>
<g id="body">
  <path d="M120 620 Q130 500 300 490 Q470 500 480 620 Z" fill="#2c2350" stroke="{INK}" stroke-width="5"/>
  <path d="M250 492 Q300 540 350 492" fill="none" stroke="#ff6fb1" stroke-width="8" stroke-linecap="round"/>
  <circle cx="300" cy="545" r="12" fill="#ffe27a" stroke="{INK}" stroke-width="3"/>
</g>
<g id="head-group">
  <path id="hair-back" d="M95 330 Q60 130 300 85 Q540 130 505 330 Q520 470 440 520 L160 520 Q80 470 95 330 Z" fill="url(#hair)" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>
  <ellipse id="head" cx="300" cy="320" rx="190" ry="180" fill="url(#skin)" stroke="{INK}" stroke-width="5"/>
  <g id="blush" opacity=".25" filter="url(#soft)"><ellipse cx="170" cy="375" rx="40" ry="22" fill="#ff5f8f"/><ellipse cx="430" cy="375" rx="40" ry="22" fill="#ff5f8f"/></g>
  {eyes}
  {blink}
  <path id="brow-l" d="M185 238 Q225 218 266 236" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>
  <path id="brow-r" d="M334 236 Q375 218 415 238" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>
  {_mouths()}
  <path id="bangs" d="M110 300 Q100 120 300 105 Q500 120 490 300 Q470 200 400 180 Q360 230 300 190 Q240 235 195 180 Q125 205 110 300 Z" fill="url(#hair)" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>
  <path id="ahoge" d="M300 112 Q270 40 322 22 Q352 14 340 46 Q332 66 314 58" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>
  {_extras()}
</g>
</svg>
"""


def emotions_json() -> str:
    """Config for the web page: which mouth each emotion rests on, and which eyes blink."""
    out = {
        n: {"rest": e["rest"], "blinks": e["eyes"] in ("open", "wide", "sad", "narrow")} for n, e in EMOTIONS.items()
    }
    return json.dumps(out, indent=1)
