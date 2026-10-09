"""The web dashboard's HTTP API, against a real server on a free local port."""

import http.client
import json
import os
import time
import urllib.parse

import helpers


class WebTest(helpers.DriveTest):
    def setUp(self):
        super().setUp()
        self.d = self.drive(web_token="secret-token")
        self.web = self.d.start_web(port=0)
        self.cookie = None

    def tearDown(self):
        self.web.stop()
        super().tearDown()

    def req(self, method, path, body=None, headers=None, auth=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.web.port, timeout=10)
        h = dict(headers or {})
        if auth and self.cookie:
            h["Cookie"] = self.cookie
        if method == "POST":
            h.setdefault("X-DD", "1")
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
                h["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, dict(r.getheaders()), data

    def login(self):
        status, headers, _ = self.req("GET", "/login?t=secret-token", auth=False)
        self.assertEqual(status, 302)
        self.cookie = headers["Set-Cookie"].split(";")[0]

    def test_sign_in_required(self):
        self.assertEqual(self.req("GET", "/api/status")[0], 401)
        status, _, body = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"link from the DiscordDrive menu", body)       # the sign-in page
        self.assertEqual(self.req("GET", "/login?t=wrong", auth=False)[0], 200)
        self.assertEqual(self.req("GET", "/api/status")[0], 401)
        self.login()
        self.assertEqual(self.req("GET", "/api/status")[0], 200)
        status, _, body = self.req("GET", "/")
        self.assertIn(b"app.js", body)

    def test_post_needs_header(self):
        self.login()
        self.assertEqual(self.req("POST", "/api/mkdir", {"path": "/x"}, headers={"X-DD": ""})[0], 403)

    def test_foreign_host_refused(self):
        self.login()
        self.assertEqual(self.req("GET", "/api/status", headers={"Host": "evil.example"})[0], 421)

    def test_files(self):
        self.login()
        self.assertEqual(self.req("POST", "/api/mkdir", {"path": "/Music"})[0], 200)
        data = os.urandom(300_000)
        status, _, body = self.req("POST", "/api/upload?" + urllib.parse.urlencode({"path": "/Music/song.mp3"}), data)
        self.assertEqual(status, 200, body)
        listing = json.loads(self.req("GET", "/api/list?path=%2FMusic")[2])
        self.assertEqual([i["name"] for i in listing["items"]], ["song.mp3"])

        status, headers, body = self.req("GET", "/api/file?path=%2FMusic%2Fsong.mp3", headers={"Range": "bytes=100-199"})
        self.assertEqual(status, 206)
        self.assertEqual(body, data[100:200])
        self.assertEqual(headers["Content-Range"], f"bytes 100-199/{len(data)}")

        # after upload to "Discord", reads come from the pieces
        self.upload(self.d)
        status, _, body = self.req("GET", "/api/file?path=%2FMusic%2Fsong.mp3")
        self.assertEqual(body, data)

        found = json.loads(self.req("GET", "/api/search?q=son")[2])["items"]
        self.assertEqual(found[0]["path"], "/Music/song.mp3")

        self.assertEqual(self.req("POST", "/api/move", {"from": "/Music/song.mp3", "to": "/Music/tune.mp3"})[0], 200)
        self.assertIsNotNone(self.d.index.resolve("/Music/tune.mp3"))
        self.assertEqual(self.req("POST", "/api/delete", {"path": "/Music"})[0], 200)
        self.assertIsNone(self.d.index.resolve("/Music"))

    def test_share_link(self):
        self.login()
        self.write(self.d, "/a.txt", b"shared text")
        self.upload(self.d)
        share = json.loads(self.req("POST", "/api/share", {"path": "/a.txt", "hours": 1})[2])
        status, _, body = self.req("GET", share["path"], auth=False)
        self.assertEqual(status, 200)
        self.assertIn(b"a.txt", body)
        status, _, body = self.req("GET", share["path"] + "/raw", auth=False)
        self.assertEqual(body, b"shared text")
        tampered = share["path"][:-3] + ("AAA" if not share["path"].endswith("AAA") else "BBB")
        self.assertEqual(self.req("GET", tampered, auth=False)[0], 404)

    def test_html_files_are_sandboxed(self):
        self.login()
        self.write(self.d, "/page.html", b"<script>alert(1)</script>")
        _, headers, _ = self.req("GET", "/api/file?path=%2Fpage.html")
        self.assertIn("sandbox", headers.get("Content-Security-Policy", ""))

    def test_snapshots_and_versions(self):
        self.login()
        self.write(self.d, "/v.txt", b"first")
        self.upload(self.d)
        self.write(self.d, "/v.txt", b"second")
        self.upload(self.d)
        versions = json.loads(self.req("GET", "/api/versions?path=%2Fv.txt")[2])["versions"]
        self.assertEqual(len(versions), 1)
        self.assertEqual(self.req("POST", "/api/versions/restore", {"path": "/v.txt", "n": 1})[0], 200)
        self.d.journal.sync_once()
        self.assertEqual(self.read(self.d, "/v.txt"), b"first")

        self.assertEqual(self.req("POST", "/api/snapshots/create", {"label": "t"})[0], 200)
        snaps = json.loads(self.req("GET", "/api/snapshots")[2])["items"]
        self.assertEqual(len(snaps), 1)
        status, _, body = self.req("POST", "/api/snapshots/restore", {"id": snaps[0]["id"], "path": "/"})
        self.assertEqual(status, 200, body)
        self.d.journal.sync_once()
        folder = json.loads(body)["folder"]
        self.assertEqual(self.read(self.d, folder + "/v.txt"), b"first")

    def test_status(self):
        self.login()
        st = json.loads(self.req("GET", "/api/status")[2])
        for key in ("version", "stats", "health", "devices", "uploads"):
            self.assertIn(key, st)
        self.assertTrue(any(d["me"] for d in st["devices"]))


if __name__ == "__main__":
    import unittest
    unittest.main()
