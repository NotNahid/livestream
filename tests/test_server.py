import json
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import server  # noqa: E402


class StateValidation(unittest.TestCase):
    def test_accepts_valid_patch(self):
        out = server.sanitize_state({"message": " hi ", "message_seconds": 5, "scene": "p2", "paused": 1, "theme": "neon"})
        self.assertEqual(out["message"], "hi")
        self.assertEqual(out["scene"], "p2")
        self.assertIs(out["paused"], True)

    def test_rejects_bad_input(self):
        for bad in ({"message": "x" * 201}, {"scene": "../etc"}, {"theme": "pink"}):
            with self.assertRaises(ValueError):
                server.sanitize_state(bad)

    def test_empty_message_clears_expiry(self):
        self.assertEqual(server.sanitize_state({"message": ""})["message_until"], 0)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.make_server("127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def req(self, path, body=None, headers=None):
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {},
                                   data=None if body is None else json.dumps(body).encode(),
                                   method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_health_and_static(self):
        self.assertEqual(self.req("/api/health"), (200, b'{"ok": true}'))
        code, body = self.req("/index.html")
        self.assertEqual(code, 200)
        self.assertIn(b"stage", body)

    def test_no_directory_listing_or_traversal(self):
        self.assertEqual(self.req("/")[0], 200)            # index.html
        self.assertEqual(self.req("/../server.py")[0], 404)
        self.assertEqual(self.req("/..%2fserver.py")[0], 404)

    def test_post_state_roundtrip(self):
        code, body = self.req("/api/state", {"message": "hello", "theme": "terminal"})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(self.req("/api/state")[1])["message"], "hello")
        self.assertEqual(self.req("/api/state", {"theme": "bad"})[0], 400)
        self.req("/api/state", {"message": "", "theme": ""})

    def test_token_required_when_set(self):
        with mock.patch.dict("os.environ", {"ADMIN_TOKEN": "s3cret"}):
            self.assertEqual(self.req("/api/state", {"paused": True})[0], 401)
            self.assertEqual(self.req("/api/state", {"paused": True}, {"X-Admin-Token": "wrong"})[0], 401)
            self.assertEqual(self.req("/api/state", {"paused": False}, {"X-Admin-Token": "s3cret"})[0], 200)

    def test_public_bind_requires_token(self):
        with mock.patch.dict("os.environ", {}, clear=True), self.assertRaises(SystemExit):
            server.make_server("0.0.0.0", 0)

    def test_status_shape(self):
        data = json.loads(self.req("/api/status")[1])
        for key in ("server_uptime_s", "ffmpeg", "state", "panels"):
            self.assertIn(key, data)


class FfmpegParse(unittest.TestCase):
    def test_regex(self):
        line = "frame=  900 fps= 30 q=26.0 size=    1024kB time=00:00:30.00 bitrate=2500.1kbits/s speed=1.00x"
        m = server.FFMPEG_RE.search(line)
        self.assertEqual((m[1], m[2], m[3], m[4]), ("900", "30", "2500.1", "1.00"))


if __name__ == "__main__":
    unittest.main()
