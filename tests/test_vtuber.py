import json
import pathlib
import re
import sys
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from vtuber import __main__ as director  # noqa: E402
from vtuber import face, voice  # noqa: E402


class Script(unittest.TestCase):
    def test_parse(self):
        out = director.parse_script("# c\n\nhappy | Hi there\nno emotion here\nbogus | still spoken\n  sad |  x  \nangry |")
        self.assertEqual(out, [("happy", "Hi there"), ("neutral", "no emotion here"), ("neutral", "still spoken"), ("sad", "x")])

    def test_default_script_is_valid(self):
        lines = director.load_script(director.DEFAULT_SCRIPT)
        self.assertGreaterEqual(len(lines), 5)
        for emo, text in lines:
            self.assertIn(emo, face.EMOTIONS)
            for tag in voice.TAG_RE.findall(text):
                self.assertIn(tag, voice.available_sfx(), f"unknown sound tag [{tag}]")

    def test_news_lines(self):
        import random
        data = {"panels": [{"title": "Hacker News", "items": [{"title": "A  big\nthing", "meta": "9 pts"}, {"title": "B"}]}, {"items": []}]}
        out = director.news_lines(data, random.Random(1))
        self.assertEqual(len(out), 3)  # 1 opener + 2 items; the empty panel is skipped
        self.assertTrue(all(e in face.EMOTIONS and "\n" not in t for e, t in out))
        self.assertEqual(director.news_lines({}, random.Random(1)), [])


class Voice(unittest.TestCase):
    def test_deterministic_and_timed(self):
        a = voice.render_line("Hello world?", "happy")
        b = voice.render_line("Hello world?", "happy")
        self.assertEqual(a.samples, b.samples)
        self.assertGreater(a.duration, 0.5)
        self.assertEqual([w[1] for w in a.words], ["Hello", "world?"])
        starts = [c[0] for c in a.cues]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(c[2] in face.MOUTHS for c in a.cues))
        self.assertLessEqual(max(abs(x) for x in a.samples), 0.81)

    def test_emotions_change_the_sound(self):
        sad = voice.render_line("same words", "sad")
        panic = voice.render_line("same words", "panic")
        self.assertGreater(sad.duration, panic.duration * 1.5)

    def test_sfx_tags(self):
        r = voice.render_line("a [laugh] b [nope] c")
        self.assertEqual(r.text, "a *laugh* b [nope] c")
        self.assertEqual([w[1] for w in r.words], ["a", "*laugh*", "b", "c"])

    def test_sfx_name_cannot_escape_folder(self):
        import random
        self.assertIsNone(voice.sfx("../etc/passwd", random.Random(0)))
        self.assertIsNone(voice.sfx("..", random.Random(0)))

    def test_wav_roundtrip_and_custom_sample(self):
        r = voice.render_line("test")
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "x.wav"
            voice.write_wav(p, r.samples)
            with wave.open(str(p)) as w:
                self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, voice.SR))
            back = voice.load_wav(p)
            self.assertAlmostEqual(len(back) / voice.SR, r.duration, places=2)
            old = voice.SOUNDS_DIR
            voice.SOUNDS_DIR = pathlib.Path(d)
            try:
                (pathlib.Path(d) / "mine.wav").write_bytes(p.read_bytes())
                self.assertIn("mine", voice.available_sfx())
                got = voice.render_line("hi [mine]")
                self.assertIn("*mine*", got.text)
                self.assertTrue(got.cues)
            finally:
                voice.SOUNDS_DIR = old

    def test_empty_text(self):
        r = voice.render_line("")
        self.assertEqual(r.words, [])


class Face(unittest.TestCase):
    def test_svg_is_valid_and_complete(self):
        svg = face.build_svg()
        ET.fromstring(svg)  # raises if malformed
        for m in face.MOUTHS:
            self.assertIn(f'class="m-{m}"', svg)
        for k in face.EYE_KINDS:
            self.assertIn(f"e-{k}", svg)
        for x in face.EXTRAS:
            self.assertIn(f"x-{x}", svg)

    def test_every_emotion_references_real_parts(self):
        css = face.build_css()
        for name, e in face.EMOTIONS.items():
            self.assertIn(e["eyes"], face.EYE_KINDS)
            self.assertIn(e["rest"], face.MOUTHS)
            self.assertTrue(set(e["extras"]) <= set(face.EXTRAS))
            self.assertIn(f'data-emo="{name}"', css)
            self.assertIn(name, voice.EMOTION_VOICE)  # every look has a voice

    def test_emotions_json(self):
        data = json.loads(face.emotions_json())
        self.assertEqual(set(data), set(face.EMOTIONS))
        self.assertFalse(data["sleepy"]["blinks"])
        self.assertTrue(data["neutral"]["blinks"])

    def test_committed_face_is_up_to_date(self):
        committed = pathlib.Path(director.VT / "face.svg")
        if committed.exists():
            self.assertEqual(committed.read_text(encoding="utf-8"), face.build_svg(), "run: python3 -m vtuber --build")


class Publish(unittest.TestCase):
    def test_speak_writes_now_json(self):
        with tempfile.TemporaryDirectory() as d:
            old = (director.VT, director.AUDIO)
            director.VT = pathlib.Path(d)
            director.AUDIO = pathlib.Path(d) / "audio"
            director.AUDIO.mkdir()
            try:
                dur = director.speak(5, "smug", "Fun fact [ahem]", "Pyon", 150.0)
                now = json.loads((pathlib.Path(d) / "now.json").read_text())
                self.assertEqual((now["id"], now["emotion"], now["name"]), (5, "smug", "Pyon"))
                self.assertAlmostEqual(now["duration"], dur, places=2)
                self.assertTrue(re.fullmatch(r"vtuber/audio/line_5\.wav", now["audio"]))
                self.assertTrue((director.AUDIO / "line_5.wav").exists())
            finally:
                director.VT, director.AUDIO = old


if __name__ == "__main__":
    unittest.main()
