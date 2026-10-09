"""The web dashboard: browse, preview, upload and share files, and see how the drive is doing.

Runs inside the drive process (standard library only) on http://127.0.0.1:<web_port>, or on every
network interface with `web_lan` so a phone on the same network can use it.

Sign-in: a user name and password (`web-password`, or the first visit from the computer running
the drive). Only a scrypt hash of the password is stored. A successful sign-in sets a signed session
cookie (HttpOnly, SameSite=Strict, 30 days); changing the password signs every browser out. Repeated
wrong passwords lock that address out for a while. POST requests also need an `X-DD` header, which a
page on another site can't send. Share links carry their own signed, expiring token and only give
access to the one file.
"""

import base64
import errno
import hashlib
import hmac
import ipaddress
import json
import logging
import mimetypes
import os
import posixpath
import re
import socket
import threading
import time
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .actions import default_restore_folder, snapshot_restore_ops, undelete_ops, version_put_op
from .config import Config, config_path
from .crypto import check_password, hash_password
from .index import ROOT_ID, new_uid
from .shares import Shares

log = logging.getLogger("discorddrive.web")

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
COOKIE = "dd_session"
PIECE = 1024 * 1024
SESSION_DAYS = 30
MAX_FAILURES = 5          # wrong passwords from one address before it has to wait
LOCKOUT = 60.0            # seconds, doubled for every further wrong password (up to an hour)
NOTES = "/Notes"          # where notes are kept on the drive (ordinary files, so they sync and keep versions)
NOTE_IDLE = 20.0          # a note is uploaded this long after the last autosave ("Save" uploads right away)


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def lan_addresses():
    """This computer's addresses on the local network (best effort)."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.0.2.1", 9))     # nothing is sent; this just picks the outgoing interface
            out.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in out and not ip.startswith("127."):
                out.append(ip)
    except OSError:
        pass
    return out


class WebServer:
    def __init__(self, drive, port=8765):
        self.drive = drive
        self.cfg = drive.cfg
        host = "0.0.0.0" if getattr(self.cfg, "web_lan", False) else "127.0.0.1"
        self.httpd = ThreadingHTTPServer((host, port), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.app = self
        self.port = self.httpd.server_address[1]
        self._thread = None
        self._cfg_mtime = None
        self._fail_lock = threading.Lock()
        self._failures = {}       # address -> (count, locked until)
        self.shares = Shares(drive.index)

    # ------------------------------------------------------------ lifecycle
    def start(self):
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="WebDashboard", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass

    def local_url(self):
        return f"http://127.0.0.1:{self.port}/"

    # ------------------------------------------------------------ auth
    def credentials(self):
        """(user, password hash). Picks up a password set with `web-password` while the drive runs."""
        if not getattr(self.drive, "local_test_dir", None):
            try:
                mtime = os.path.getmtime(config_path())
            except OSError:
                mtime = None
            if mtime != self._cfg_mtime:
                self._cfg_mtime = mtime
                try:
                    saved = Config.load()
                    self.cfg.web_user, self.cfg.web_password = saved.web_user, saved.web_password
                except (Exception, SystemExit) as e:
                    log.warning("Could not read the dashboard sign-in from the config: %s", e)
        return self.cfg.web_user or "", self.cfg.web_password or ""

    def set_credentials(self, user, password):
        self.cfg.web_user, self.cfg.web_password = user, hash_password(password)
        if not getattr(self.drive, "local_test_dir", None):
            saved = Config.load()
            saved.web_user, saved.web_password = self.cfg.web_user, self.cfg.web_password
            saved.save()
            self._cfg_mtime = os.path.getmtime(config_path())

    def _secret(self, purpose=b"") -> bytes:
        # Sessions also depend on the password hash, so a new password ends every session.
        extra = self.cfg.web_password.encode() if purpose == b"session" else b""
        return hashlib.sha256(b"DiscordDrive-web:" + (self.cfg.web_token or "").encode() + purpose + extra).digest()

    def new_session(self, user):
        payload = _b64(json.dumps({"u": user, "t": int(time.time())}, separators=(",", ":")).encode())
        sig = _b64(hmac.new(self._secret(b"session"), payload.encode(), hashlib.sha256).digest())
        return f"{payload}.{sig}"

    def session_user(self, value):
        """The signed-in user of a session cookie, or None."""
        user, pw = self.credentials()
        if not value or not user or not pw:
            return None
        try:
            payload, sig = value.split(".", 1)
            good = _b64(hmac.new(self._secret(b"session"), payload.encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(good, sig):
                return None
            data = json.loads(_unb64(payload))
            if data.get("u") != user or time.time() - data.get("t", 0) > SESSION_DAYS * 86400:
                return None
            return user
        except Exception:
            return None

    def locked_for(self, addr):
        with self._fail_lock:
            count, until = self._failures.get(addr, (0, 0.0))
        return max(0.0, until - time.time())

    def note_login(self, addr, ok):
        with self._fail_lock:
            if ok:
                self._failures.pop(addr, None)
                return
            count, _ = self._failures.get(addr, (0, 0.0))
            count += 1
            until = time.time() + min(3600.0, LOCKOUT * 2 ** (count - MAX_FAILURES)) if count >= MAX_FAILURES else 0.0
            self._failures[addr] = (count, until)

    def share_unlock_value(self, sid, rec):
        """Cookie proving a visitor typed the password of share `sid` (void when the password changes)."""
        msg = f"share:{sid}:{rec.get('pw', '')}".encode()
        return _b64(hmac.new(self._secret(b"share"), msg, hashlib.sha256).digest())


class _Handler(BaseHTTPRequestHandler):
    server_version = "DiscordDrive"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------ plumbing
    @property
    def app(self) -> WebServer:
        return self.server.app

    @property
    def drive(self):
        return self.server.app.drive

    def log_message(self, fmt, *args):
        log.debug("web %s - %s", self.address_string(), fmt % args)

    def _host_ok(self):
        """Refuse requests addressed to some other name (a DNS-rebinding site, for instance)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return True
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            pass
        name = socket.gethostname().lower()
        return host in (name, name + ".local", name + ".lan")

    def _cookie(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                return v
        return None

    def _authed(self):
        return self.app.session_user(self._cookie()) is not None

    def _local_request(self):
        """From the computer running the drive (the only place a first password may be set)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return self.client_address[0] in ("127.0.0.1", "::1") and host in ("127.0.0.1", "localhost", "::1")

    def _form(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 16 * 1024:
            raise ApiError(413, "request too large")
        return {k: v[-1] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}

    def _redirect(self, where, cookie=None):
        headers = {"Location": where}
        if cookie is not None:
            headers["Set-Cookie"] = cookie
        self._send(303, b"", "text/plain", headers)

    def _signin(self, error="", status=200):
        user, pw = self.app.credentials()
        if user and pw:
            mode = "login"
        elif self._local_request():
            mode = "setup"
        else:
            mode = "remote"
        self._send(status, _signin_page(mode, error).encode("utf-8"), "text/html; charset=utf-8", _PAGE_HEADERS)

    def _send(self, status, body=b"", ctype="application/json; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, separators=(",", ":")).encode("utf-8"))

    def _error(self, status, message):
        self._json({"error": message}, status)

    def _query(self):
        return {k: v[-1] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}

    def _body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1 << 20:
            raise ApiError(413, "request too large")
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            raise ApiError(400, "invalid JSON") from None

    # ------------------------------------------------------------ routing
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        try:
            if not self._host_ok():
                return self._send(421, b"Misdirected request", "text/plain")
            route = urllib.parse.urlparse(self.path).path
            if method == "POST" and route == "/login":
                return self._login()
            if method == "POST" and route == "/setup":
                return self._setup()
            if route.startswith("/s/") and method in ("GET", "POST"):
                return self._shared(route[3:], method)
            if method == "GET" and route in ("/", "/index.html", "/app.css", "/app.js", "/logo.svg"):
                if route in ("/", "/index.html") and not self._authed():
                    return self._signin()
                return self._static(route.lstrip("/") or "index.html")
            if not self._authed():
                return self._error(401, "Signed out. Reload the page to sign in.")
            if method == "POST" and self.headers.get("X-DD") != "1":
                return self._error(403, "missing X-DD header")
            fn = getattr(self, f"_{method.lower()}_{route.strip('/').replace('/', '_').replace('-', '_')}", None)
            if fn is None:
                return self._error(404, "not found")
            fn()
        except ApiError as e:
            self._error(e.status, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError as e:
            code = {errno.ENOENT: 404, errno.EEXIST: 409, errno.ENOTDIR: 400, errno.EISDIR: 400,
                    errno.ENOTEMPTY: 409, errno.ENOSPC: 507, errno.EFBIG: 413}.get(e.errno or 0, 500)
            self._error(code, os.strerror(e.errno) if e.errno else str(e))
        except Exception as e:
            log.warning("Web request %s %s failed: %s", method, self.path.split("?")[0], e, exc_info=True)
            try:
                self._error(500, str(e))
            except Exception:
                pass

    def _static(self, name):
        path = os.path.join(STATIC, name)
        try:
            with open(path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            return self._error(404, "not found")
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype, _PAGE_HEADERS)

    def _cookie_for(self, value, days=SESSION_DAYS):
        return f"{COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={int(days * 86400)}"

    def _login(self):
        addr = self.client_address[0]
        wait = self.app.locked_for(addr)
        form = self._form()
        if wait:
            return self._signin(f"Too many wrong passwords. Try again in {int(wait) + 1} seconds.", 429)
        user, pw = self.app.credentials()
        given = (form.get("user") or "").strip()
        ok = bool(user and pw) and hmac.compare_digest(given.lower(), user.lower()) \
            and check_password(form.get("password") or "", pw)
        self.app.note_login(addr, ok)
        if not ok:
            log.warning("Web dashboard: wrong user name or password from %s", addr)
            return self._signin("Wrong user name or password.", 401)
        self._redirect("/", self._cookie_for(self.app.new_session(user)))

    def _setup(self):
        user, pw = self.app.credentials()
        if (user and pw) or not self._local_request():
            return self._signin("", 403)
        form = self._form()
        name = (form.get("user") or "").strip()
        password = form.get("password") or ""
        if not name or len(name) > 64:
            return self._signin("Choose a user name.", 400)
        if len(password) < 8:
            return self._signin("Use a password of at least 8 characters.", 400)
        if password != form.get("password2"):
            return self._signin("The two passwords are different.", 400)
        self.app.set_credentials(name, password)
        log.info("Web dashboard: sign-in created for %s", name)
        self._redirect("/", self._cookie_for(self.app.new_session(name)))

    def _post_api_logout(self):
        self._send(200, b'{"ok":true}', "application/json; charset=utf-8", {"Set-Cookie": self._cookie_for("", 0)})

    # ------------------------------------------------------------ helpers
    def _node(self, path, want_dir=None):
        path = "/" + (path or "").strip("/")
        node = self.drive.index.resolve(path)
        if node is None or self.drive.fs._hidden(path):
            raise ApiError(404, f"Not found: {path}")
        if want_dir is True and not node["is_dir"]:
            raise ApiError(400, f"{path} is a file")
        if want_dir is False and node["is_dir"]:
            raise ApiError(400, f"{path} is a folder")
        return path, node

    def _entry(self, path, n):
        return {"name": n["name"], "path": path, "dir": bool(n["is_dir"]), "size": n["size"], "mtime": n["mtime"],
                "state": n["state"], "pinned": bool(n["is_pinned"])}

    def _publish(self, ops):
        self.drive.index.queue_ops(ops)
        self.drive.journal.wake()

    # ------------------------------------------------------------ status
    def _get_api_status(self):
        d = self.drive
        st = d.index.stats(max_age=2)
        devices = []
        for dev, info in sorted(d.index.devices().items(), key=lambda kv: -kv[1].get("seen", 0)):
            devices.append({"id": dev, "name": info.get("name") or "", "seen": info.get("seen", 0),
                            "me": dev == d.cfg.device_id})
        if not any(x["me"] for x in devices):
            devices.insert(0, {"id": d.cfg.device_id, "name": socket.gethostname(), "seen": time.time(), "me": True})
        scrub = d.maintenance.scrub_state() if d.maintenance else {}
        self._json({
            "version": __version__,
            "user": self.app.credentials()[0],
            "mount": d.cfg.mount_point,
            "device": d.cfg.device_id,
            "encrypted": d.crypto is not None,
            "bots": getattr(d.backend, "upload_slots", 1),
            "stats": st,
            "uploads": list(d.uploader.progress.values()) if d.uploader else [],
            "queued": len(d.uploader._pending) if d.uploader else 0,
            "saved": dict(d.uploader.stats) if d.uploader else {},
            "health": {
                "parity": bool(d.cfg.parity_enabled),
                "group": d.cfg.parity_group, "pieces": d.cfg.parity_pieces,
                "scrub": scrub, "healer": dict(d.healer.stats) if d.healer else {},
                "leader": d.maintenance.leader() if d.maintenance else False,
            },
            "devices": devices,
            "lan": [f"http://{ip}:{self.app.port}/" for ip in lan_addresses()] if d.cfg.web_lan else [],
            "snapshots": {"interval": d.cfg.snapshot_interval_hours, "keep": d.cfg.snapshot_keep_days},
        })

    # ------------------------------------------------------------ browsing
    def _get_api_list(self):
        path, node = self._node(self._query().get("path"), want_dir=True)
        items = []
        for c in self.drive.index.children(node["id"]):
            cpath = posixpath.join(path, c["name"])
            if not self.drive.fs._hidden(cpath):
                items.append(self._entry(cpath, c))
        items.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        self._json({"path": path, "items": items})

    def _get_api_search(self):
        q = (self._query().get("q") or "").strip()
        if len(q) < 2:
            return self._json({"items": []})
        idx = self.drive.index
        rows = idx._all("SELECT * FROM nodes WHERE id != ? AND name LIKE ? ESCAPE '\\' ORDER BY is_dir DESC, name LIMIT 200",
                        (ROOT_ID, "%" + re.sub(r"([%_\\])", r"\\\1", q) + "%"))
        items = []
        for r in rows:
            p = idx.path_of(r["id"])
            if not self.drive.fs._hidden(p):
                items.append(self._entry(p, r))
        self._json({"items": items})

    def _get_api_file(self):
        q = self._query()
        path, node = self._node(q.get("path"), want_dir=False)
        self._stream(node, download=q.get("dl") == "1")

    def _stream(self, node, download=False):
        total = node["size"]
        on = self.drive.fs.open_nodes.get(node["id"])
        staging = self.drive.fs.staging_path(node["id"])
        if on is not None or os.path.exists(staging):
            try:
                total = os.path.getsize(staging)
            except OSError:
                pass
        start, end = 0, total - 1
        status = 200
        rng = self.headers.get("Range") or ""
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        if m and total > 0:
            a, b = m.groups()
            if a == "" and b:
                start = max(0, total - int(b))
            else:
                start = int(a or 0)
                end = min(total - 1, int(b)) if b else total - 1
            if start > end or start >= total:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        ctype = mimetypes.guess_type(node["name"])[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.send_header("Cache-Control", "private, max-age=60")
        self.send_header("X-Content-Type-Options", "nosniff")
        if ctype.split(";")[0] in _ACTIVE_TYPES:
            # A stored web page or SVG must not run scripts with the dashboard's rights.
            self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; img-src 'self' data:; "
                                                        "style-src 'unsafe-inline'")
        disp = "attachment" if download else "inline"
        self.send_header("Content-Disposition", f"{disp}; filename*=UTF-8''{urllib.parse.quote(node['name'])}")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.end_headers()
        if self.command == "HEAD":
            return
        pos = start
        while pos <= end:
            n = min(PIECE, end - pos + 1)
            data = self.drive.fs.read_file(node["id"], pos, n)
            if not data:
                break
            self.wfile.write(data)
            pos += len(data)

    # ------------------------------------------------------------ changing
    def _post_api_upload(self):
        path = "/" + (self._query().get("path") or "").strip("/")
        parent, name = posixpath.split(path)
        if not name:
            raise ApiError(400, "missing file name")
        self._node(parent, want_dir=True)
        fs = self.drive.fs
        remaining = int(self.headers.get("Content-Length") or 0)
        fh = fs.create(path, 0o644)
        offset = 0
        try:
            while remaining > 0:
                data = self.rfile.read(min(PIECE, remaining))
                if not data:
                    break
                fs.write(path, data, offset, fh)
                offset += len(data)
                remaining -= len(data)
        finally:
            fs.release(path, fh)
        if remaining:
            raise ApiError(400, "upload was cut off")
        save = self._query().get("save")
        node = self.drive.index.resolve(path)
        if save in ("now", "later") and node is not None and self.drive.uploader is not None:
            # notes: autosaves wait until typing pauses; "Save" sends it to Discord right away
            self.drive.uploader.enqueue(node["id"], delay=0 if save == "now" else NOTE_IDLE)
        self._json({"ok": True, "path": path, "size": offset, "mtime": node["mtime"] if node else None})

    def _get_api_zip(self):
        path, node = self._node(self._query().get("path"), want_dir=True)
        self._zip(node, path)

    def _zip(self, node, path):
        """A folder as one .zip download (streamed: nothing is stored on the way)."""
        idx = self.drive.index
        name = (node["name"] or "DiscordDrive") + ".zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        out = _Unseekable(self.wfile)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            todo = [(node, "")]
            while todo:
                n, rel = todo.pop()
                for c in idx.children(n["id"]):
                    crel = f"{rel}{c['name']}"
                    if self.drive.fs._hidden(posixpath.join(path, crel)):
                        continue
                    if c["is_dir"]:
                        zf.writestr(zipfile.ZipInfo(crel + "/", time.localtime(c["mtime"])[:6]), b"")
                        todo.append((c, crel + "/"))
                        continue
                    info = zipfile.ZipInfo(crel, time.localtime(max(c["mtime"], 315532800))[:6])
                    with zf.open(info, "w", force_zip64=c["size"] > 2 ** 31) as f:
                        pos = 0
                        while pos < c["size"]:
                            data = self.drive.fs.read_file(c["id"], pos, PIECE)
                            if not data:
                                break
                            f.write(data)
                            pos += len(data)

    def _post_api_copy(self):
        """Duplicate a file (pieces the drive already stores are reused, so this uploads nothing new)."""
        body = self._body_json()
        src, node = self._node(body.get("from"), want_dir=False)
        dst = "/" + (body.get("to") or "").strip("/")
        if self.drive.index.resolve(dst) is not None:
            raise ApiError(409, "Something with that name already exists")
        fs = self.drive.fs
        fh = fs.create(dst, 0o644)
        try:
            pos = 0
            while pos < node["size"]:
                data = fs.read_file(node["id"], pos, PIECE)
                if not data:
                    break
                fs.write(dst, data, pos, fh)
                pos += len(data)
        finally:
            fs.release(dst, fh)
        self._json({"ok": True, "path": dst})

    def _post_api_mkdir(self):
        path = "/" + (self._body_json().get("path") or "").strip("/")
        self.drive.fs.mkdir(path, 0o755)
        self._json({"ok": True, "path": path})

    def _post_api_move(self):
        body = self._body_json()
        src, _ = self._node(body.get("from"))
        dst = "/" + (body.get("to") or "").strip("/")
        if self.drive.index.resolve(dst) is not None:
            raise ApiError(409, "Something with that name already exists")
        if dst.lower().startswith(src.lower() + "/"):
            raise ApiError(400, "A folder can't be moved into itself")
        self._node(posixpath.dirname(dst), want_dir=True)
        self.drive.fs.rename(src, dst)
        self._json({"ok": True, "path": dst})

    def _post_api_delete(self):
        path, node = self._node(self._body_json().get("path"))
        if node["id"] == ROOT_ID:
            raise ApiError(400, "The drive itself can't be deleted")
        fs = self.drive.fs

        def remove(p, n):
            if n["is_dir"]:
                for c in self.drive.index.children(n["id"]):
                    remove(posixpath.join(p, c["name"]), c)
                fs.rmdir(p)
            else:
                fs.unlink(p)
        remove(path, node)
        self._json({"ok": True})

    def _post_api_pin(self):
        body = self._body_json()
        path, node = self._node(body.get("path"))
        on = bool(body.get("on"))
        d = self.drive
        d.index.set_pinned(node["id"], pinned=on, recursive=True)
        if on:
            threading.Thread(target=d.cache.prefetch_node, args=(node["id"],), name="Pin", daemon=True).start()
        else:
            d.cache.free_space(node_id=node["id"], force=True)
        self._json({"ok": True})

    def _share_json(self, sid, rec):
        node = self.drive.index.get_by_uid(rec["u"])
        return {"id": sid, "path": f"/s/{sid}",
                "lan": [f"http://{ip}:{self.app.port}/s/{sid}" for ip in lan_addresses()] if self.drive.cfg.web_lan else [],
                "item": self.drive.index.path_of(node["id"]) if node else None, "dir": rec.get("d", False),
                "created": rec.get("c"), "expires": rec.get("e"), "password": bool(rec.get("pw")),
                "download": rec.get("dl", True), "views": rec.get("v", 0)}

    def _post_api_share(self):
        body = self._body_json()
        path, node = self._node(body.get("path"))
        if node["id"] == ROOT_ID:
            raise ApiError(400, "Share a folder or file, not the whole drive")
        hours = body.get("hours", 24 * 7)
        sid, rec = self.app.shares.create(node["uid"], node["is_dir"], hours=hours,
                                          password=str(body.get("password") or ""), download=body.get("download", True))
        self._json(self._share_json(sid, rec))

    def _get_api_shares(self):
        items = [self._share_json(sid, rec) for sid, rec in self.app.shares.all().items()]
        items.sort(key=lambda x: -(x["created"] or 0))
        self._json({"items": items})

    def _post_api_shares_update(self):
        body = self._body_json()
        rec = self.app.shares.update(str(body.get("id")), hours=body.get("hours"),
                                     password=body.get("password"), download=body.get("download"))
        if rec is None:
            raise ApiError(404, "That link no longer exists")
        self._json(self._share_json(str(body.get("id")), rec))

    def _post_api_shares_revoke(self):
        if not self.app.shares.revoke(str(self._body_json().get("id"))):
            raise ApiError(404, "That link no longer exists")
        self._json({"ok": True})

    # ------------------------------------------------------------ notes
    def _get_api_notes(self):
        idx = self.drive.index
        folder = idx.resolve(NOTES)
        items = []
        if folder is not None and folder["is_dir"]:
            for c in idx.children(folder["id"]):
                if c["is_dir"]:
                    continue
                try:
                    head = self.drive.fs.read_file(c["id"], 0, 600).decode("utf-8", "replace")
                except Exception:
                    head = ""
                title, _, rest = c["name"].rpartition(".") if c["name"].lower().endswith((".md", ".txt")) else (c["name"], "", "")
                items.append({"path": posixpath.join(NOTES, c["name"]), "name": c["name"], "title": title or c["name"],
                              "mtime": c["mtime"], "size": c["size"], "state": c["state"],
                              "snippet": " ".join(head.split())[:140]})
        items.sort(key=lambda n: -n["mtime"])
        self._json({"folder": NOTES, "items": items})

    # ------------------------------------------------------------ history
    def _get_api_versions(self):
        path, node = self._node(self._query().get("path"), want_dir=False)
        rows = self.drive.index.versions_for(node["uid"])
        self._json({"path": path, "current": {"size": node["size"], "mtime": node["mtime"]},
                    "versions": [{"n": i, "at": v["superseded"], "size": v["size"], "reason": v["reason"]}
                                 for i, v in enumerate(rows, 1)]})

    def _post_api_versions_restore(self):
        body = self._body_json()
        path, node = self._node(body.get("path"), want_dir=False)
        idx = self.drive.index
        rows = idx.versions_for(node["uid"])
        n = int(body.get("n") or 0)
        if not 1 <= n <= len(rows):
            raise ApiError(400, "no such version")
        parent_uid = idx.get(node["parent"])["uid"]
        if body.get("copy"):
            stem, ext = os.path.splitext(node["name"])
            name = f"{stem} (version {n}){ext}"
            op = version_put_op(idx, rows[n - 1], new_uid(), parent_uid, name)
        else:
            op = version_put_op(idx, rows[n - 1], node["uid"], parent_uid, node["name"])
        self._publish([op])
        self._json({"ok": True})

    def _get_api_deleted(self):
        rows = self.drive.index.deleted_files("/")
        self._json({"items": [{"uid": v["uid"], "path": v["path"], "size": v["size"], "at": v["superseded"]}
                              for v in rows[:5000]]})

    def _deleted_by_uid(self, body):
        """Deleted files picked by uid ({"uids": [...]}), or one by path ({"path": ...})."""
        rows = self.drive.index.deleted_files("/")
        if body.get("uids"):
            wanted = set(map(str, body["uids"]))
            return [v for v in rows if v["uid"] in wanted]
        path = "/" + (body.get("path") or "").strip("/")
        return [v for v in rows if (v["path"] or "").lower() == path.lower()][:1]

    def _post_api_undelete(self):
        idx = self.drive.index
        rows = self._deleted_by_uid(self._body_json())
        if not rows:
            raise ApiError(404, "Those files are no longer kept")
        self._publish(undelete_ops(idx, rows))
        self._json({"ok": True, "count": len(rows)})

    def _post_api_purge(self):
        rows = self._deleted_by_uid(self._body_json())
        n = self.drive.index.purge_deleted([v["uid"] for v in rows])
        self.drive.journal.wake()
        self._json({"ok": True, "count": n})

    # ------------------------------------------------------------ snapshots
    def _get_api_snapshots(self):
        self._json({"items": [{"id": s["id"], "at": s["at"], "label": s["label"], "files": s["files"],
                               "bytes": s["bytes"], "keep_until": s["keep_until"]}
                              for s in self.drive.index.snapshots()]})

    def _get_api_snapshot(self):
        q = self._query()
        sid, path = q.get("id"), "/" + (q.get("path") or "").strip("/")
        entries = self.drive.index.snapshot_entries(sid, path)
        depth = 0 if path == "/" else path.count("/")
        items = [{"name": posixpath.basename(e["path"]), "path": e["path"], "dir": e["is_dir"], "size": e["size"],
                  "mtime": e["mtime"]} for e in entries if e["path"].count("/") == depth + 1]
        items.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        self._json({"path": path, "items": items})

    def _post_api_snapshots_create(self):
        label = str(self._body_json().get("label") or "")[:60]
        sid = self.drive.journal.create_snapshot(label or "Manual", float(self.drive.cfg.snapshot_keep_days or 0))
        self._json({"ok": True, "id": sid})

    def _post_api_snapshots_restore(self):
        body = self._body_json()
        snap = next((s for s in self.drive.index.snapshots() if s["id"] == body.get("id")), None)
        if snap is None:
            raise ApiError(404, "no such snapshot")
        target = default_restore_folder(snap)
        ops, files = snapshot_restore_ops(self.drive.index, snap["id"], body.get("path") or "/", target)
        if not ops:
            raise ApiError(404, "nothing to restore there")
        self._publish(ops)
        self._json({"ok": True, "files": files, "folder": target})

    # ------------------------------------------------------------ share links
    def _shared(self, rest, method):
        sid, _, tail = rest.partition("/")
        rec = self.app.shares.get(sid)
        root = self.drive.index.get_by_uid(rec["u"]) if rec else None
        if root is None:
            return self._send(404, _share_message("This link has expired", "Ask for a new one.").encode(),
                              "text/html; charset=utf-8", _SHARE_HEADERS)
        if rec.get("pw"):
            if method == "POST":
                addr = "share:" + self.client_address[0]
                wait = self.app.locked_for(addr)
                ok = not wait and self.app.shares.password_ok(rec, self._form().get("password"))
                self.app.note_login(addr, ok)
                if not ok:
                    msg = f"Too many tries. Wait {int(wait) + 1} seconds." if wait else "That password isn't right."
                    return self._send(401, _share_password(sid, rec, msg).encode(), "text/html; charset=utf-8",
                                      _SHARE_HEADERS)
                cookie = f"dds_{sid}={self.app.share_unlock_value(sid, rec)}; Path=/s/{sid}; HttpOnly; SameSite=Lax; Max-Age=43200"
                return self._redirect(f"/s/{sid}", cookie)
            jar = {k.strip(): v for k, _, v in (p.partition("=") for p in (self.headers.get("Cookie") or "").split(";"))}
            if not hmac.compare_digest(jar.get(f"dds_{sid}", ""), self.app.share_unlock_value(sid, rec)):
                return self._send(200, _share_password(sid, rec).encode(), "text/html; charset=utf-8", _SHARE_HEADERS)
        elif method == "POST":
            return self._redirect(f"/s/{sid}")
        rel = (self._query().get("p") or "").strip("/")
        node, shown = self._share_target(root, rel)
        if node is None:
            return self._send(404, _share_message("Not found", "That file isn't in this share.").encode(),
                              "text/html; charset=utf-8", _SHARE_HEADERS)
        if tail == "raw" and not node["is_dir"]:
            if self._query().get("dl") == "1" and not rec.get("dl", True):
                return self._send(403, b"Downloading is turned off for this link.", "text/plain; charset=utf-8")
            return self._stream(node, download=self._query().get("dl") == "1")
        if tail == "zip" and node["is_dir"]:
            if not rec.get("dl", True):
                return self._send(403, b"Downloading is turned off for this link.", "text/plain; charset=utf-8")
            return self._zip(node, shown)
        if not rel:
            self.app.shares.viewed(sid)
        children = []
        if node["is_dir"]:
            for c in self.drive.index.children(node["id"]):
                if not self.drive.fs._hidden(posixpath.join(shown, c["name"])):
                    children.append(c)
            children.sort(key=lambda c: (not c["is_dir"], c["name"].lower()))
        text = None
        if not node["is_dir"] and _kind(node["name"]) == "text" and node["size"] <= 2 * 2 ** 20:
            text = self.drive.fs.read_file(node["id"], 0, 256 * 1024).decode("utf-8", "replace")
        html = _share_page(sid, rec, root, node, rel, children, text)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", _SHARE_HEADERS)

    def _share_target(self, root, rel):
        """The node at `rel` inside a shared item (never outside it), and its path on the drive."""
        idx = self.drive.index
        node = root
        shown = idx.path_of(root["id"])
        for part in [p for p in rel.split("/") if p]:
            if part in (".", "..") or not node["is_dir"]:
                return None, None
            node = idx.lookup(node["id"], part)
            if node is None:
                return None, None
            shown = posixpath.join(shown, node["name"])
        if self.drive.fs._hidden(shown):
            return None, None
        return node, shown

class _Unseekable:
    """A response stream for zipfile: write-only, so it adds data descriptors instead of seeking back."""

    def __init__(self, raw):
        self._raw = raw
        self._pos = 0

    def write(self, data):
        self._raw.write(data)
        self._pos += len(data)
        return len(data)

    def tell(self):
        return self._pos

    def flush(self):
        self._raw.flush()

    def seekable(self):
        return False


_PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
                               "style-src 'self'; script-src 'self'; frame-src 'self'; object-src 'none'; "
                               "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


def _signin_page(mode, error=""):
    err = f'<p class="err" role="alert">{_esc(error)}</p>' if error else ""
    if mode == "login":
        body = f"""<h1>Sign in</h1>
  <p class="muted">DiscordDrive</p>
  {err}
  <form method="post" action="/login">
    <label>User name<input name="user" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus></label>
    <label>Password<input name="password" type="password" autocomplete="current-password" required></label>
    <button class="btn" type="submit">Sign in</button>
  </form>"""
    elif mode == "setup":
        body = f"""<h1>Create your sign-in</h1>
  <p class="muted">Pick a user name and password for the dashboard. You need them on every browser
  and phone you open it on. Change them later with <code>web-password</code>.</p>
  {err}
  <form method="post" action="/setup">
    <label>User name<input name="user" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus></label>
    <label>Password<input name="password" type="password" autocomplete="new-password" minlength="8" required></label>
    <label>Password again<input name="password2" type="password" autocomplete="new-password" minlength="8" required></label>
    <button class="btn" type="submit">Create and sign in</button>
  </form>"""
    else:
        body = """<h1>Set up a sign-in first</h1>
  <p class="muted">No user name and password are set for this dashboard yet. Set them on the computer
  running the drive: open the dashboard there, or in the DiscordDrive menu choose
  <b>Web dashboard</b>, or run <code>web-password</code>.</p>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark"><title>DiscordDrive</title>
<link rel="icon" href="/logo.svg" type="image/svg+xml"><link rel="stylesheet" href="/app.css"></head>
<body class="signin"><main>
  <img src="/logo.svg" alt="" width="40" height="40">
  {body}
</main></body></html>"""


_ACTIVE_TYPES = {"text/html", "application/xhtml+xml", "image/svg+xml", "text/xml", "application/xml"}


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def _human(n):
    n = float(n or 0)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024


_KINDS = {
    "image": "jpg jpeg png gif webp avif bmp svg heic",
    "video": "mp4 m4v webm mov mkv",
    "audio": "mp3 m4a aac flac wav ogg opus",
    "pdf": "pdf",
    "text": "txt md log csv json xml yml yaml ini conf cfg py js ts css sh bat ps1 c h cpp rs go java toml srt",
}


def _kind(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return next((k for k, exts in _KINDS.items() if ext in exts.split()), "file")


_SHARE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; media-src 'self'; "
                               "frame-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'self'",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
}

_SHARE_STYLE = """
*{box-sizing:border-box}
:root{--bg:#fbfbfa;--panel:#fff;--ink:#141414;--muted:#6b6b6b;--faint:#a1a1a1;--line:#ebebe8;--hover:#f3f3f1;--accent:#e5484d}
@media (prefers-color-scheme:dark){:root{--bg:#0f0f10;--panel:#151516;--ink:#ececec;--muted:#9b9b9b;--faint:#626262;
--line:#232325;--hover:#1b1b1d;--accent:#ff6369}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI Variable Text",
"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
main{width:min(880px,calc(100% - 32px));margin:0 auto;padding:40px 0 64px}
.top{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:13px;margin-bottom:28px}
.top img{width:20px;height:20px;border-radius:5px}
h1{font-size:22px;font-weight:600;letter-spacing:-.015em;margin:0 0 4px;word-break:break-word}
.m{color:var(--muted);margin:0 0 24px;font-size:14px}
.crumbs{font-size:14px;color:var(--muted);margin:-14px 0 20px}.crumbs a{text-decoration:none}.crumbs a:hover{color:var(--ink)}
.pv{display:grid;place-items:center;background:var(--hover);border-radius:10px;overflow:hidden;margin-bottom:20px;min-height:120px}
.pv img,.pv video{display:block;max-width:100%;max-height:72vh}.pv audio{width:calc(100% - 32px);margin:28px 16px}
.pv iframe{width:100%;height:78vh;border:0;background:#fff}
.pv pre{width:100%;max-height:72vh;overflow:auto;margin:0;padding:18px 20px;font:13px/1.6 ui-monospace,"SF Mono",Consolas,monospace;
white-space:pre-wrap;word-break:break-word}
.btns{display:flex;flex-wrap:wrap;gap:8px}
.b{display:inline-flex;align-items:center;height:38px;padding:0 16px;border-radius:8px;background:var(--ink);color:var(--bg);
text-decoration:none;font-weight:500;border:0;font-size:14px;cursor:pointer}
.b.g{background:none;color:var(--ink);border:1px solid var(--line)}
.list{border-top:1px solid var(--line);margin-bottom:24px}
.row{display:flex;align-items:center;gap:12px;min-height:46px;padding:0 6px;border-bottom:1px solid var(--line);text-decoration:none}
.row:hover{background:var(--hover)}.row .n{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .s{color:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.ic{width:18px;height:18px;flex:none;color:var(--muted)}
.lock{max-width:360px;margin:12vh auto 0}
.lock input{display:block;width:100%;height:40px;margin:6px 0 14px;padding:0 12px;border:1px solid var(--line);border-radius:8px;
background:var(--panel);color:var(--ink);font-size:15px;outline:none}
.lock label{color:var(--muted);font-size:13px}.lock .b{width:100%;justify-content:center}
.err{color:var(--accent);font-size:14px}
.f{margin-top:48px;color:var(--faint);font-size:12px}
"""

_ICON_FOLDER = ('<svg class="ic" viewBox="0 0 20 20" fill="currentColor" fill-opacity=".18" stroke="currentColor" '
                'stroke-width="1.5"><path d="M2.5 5.5a1.5 1.5 0 0 1 1.5-1.5h3.6l1.6 1.8H16a1.5 1.5 0 0 1 1.5 1.5v7.7A1.5 '
                '1.5 0 0 1 16 16.5H4a1.5 1.5 0 0 1-1.5-1.5z"/></svg>')
_ICON_FILE = ('<svg class="ic" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" '
              'stroke-linejoin="round"><path d="M5 2.5h6.5L15 6v11.5H5z"/><path d="M11.5 2.5V6H15"/></svg>')


def _share_shell(title, body):
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport "
            f"content='width=device-width,initial-scale=1'><meta name=robots content=noindex><title>{_esc(title)}</title>"
            f"<link rel=icon href='/logo.svg'><style>{_SHARE_STYLE}</style></head><body><main>"
            f"<div class=top><img src='/logo.svg' alt=''>Shared with you</div>{body}"
            f"<p class=f>Shared from DiscordDrive</p></main></body></html>")


def _share_message(title, text):
    return _share_shell(title, f"<h1>{_esc(title)}</h1><p class=m>{_esc(text)}</p>")


def _share_password(sid, rec, error=""):
    err = f"<p class=err role=alert>{_esc(error)}</p>" if error else ""
    return _share_shell("Password needed", f"""<form class=lock method=post action="/s/{sid}">
<h1>Password needed</h1><p class=m>Whoever shared this protected it with a password.</p>{err}
<label>Password<input name=password type=password autocomplete=current-password required autofocus></label>
<button class=b type=submit>Open</button></form>""")


def _until(rec):
    if not rec.get("e"):
        return "no expiry"
    return "link works until " + time.strftime("%d %b %Y, %H:%M", time.localtime(rec["e"]))


def _share_page(sid, rec, root, node, rel, children, text):
    base = f"/s/{sid}"
    q = (lambda r: "?" + urllib.parse.urlencode({"p": r}) if r else "")
    crumbs = ""
    if rel:
        parts = rel.split("/")
        links = [f"<a href='{base}'>{_esc(root['name'])}</a>"]
        for i, part in enumerate(parts[:-1]):
            links.append(f"<a href='{base}{q('/'.join(parts[:i + 1]))}'>{_esc(part)}</a>")
        crumbs = f"<p class=crumbs>{' / '.join(links)}</p>"
    name = _esc(node["name"])
    if node["is_dir"]:
        rows = []
        for c in children:
            crel = f"{rel}/{c['name']}".strip("/")
            icon = _ICON_FOLDER if c["is_dir"] else _ICON_FILE
            size = "" if c["is_dir"] else _human(c["size"])
            rows.append(f"<a class=row href='{base}{q(crel)}'>{icon}<span class=n>{_esc(c['name'])}</span>"
                        f"<span class=s>{size}</span></a>")
        listing = f"<div class=list>{''.join(rows)}</div>" if rows else "<p class=m>This folder is empty.</p>"
        files = sum(1 for c in children if not c["is_dir"])
        btn = f"<div class=btns><a class=b href='{base}/zip{q(rel)}'>Download all (ZIP)</a></div>" if rec.get("dl", True) else ""
        return _share_shell(node["name"], f"{crumbs}<h1>{name}</h1><p class=m>Folder &middot; {files} file(s) &middot; "
                                          f"{_until(rec)}</p>{listing}{btn}")
    raw = f"{base}/raw{q(rel)}"
    kind = _kind(node["name"])
    if kind == "image":
        pv = f"<div class=pv><img src='{raw}' alt='{name}'></div>"
    elif kind == "video":
        pv = f"<div class=pv><video src='{raw}' controls playsinline preload=metadata></video></div>"
    elif kind == "audio":
        pv = f"<div class=pv><audio src='{raw}' controls preload=metadata></audio></div>"
    elif kind == "pdf":
        pv = f"<div class=pv><iframe src='{raw}' title='{name}'></iframe></div>"
    elif text is not None:
        pv = f"<div class=pv><pre>{_esc(text)}</pre></div>"
    else:
        pv = ""
    sep = "&" if rel else "?"
    btns = []
    if rec.get("dl", True):
        btns.append(f"<a class=b href='{raw}{sep}dl=1'>Download</a>")
    if rel:
        up = "/".join(rel.split("/")[:-1])
        btns.append(f"<a class='b g' href='{base}{q(up)}'>Back to the folder</a>")
    if not rec.get("dl", True) and not pv:
        btns.append("<span class=m>This kind of file can't be shown here, and downloading is turned off.</span>")
    return _share_shell(node["name"], f"{crumbs}<h1>{name}</h1><p class=m>{_human(node['size'])} &middot; {_until(rec)}</p>"
                                      f"{pv}<div class=btns>{''.join(btns)}</div>")
