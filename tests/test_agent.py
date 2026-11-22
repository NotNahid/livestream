import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import agent  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_validate_clamps_and_defaults(self):
        cfg = agent.validate_config({"rotate_seconds": 1, "refresh_seconds": 99999, "theme": "nope", "sources": []})
        self.assertEqual(cfg["rotate_seconds"], 5)
        self.assertEqual(cfg["refresh_seconds"], 3600)
        self.assertEqual(cfg["theme"], "midnight")
        self.assertTrue(cfg["sources"])

    def test_example_config_is_valid(self):
        path = pathlib.Path(agent.ROOT / "config.example.json")
        cfg = agent.validate_config(json.loads(path.read_text()))
        for sc in cfg["sources"]:
            self.assertIn(sc["type"], agent.SOURCES)


class HelperTests(unittest.TestCase):
    def test_clip(self):
        self.assertEqual(agent.clip("a  b\n c"), "a b c")
        self.assertEqual(len(agent.clip("x" * 500, 50)), 50)

    def test_human(self):
        self.assertEqual(agent.human(950), "950")
        self.assertEqual(agent.human(1500), "1.5k")
        self.assertEqual(agent.human(2_000_000), "2M")

    def test_http_get_rejects_non_http(self):
        with self.assertRaises(ValueError):
            agent.http_get("file:///etc/passwd")


class SourceTests(unittest.TestCase):
    def test_text_source(self):
        p = agent.SOURCES["text"]({"title": "Hi", "lines": ["one", "two"]})
        self.assertEqual(p["kind"], "text")
        self.assertEqual([i["title"] for i in p["items"]], ["one", "two"])

    def test_file_source_parses_and_blocks_escape(self):
        f = agent.ROOT / "tests" / "_feed.txt"
        f.write_text("Alpha | 1\n\nBeta\n")
        try:
            p = agent.SOURCES["file"]({"path": "tests/_feed.txt"})
            self.assertEqual(p["items"][0], {"title": "Alpha", "meta": "1"})
            self.assertEqual(p["items"][1]["title"], "Beta")
            with self.assertRaises(ValueError):
                agent.SOURCES["file"]({"path": "../../etc/hostname"})
        finally:
            f.unlink()

    def test_rss_source_rss_and_atom(self):
        rss = b"<rss><channel><title>T</title><item><title>A</title><pubDate>Mon</pubDate></item></channel></rss>"
        atom = (b'<feed xmlns="http://www.w3.org/2005/Atom"><title>F</title>'
                b"<entry><title>B</title><updated>2026</updated></entry></feed>")
        with mock.patch.object(agent, "http_get", return_value=rss):
            self.assertEqual(agent.SOURCES["rss"]({"url": "http://x"})["items"][0]["title"], "A")
        with mock.patch.object(agent, "http_get", return_value=atom):
            self.assertEqual(agent.SOURCES["rss"]({"url": "http://x"})["items"][0]["title"], "B")

    def test_crypto_formats_delta(self):
        fake = {"bitcoin": {"usd": 67123.4, "usd_24h_change": -1.234}}
        with mock.patch.object(agent, "http_json", return_value=fake):
            p = agent.SOURCES["crypto"]({"coins": ["bitcoin"]})
        self.assertEqual(p["items"][0]["delta"], -1.23)


class AgentEngineTests(unittest.TestCase):
    def test_failed_source_keeps_last_good_as_stale(self):
        cfg = agent.validate_config({"sources": [{"type": "text", "lines": ["ok"]}]})
        a = agent.Agent(cfg)
        first = a.collect()
        self.assertFalse(first["panels"][0]["stale"])
        with mock.patch.dict(agent.SOURCES, {"text": mock.Mock(side_effect=RuntimeError("boom"))}):
            second = a.collect()
        self.assertTrue(second["panels"][0]["stale"])
        self.assertEqual(second["errors"][0]["source"], "text")

    def test_unknown_source_never_crashes(self):
        a = agent.Agent(agent.validate_config({"sources": [{"type": "does-not-exist"}]}))
        out = a.collect()
        self.assertEqual(out["panels"][0]["title"], "Reconnecting…")
        self.assertEqual(len(out["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
