"""The web dashboard: browse, preview, upload and share files, and see how the drive is doing.

Runs inside the drive process (standard library only) on http://127.0.0.1:<web_port>, or on every
network interface with `web_lan` so a phone on the same network can use it.

Sign-in: every request needs a session cookie, which `/login?t=<web_token>` sets (the menu and the
`web` command print that link). POST requests also need an `X-DD` header, which a page on another
site can't send, and the cookie is SameSite=Strict. Share links carry their own signed, expiring
token and only give access to the one file.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .actions import default_restore_folder, snapshot_restore_ops, version_put_op
from .index import ROOT_ID, new_uid

log = logging.getLogger("discorddrive.web")

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
COOKIE = "dd_session"
PIECE = 1024 * 1024


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

    def local_url(self, with_token=False):
        url = f"http://127.0.0.1:{self.port}/"
        return url + f"login?t={self.cfg.web_token}" if with_token else url

    # ------------------------------------------------------------ auth
    def _secret(self) -> bytes:
        return hashlib.sha256(b"DiscordDrive-web:" + (self.cfg.web_token or "").encode()).digest()

    def session_value(self):
        return _b64(hmac.new(self._secret(), b"session", hashlib.sha256).digest())

    def token_ok(self, token):
        return bool(self.cfg.web_token) and hmac.compare_digest(str(token or ""), self.cfg.web_token)

    def share_token(self, uid, hours):
        payload = json.dumps({"u": uid, "e": int(time.time() + hours * 3600)}, separators=(",", ":")).encode()
        sig = hmac.new(self._secret(), b"share:" + payload, hashlib.sha256).digest()[:16]
        return f"{_b64(payload)}.{_b64(sig)}"

    def check_share(self, token):
        try:
            p, s = token.split(".", 1)
            payload = _unb64(p)
            good = hmac.new(self._secret(), b"share:" + payload, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(good, _unb64(s)):
                return None
            data = json.loads(payload)
            if data["e"] < time.time():
                return None
            return data
        except Exception:
            return None


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
        c = self._cookie()
        return c is not None and hmac.compare_digest(c, self.app.session_value())

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
            if method == "GET" and route == "/login":
                return self._login()
            if method == "GET" and route.startswith("/s/"):
                return self._shared(route[3:])
            if method == "GET" and route in ("/", "/index.html", "/app.css", "/app.js", "/logo.svg"):
                if route in ("/", "/index.html") and not self._authed():
                    return self._static("signin.html")
                return self._static(route.lstrip("/") or "index.html")
            if not self._authed():
                return self._error(401, "Open the dashboard link from the DiscordDrive menu to sign in.")
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
        self._send(200, body, ctype, {
            "Content-Security-Policy": "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; "
                                       "style-src 'self'; script-src 'self'; frame-src 'self'; object-src 'none'; "
                                       "base-uri 'none'; frame-ancestors 'none'",
        })

    def _login(self):
        if not self.app.token_ok(self._query().get("t")):
            return self._static("signin.html")
        self._send(302, b"", "text/plain", {
            "Location": "/",
            "Set-Cookie": f"{COOKIE}={self.app.session_value()}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000",
        })

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
        j = self.drive.journal
        for i in range(0, len(ops), 300):
            j.post_ops(ops[i:i + 300])
        j.wake()

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
        self._json({"ok": True, "path": path, "size": offset})

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

    def _post_api_share(self):
        body = self._body_json()
        path, node = self._node(body.get("path"), want_dir=False)
        hours = min(24 * 30, max(1.0, float(body.get("hours") or 24)))
        token = self.app.share_token(node["uid"], hours)
        self._json({"token": token, "path": f"/s/{token}", "expires": time.time() + hours * 3600,
                    "lan": [f"http://{ip}:{self.app.port}/s/{token}" for ip in lan_addresses()]
                    if self.drive.cfg.web_lan else []})

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
        self._json({"items": [{"path": v["path"], "size": v["size"], "at": v["superseded"]} for v in rows[:1000]]})

    def _post_api_undelete(self):
        path = "/" + (self._body_json().get("path") or "").strip("/")
        idx = self.drive.index
        matches = [v for v in idx.deleted_files(path) if (v["path"] or "").lower() == path.lower()]
        if not matches:
            raise ApiError(404, "That file is no longer kept")
        v = matches[0]
        self._publish([version_put_op(idx, v, v["uid"], v["parent_uid"], v["name"])])
        self._json({"ok": True})

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
    def _shared(self, rest):
        token, _, tail = rest.partition("/")
        data = self.app.check_share(token)
        node = self.drive.index.get_by_uid(data["u"]) if data else None
        if node is None or node["is_dir"]:
            return self._send(404, _SHARE_GONE.encode(), "text/html; charset=utf-8")
        if tail == "raw":
            return self._stream(node, download=self._query().get("dl") == "1")
        html = _SHARE_PAGE.format(name=_esc(node["name"]), size=_human(node["size"]), token=token,
                                  expires=time.strftime("%d %b %Y, %H:%M", time.localtime(data["e"])))
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8",
                   {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'"})


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


_SHARE_STYLE = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:#fbfbfa;color:#111}main{width:min(420px,calc(100% - 32px))}
.n{font-size:20px;font-weight:600;word-break:break-word;margin:0 0 4px}.m{color:#6f6f6f;margin:0 0 28px}
a.b{display:inline-block;background:#111;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px}
.f{margin-top:48px;color:#a3a3a3;font-size:12px}
@media (prefers-color-scheme:dark){body{background:#0e0e0f;color:#ececec}.m{color:#9a9a9a}
a.b{background:#ececec;color:#111}}
"""
_SHARE_PAGE = ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,"
               "initial-scale=1'><title>{name}</title><style>" + _SHARE_STYLE.replace("{", "{{").replace("}", "}}") +
               "</style><main><p class=n>{name}</p><p class=m>{size} &middot; link works until {expires}</p>"
               "<a class=b href='/s/{token}/raw?dl=1'>Download</a>"
               "<p class=f>Shared from DiscordDrive</p></main></html>")
_SHARE_GONE = ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,"
               "initial-scale=1'><title>Link expired</title><style>" + _SHARE_STYLE +
               "</style><main><p class=n>This link has expired</p><p class=m>Ask for a new one.</p></main></html>")
