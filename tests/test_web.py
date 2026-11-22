"""Static sanity checks for the HTML/JSON assets (no browser needed)."""
import json
import pathlib
import unittest
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
VOID = {"meta", "link", "br", "img", "input", "hr", "source"}


class Balanced(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.ids = [], [], set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id":
                if v in self.ids:
                    self.errors.append(f"duplicate id {v}")
                self.ids.add(v)
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
        else:
            self.stack.pop()


class WebAssets(unittest.TestCase):
    def test_html_files_balanced(self):
        for f in list((ROOT / "web").glob("*.html")) + list((ROOT / "docs").glob("*.html")):
            p = Balanced()
            p.feed(f.read_text(encoding="utf-8"))
            self.assertEqual(p.errors, [], f.name)
            self.assertEqual(p.stack, [], f"{f.name} has unclosed tags")

    def test_json_files_parse(self):
        for f in ("config.example.json", "web/demo.json"):
            json.loads((ROOT / f).read_text(encoding="utf-8"))

    def test_demo_panels_have_unique_ids(self):
        panels = json.loads((ROOT / "web/demo.json").read_text())["panels"]
        ids = [p["id"] for p in panels]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
