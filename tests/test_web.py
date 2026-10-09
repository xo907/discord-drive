"""The web dashboard's HTTP API, against a real server on a free local port."""

import http.client
import io
import json
import os
import urllib.parse
import zipfile

import helpers


class WebTest(helpers.DriveTest):
    def setUp(self):
        super().setUp()
        self.d = self.drive(web_token="secret-token")
        self.web = self.d.start_web(port=0)
        self.web.set_credentials("Dennis", "correct horse")
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
            if isinstance(body, str):
                body = body.encode()
                h["Content-Type"] = "application/x-www-form-urlencoded"
            elif isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
                h["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, dict(r.getheaders()), data

    def form(self, **fields):
        return urllib.parse.urlencode(fields)

    def login(self, user="dennis", password="correct horse"):
        status, headers, body = self.req("POST", "/login", self.form(user=user, password=password), auth=False)
        if status == 303:
            self.cookie = headers["Set-Cookie"].split(";")[0]
        return status, body

    def test_sign_in_required(self):
        self.assertEqual(self.req("GET", "/api/status")[0], 401)
        status, _, body = self.req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b'action="/login"', body)                       # the sign-in form
        self.assertEqual(self.login(password="wrong")[0], 401)
        self.assertEqual(self.req("GET", "/api/status")[0], 401)
        self.assertEqual(self.login()[0], 303)                         # user name is not case-sensitive
        self.assertEqual(self.req("GET", "/api/status")[0], 200)
        status, _, body = self.req("GET", "/")
        self.assertIn(b"app.js", body)
        self.assertEqual(json.loads(self.req("GET", "/api/status")[2])["user"], "Dennis")

    def test_forged_or_old_sessions_fail(self):
        self.login()
        self.cookie = self.cookie[:-4] + "AAAA"
        self.assertEqual(self.req("GET", "/api/status")[0], 401)
        self.login()
        self.web.set_credentials("Dennis", "a new password")           # changing the password signs everyone out
        self.assertEqual(self.req("GET", "/api/status")[0], 401)
        self.assertEqual(self.login(password="a new password")[0], 303)

    def test_lockout(self):
        for _ in range(5):
            self.assertEqual(self.login(password="nope")[0], 401)
        status, body = self.login()                                     # even the right password waits now
        self.assertEqual(status, 429)
        self.assertIn(b"Too many", body)

    def test_logout(self):
        self.login()
        _, headers, _ = self.req("POST", "/api/logout", {})
        self.assertIn("Max-Age=0", headers["Set-Cookie"])

    def test_first_sign_in_from_this_computer(self):
        self.web.cfg.web_user = self.web.cfg.web_password = ""
        status, _, body = self.req("GET", "/")
        self.assertIn(b'action="/setup"', body)
        status, _, body = self.req("POST", "/setup", self.form(user="me", password="short", password2="short"), auth=False)
        self.assertEqual(status, 400)
        status, headers, _ = self.req("POST", "/setup", self.form(user="me", password="long enough", password2="long enough"),
                                      auth=False)
        self.assertEqual(status, 303)
        self.cookie = headers["Set-Cookie"].split(";")[0]
        self.assertEqual(self.req("GET", "/api/status")[0], 200)
        # once set, /setup can't replace it
        self.assertEqual(self.req("POST", "/setup", self.form(user="x", password="12345678", password2="12345678"),
                                  auth=False)[0], 403)

    def test_zip_copy_and_purge(self):
        self.login()
        self.write(self.d, "/Album/a.txt", b"first file")
        self.write(self.d, "/Album/sub/b.txt", b"second file")
        self.upload(self.d)
        status, _, body = self.req("GET", "/api/zip?path=%2FAlbum")
        self.assertEqual(status, 200)
        z = zipfile.ZipFile(io.BytesIO(body))
        self.assertEqual(z.read("a.txt"), b"first file")
        self.assertEqual(z.read("sub/b.txt"), b"second file")

        self.assertEqual(self.req("POST", "/api/copy", {"from": "/Album/a.txt", "to": "/Album/a copy.txt"})[0], 200)
        self.assertEqual(self.req("GET", "/api/file?path=%2FAlbum%2Fa%20copy.txt")[2], b"first file")
        self.assertEqual(self.req("POST", "/api/move", {"from": "/Album", "to": "/Album/sub/Album"})[0], 400)
        before = self.d.backend.uploads
        self.upload(self.d)
        self.assertEqual(self.d.backend.uploads, before)               # the duplicate reused every piece

        self.assertEqual(self.req("POST", "/api/delete", {"path": "/Album"})[0], 200)
        deleted = json.loads(self.req("GET", "/api/deleted")[2])["items"]
        self.assertEqual(len(deleted), 3)
        uids = [it["uid"] for it in deleted if it["path"] != "/Album/a.txt"]
        r = json.loads(self.req("POST", "/api/purge", {"uids": uids})[2])
        self.assertEqual(r["count"], 2)
        left = json.loads(self.req("GET", "/api/deleted")[2])["items"]
        self.assertEqual([it["path"] for it in left], ["/Album/a.txt"])
        r = json.loads(self.req("POST", "/api/undelete", {"uids": [left[0]["uid"]]})[2])
        self.assertEqual(r["count"], 1)
        self.d.journal.sync_once()
        self.assertEqual(self.read(self.d, "/Album/a.txt"), b"first file")

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

    def test_share_options(self):
        self.login()
        self.write(self.d, "/Trip/photo.txt", b"a view of the sea")
        self.write(self.d, "/Trip/day 2/notes.txt", b"second day")
        self.upload(self.d)
        # a password-protected, view-only link to a folder
        link = json.loads(self.req("POST", "/api/share", {"path": "/Trip", "hours": 1, "password": "open sesame",
                                                          "download": False})[2])
        self.assertTrue(link["password"])
        status, _, body = self.req("GET", link["path"], auth=False)
        self.assertIn(b"Password needed", body)
        self.assertEqual(self.req("GET", link["path"] + "/raw?p=photo.txt", auth=False)[0], 200)   # still the form
        status, _, _ = self.req("POST", link["path"], self.form(password="wrong"), auth=False)
        self.assertEqual(status, 401)
        status, headers, _ = self.req("POST", link["path"], self.form(password="open sesame"), auth=False)
        self.assertEqual(status, 303)
        unlock = headers["Set-Cookie"].split(";")[0]
        status, _, body = self.req("GET", link["path"], headers={"Cookie": unlock}, auth=False)
        self.assertIn(b"photo.txt", body)
        self.assertIn(b"day 2", body)
        self.assertNotIn(b"Download all", body)                     # view only
        status, _, body = self.req("GET", link["path"] + "?p=photo.txt", headers={"Cookie": unlock}, auth=False)
        self.assertIn(b"a view of the sea", body)                   # text shown on the page
        self.assertEqual(self.req("GET", link["path"] + "/raw?p=photo.txt&dl=1", headers={"Cookie": unlock}, auth=False)[0], 403)
        self.assertEqual(self.req("GET", link["path"] + "?p=..", headers={"Cookie": unlock}, auth=False)[0], 404)
        # change it: downloads allowed, no password
        r = json.loads(self.req("POST", "/api/shares/update", {"id": link["id"], "download": True, "password": ""})[2])
        self.assertFalse(r["password"])
        status, _, body = self.req("GET", link["path"] + "/raw?p=day%202/notes.txt&dl=1", auth=False)
        self.assertEqual(body, b"second day")
        status, _, body = self.req("GET", link["path"] + "/zip", auth=False)
        self.assertEqual(zipfile.ZipFile(io.BytesIO(body)).read("photo.txt"), b"a view of the sea")
        listed = json.loads(self.req("GET", "/api/shares")[2])["items"]
        self.assertEqual([x["item"] for x in listed], ["/Trip"])
        self.assertGreaterEqual(listed[0]["views"], 1)
        self.assertEqual(self.req("POST", "/api/shares/revoke", {"id": link["id"]})[0], 200)
        self.assertEqual(self.req("GET", link["path"], auth=False)[0], 404)

    def test_share_link_uses_domain(self):
        self.login()
        self.write(self.d, "/x.txt", b"x")
        self.assertEqual(self.req("GET", "/api/status", headers={"Host": "drive.example.com"})[0], 421)
        self.assertEqual(self.req("POST", "/api/settings", {"web_hosts": "https://Drive.Example.com/"})[0], 200)
        self.assertEqual(self.d.cfg.web_hosts, ["drive.example.com"])
        self.assertEqual(self.req("GET", "/api/status", headers={"Host": "drive.example.com"})[0], 200)
        link = json.loads(self.req("POST", "/api/share", {"path": "/x.txt"})[2])
        self.assertTrue(link["url"].startswith("https://drive.example.com/s/"))
        self.req("POST", "/api/settings", {"web_public_url": "https://files.example.org"})
        link = json.loads(self.req("POST", "/api/share", {"path": "/x.txt"})[2])
        self.assertTrue(link["url"].startswith("https://files.example.org/s/"))
        self.assertEqual(self.req("POST", "/api/settings", {"web_public_url": "not a url"})[0], 400)
        self.assertEqual(self.req("POST", "/api/settings", {"bot_token": "x"})[0], 400)
        values = json.loads(self.req("GET", "/api/settings")[2])["values"]
        self.assertEqual(values["web_public_url"], "https://files.example.org")

    def test_notes(self):
        self.login()
        self.assertEqual(json.loads(self.req("GET", "/api/notes")[2])["items"], [])
        self.req("POST", "/api/mkdir", {"path": "/Notes"})
        self.assertEqual(self.req("POST", "/api/upload?path=%2FNotes%2FShopping.md&save=later", b"Milk, eggs")[0], 200)
        items = json.loads(self.req("GET", "/api/notes")[2])["items"]
        self.assertEqual([(n["title"], n["snippet"]) for n in items], [("Shopping", "Milk, eggs")])
        nid = self.d.index.resolve("/Notes/Shopping.md")["id"]
        self.assertGreater(self.d.uploader._pending[nid], __import__("time").time() + 5)   # waits for a pause
        self.req("POST", "/api/upload?path=%2FNotes%2FShopping.md&save=now", b"Milk, eggs, bread")
        self.assertLessEqual(self.d.uploader._pending[nid], __import__("time").time() + 0.5)  # Save: right away
        self.upload(self.d)
        self.assertEqual(self.read(self.d, "/Notes/Shopping.md"), b"Milk, eggs, bread")

    def test_activity_log_and_changelog(self):
        import logging
        self.login()
        logging.getLogger("discorddrive.test").warning("a line for the log tab")
        lines = json.loads(self.req("GET", "/api/log")[2])["lines"]
        self.assertTrue(any(l["m"] == "a line for the log tab" and l["l"] == "WARNING" for l in lines))
        after = lines[-1]["i"]
        self.assertEqual(json.loads(self.req("GET", f"/api/log?after={after}")[2])["lines"], [])
        # a file being uploaded shows up with progress, speed and time left
        self.write(self.d, "/big.bin", os.urandom(300_000))
        nid = self.d.index.resolve("/big.bin")["id"]
        self.d.uploader.progress[nid] = {"path": "/big.bin", "size": 300_000, "bytes": 100_000, "base": 0,
                                         "started": __import__("time").time() - 2, "done": 1, "total": 3,
                                         "stage": "uploading", "updated": 0}
        a = json.loads(self.req("GET", "/api/activity")[2])
        u = a["uploads"][0]
        self.assertAlmostEqual(u["pct"], 33.3, places=1)
        self.assertGreater(u["speed"], 0)
        self.assertGreater(u["eta"], 0)
        self.assertEqual(json.loads(self.req("GET", "/api/status")[2])["uploads"][0]["path"], "/big.bin")
        log = json.loads(self.req("GET", "/api/changelog")[2])
        self.assertIn(log["version"], log["text"])

    def test_check_and_remove_unreadable(self):
        import time as _t
        self.login()
        self.write(self.d, "/Box/good.bin", os.urandom(200_000))
        self.write(self.d, "/Box/bad.bin", os.urandom(200_000))
        self.d.cfg.parity_enabled = False
        self.upload(self.d)
        for c in self.d.index.get_chunks(self.d.index.resolve("/Box/bad.bin")["id"]):
            self.d.backend.delete(c["message_id"])
        self.assertEqual(self.req("POST", "/api/check/start", {"path": "/Box"})[0], 200)
        for _ in range(100):
            st = json.loads(self.req("GET", "/api/check")[2])
            if not st["running"]:
                break
            _t.sleep(0.1)
        self.assertEqual(st["checked"], 2)
        self.assertEqual([b["path"] for b in st["bad"]], ["/Box/bad.bin"])
        self.assertEqual(st["bad"][0]["kind"], "missing")
        r = json.loads(self.req("POST", "/api/check/remove", {"uids": [st["bad"][0]["uid"]]})[2])
        self.assertEqual(r["removed"], 1)
        self.assertIsNone(self.d.index.resolve("/Box/bad.bin"))
        self.assertIsNotNone(self.d.index.resolve("/Box/good.bin"))

    def test_contacts(self):
        self.login()
        self.assertEqual(json.loads(self.req("GET", "/api/contacts")[2])["items"], [])
        vcf = "\r\n".join(["BEGIN:VCARD", "VERSION:3.0", "FN:Ada Lovelace", "N:Lovelace;Ada;;;",
                           "TEL;TYPE=CELL:+44 7700 900000", "END:VCARD", "BEGIN:VCARD", "VERSION:3.0",
                           "FN:Grace Hopper", "EMAIL:grace@example.mil", "END:VCARD", ""])
        r = json.loads(self.req("POST", "/api/contacts/import?name=phone.vcf", vcf.encode())[2])
        self.assertEqual((r["added"], r["skipped"]), (2, 0))
        r = json.loads(self.req("POST", "/api/contacts/import?name=phone.vcf", vcf.encode())[2])
        self.assertEqual((r["added"], r["skipped"]), (0, 2))                       # duplicates skipped
        items = json.loads(self.req("GET", "/api/contacts")[2])["items"]
        self.assertEqual([c["name"] for c in items], ["Ada Lovelace", "Grace Hopper"])
        ada = items[0]
        ada["title"] = "Programmer"
        ada["phones"].append({"label": "work", "value": "+44 20 7946 0000"})
        self.assertEqual(self.req("POST", "/api/contacts/save", {"contact": ada})[0], 200)
        r = json.loads(self.req("POST", "/api/contacts/save", {"contact": {"first": "Alan", "last": "Turing"}})[2])
        self.assertEqual(r["contact"]["name"], "Alan Turing")
        self.assertEqual(self.req("POST", "/api/contacts/save", {"contact": {}})[0], 400)
        items = json.loads(self.req("GET", "/api/contacts")[2])["items"]
        self.assertEqual(len(items), 3)
        self.assertEqual(next(c for c in items if c["name"] == "Ada Lovelace")["title"], "Programmer")
        _, headers, body = self.req("GET", "/api/contacts/export?uids=" + ada["uid"])
        self.assertIn("text/vcard", headers["Content-Type"])
        self.assertEqual(body.count(b"BEGIN:VCARD"), 1)
        self.assertIn(b"TEL;TYPE=WORK:+44 20 7946 0000", body)
        self.req("POST", "/api/contacts/delete", {"uids": [ada["uid"]]})
        self.assertEqual(len(json.loads(self.req("GET", "/api/contacts")[2])["items"]), 2)
        # stored on the drive as one encrypted vCard file
        self.upload(self.d)
        self.assertIn(b"Alan Turing", self.read(self.d, "/Contacts/Contacts.vcf"))

    def test_direct_links_for_embedding(self):
        self.login()
        png = bytes([0x89]) + b"PNG fake image bytes" * 50
        self.write(self.d, "/Pics/cat.png", png)
        self.write(self.d, "/Pics/clip.mp4", os.urandom(50_000))
        self.upload(self.d)
        link = json.loads(self.req("POST", "/api/share", {"path": "/Pics/cat.png"})[2])
        self.assertEqual(link["direct_path"], link["path"] + "/cat.png")
        status, headers, body = self.req("GET", link["direct_path"], auth=False)
        self.assertEqual((status, headers["Content-Type"], body), (200, "image/png", png))
        self.assertIn("public", headers["Cache-Control"])
        self.assertIn("inline", headers["Content-Disposition"])
        status, headers, body = self.req("HEAD", link["direct_path"], auth=False)
        self.assertEqual((status, body), (200, b""))
        status, headers, body = self.req("GET", link["direct_path"], headers={"Range": "bytes=0-9"}, auth=False)
        self.assertEqual((status, body), (206, png[:10]))
        # the page carries preview tags pointing at the direct file
        _, _, page = self.req("GET", link["path"], headers={"X-Forwarded-Proto": "https", "Host": "127.0.0.1"}, auth=False)
        self.assertIn(b"property='og:image' content='https://127.0.0.1" + link["direct_path"].encode(), page)
        video = json.loads(self.req("POST", "/api/share", {"path": "/Pics/clip.mp4"})[2])
        _, _, page = self.req("GET", video["path"], auth=False)
        self.assertIn(b"og:video:type' content='video/mp4'", page)
        # a whole folder: /s/<id>/<path inside it>
        folder = json.loads(self.req("POST", "/api/share", {"path": "/Pics"})[2])
        self.assertEqual(folder["direct_path"], "")
        self.assertEqual(self.req("GET", folder["path"] + "/cat.png", auth=False)[2], png)
        self.assertEqual(self.req("GET", folder["path"] + "/..%2Fsecret", auth=False)[0], 404)
        # with a password there is no direct link (Discord couldn't type it)
        locked = json.loads(self.req("POST", "/api/share", {"path": "/Pics/cat.png", "password": "pw"})[2])
        self.assertEqual(locked["direct_path"], "")
        self.assertNotEqual(self.req("GET", locked["path"] + "/cat.png", auth=False)[2], png)

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
