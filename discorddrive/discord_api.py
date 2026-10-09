"""Discord REST client supporting curl.exe (standard on Windows 10/11) and urllib.

Only the handful of endpoints DiscordDrive needs are implemented. The bot never
connects to the gateway, so no privileged intents or background connections are required.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from . import __version__

log = logging.getLogger("discorddrive.discord")

API_BASE = "https://discord.com/api/v10"
USER_AGENT = f"DiscordDrive (https://github.com/xo907/discord-drive, {__version__})"


def _ram_tmpdir():
    """A RAM-backed temp folder on Linux, so uploads keep working when the disk is full."""
    d = "/dev/shm"
    if os.name == "posix" and os.path.isdir(d) and os.access(d, os.W_OK):
        return d
    return None


_TMPDIR = _ram_tmpdir()


class DiscordError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Discord HTTP {status}: {message}")
        self.status = status


def _encode_multipart(fields, files):
    """fields: {name: (bytes, content_type)}; files: {name: (filename, bytes, content_type)}"""
    boundary = uuid.uuid4().hex
    parts = []
    for name, (value, ctype) in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode()
        )
        parts.append(value)
        parts.append(b"\r\n")
    for name, (filename, value, ctype) in files.items():
        safe = filename.replace('"', "_")
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{safe}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode()
        )
        parts.append(value)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class DiscordAPI:
    def __init__(self, token: str, timeout: float = 600.0, retries: int = 8):
        token = (token or "").strip()
        if token.lower().startswith("bot "):
            token = token[4:].strip()
        self.token = token
        self.timeout = timeout
        self.retries = retries
        self.curl_bin = shutil.which("curl") or shutil.which("curl.exe")
        self.has_curl = bool(self.curl_bin)

    # ------------------------------------------------------------------ core
    def _send_curl(self, method, url, body=None, headers=None, auth=True, multipart_file=None):
        cmd = [self.curl_bin or "curl", "-s", "-S", "-X", method, "--max-time", str(int(self.timeout))]
        temp_files = []
        try:
            # Only two tiny files (headers); request data goes through stdin, never to disk.
            with tempfile.NamedTemporaryFile(delete=False, dir=_TMPDIR) as hf:
                hdr_path = hf.name
            temp_files.append(hdr_path)
            cmd.extend(["-D", hdr_path])
            cmd.extend(["-w", "\n__HTTP_STATUS__:%{http_code}"])

            req_headers = {"User-Agent": USER_AGENT}
            if auth and self.token:
                req_headers["Authorization"] = f"Bot {self.token}"
            if headers:
                req_headers.update(headers)

            # Pass headers through a file so the bot token never appears in the
            # process list (command lines are visible to other local users).
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", newline="\n", dir=_TMPDIR) as rf:
                for k, v in req_headers.items():
                    rf.write(f"{k}: {v}\n")
                req_hdr_path = rf.name
            temp_files.append(req_hdr_path)
            cmd.extend(["-H", f"@{req_hdr_path}"])

            stdin_data = None
            if multipart_file:
                # tuple of (field_name, filename, data_bytes, optional_payload_json)
                field_name, filename, data_bytes, payload_json = multipart_file
                stdin_data = data_bytes
                # curl's -F syntax treats ; , and " specially inside the filename
                safe_name = "".join("_" if ch in '";,\r\n' else ch for ch in filename)
                cmd.extend(["-F", f"{field_name}=@-;filename={safe_name}"])
                if payload_json:
                    # --form-string: no @file / <file / ;type= interpretation of the value
                    cmd.extend(["--form-string", f"payload_json={payload_json}"])
            elif body is not None:
                if isinstance(body, str):
                    body = body.encode("utf-8")
                stdin_data = body
                cmd.extend(["--data-binary", "@-"])

            cmd.append(url)
            proc = subprocess.run(cmd, capture_output=True, input=stdin_data)
            raw = proc.stdout
            if proc.returncode != 0 and b"__HTTP_STATUS__:" not in raw:
                err = proc.stderr.decode("utf-8", "replace").strip() or f"curl exit code {proc.returncode}"
                raise ConnectionError(err)
            marker = b"\n__HTTP_STATUS__:"
            pos = raw.rfind(marker)
            if pos != -1:
                resp_body = raw[:pos]
                try:
                    status_code = int(raw[pos + len(marker):].strip())
                except ValueError:
                    status_code = 0
            else:
                resp_body = raw
                status_code = 0

            resp_headers = {}
            if os.path.exists(hdr_path):
                try:
                    with open(hdr_path, "r", encoding="latin-1", errors="replace") as f:
                        for line in f:
                            if ":" in line:
                                hk, _, hv = line.partition(":")
                                resp_headers[hk.strip().lower()] = hv.strip()
                except Exception:
                    pass

            return status_code, resp_body, resp_headers
        finally:
            for p in temp_files:
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _send_urllib(self, method, url, body=None, headers=None, auth=True):
        hdrs = {"User-Agent": USER_AGENT}
        if auth and self.token:
            hdrs["Authorization"] = f"Bot {self.token}"
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read()
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, data, resp_headers
        except urllib.error.HTTPError as e:
            resp_headers = {k.lower(): v for k, v in e.headers.items()}
            return e.code, e.read(), resp_headers

    def _send(self, method, url, body=None, headers=None, auth=True, multipart_file=None, retries=None):
        retries = retries or self.retries
        delay = 1.0
        last_err = None
        for _ in range(retries):
            try:
                if self.has_curl:
                    status, data, resp_hdrs = self._send_curl(
                        method, url, body=body, headers=headers, auth=auth, multipart_file=multipart_file
                    )
                else:
                    if multipart_file:
                        field_name, filename, data_bytes, payload_json = multipart_file
                        fields = {}
                        if payload_json:
                            fields["payload_json"] = (payload_json.encode("utf-8"), "application/json")
                        files = {field_name: (filename, data_bytes, "application/octet-stream")}
                        body, ctype = _encode_multipart(fields, files)
                        headers = dict(headers or {})
                        headers["Content-Type"] = ctype
                    status, data, resp_hdrs = self._send_urllib(
                        method, url, body=body, headers=headers, auth=auth
                    )
            except Exception as e:
                last_err = e
                log.warning("Network error reaching Discord (%s); retrying in %.0fs", e, delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue

            if status == 0:  # curl reached nothing (DNS failure, connection reset, timeout)
                last_err = ConnectionError("no HTTP response")
                log.warning("No response from Discord; retrying in %.0fs", delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue

            if 200 <= status < 300:
                if resp_hdrs.get("x-ratelimit-remaining") == "0":
                    try:
                        wait = float(resp_hdrs.get("x-ratelimit-reset-after", "0"))
                        if 0 < wait < 60:
                            time.sleep(wait)
                    except ValueError:
                        pass
                return status, data

            if status == 429:
                retry_after = 1.0
                try:
                    retry_after = float(json.loads(data).get("retry_after", 1.0))
                except Exception:
                    try:
                        retry_after = float(resp_hdrs.get("retry-after", "1"))
                    except (TypeError, ValueError):
                        pass
                log.info("Rate limited (%s %s); waiting %.2fs", method, url.split("?")[0], retry_after)
                time.sleep(retry_after + 0.25)
                continue

            if status >= 500:
                last_err = DiscordError(status, data[:300].decode("utf-8", "replace"))
                log.warning("Discord server error %s; retrying in %.0fs", status, delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue

            raise DiscordError(status, data[:500].decode("utf-8", "replace"))

        raise DiscordError(0, f"Giving up on {method} {url.split('?')[0]}: {last_err}")

    def request(self, method, path, json_body=None):
        body = None
        headers = {}
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, data = self._send(method, API_BASE + path, body=body, headers=headers)
        if status == 204 or not data:
            return None
        return json.loads(data)

    # ------------------------------------------------------------- endpoints
    def get_me(self):
        return self.request("GET", "/users/@me")

    def get_channel(self, channel_id):
        return self.request("GET", f"/channels/{channel_id}")

    def send_file(self, channel_id, filename: str, data: bytes, content: str = ""):
        payload = {
            "content": content[:2000],
            "attachments": [{"id": 0, "filename": filename}],
            "allowed_mentions": {"parse": []},
        }
        payload_json = json.dumps(payload)
        status, resp = self._send(
            "POST",
            f"{API_BASE}/channels/{channel_id}/messages",
            multipart_file=("files[0]", filename, data, payload_json),
        )
        return json.loads(resp)

    def get_message(self, channel_id, message_id):
        return self.request("GET", f"/channels/{channel_id}/messages/{message_id}")

    def get_messages(self, channel_id, before=None, after=None, limit=100):
        """With `after`, returns the `limit` messages directly after that id (in any order)."""
        q = f"?limit={limit}" + (f"&before={before}" if before else "") + (f"&after={after}" if after else "")
        return self.request("GET", f"/channels/{channel_id}/messages{q}")

    def send_message(self, channel_id, content: str):
        return self.request("POST", f"/channels/{channel_id}/messages",
                            {"content": content[:2000], "allowed_mentions": {"parse": []}})

    def delete_message(self, channel_id, message_id):
        return self.request("DELETE", f"/channels/{channel_id}/messages/{message_id}")

    def pin(self, channel_id, message_id):
        try:
            return self.request("PUT", f"/channels/{channel_id}/messages/pins/{message_id}")
        except DiscordError as e:
            if e.status not in (404, 405):
                raise
            return self.request("PUT", f"/channels/{channel_id}/pins/{message_id}")

    def unpin(self, channel_id, message_id):
        try:
            return self.request("DELETE", f"/channels/{channel_id}/messages/pins/{message_id}")
        except DiscordError as e:
            if e.status not in (404, 405):
                raise
            return self.request("DELETE", f"/channels/{channel_id}/pins/{message_id}")

    def list_pins(self, channel_id):
        try:
            r = self.request("GET", f"/channels/{channel_id}/messages/pins?limit=50")
            if isinstance(r, dict) and "items" in r:
                return [it["message"] for it in r["items"]]
            elif isinstance(r, list):
                return r
        except DiscordError as e:
            if e.status not in (404, 405):
                raise
        return self.request("GET", f"/channels/{channel_id}/pins") or []

    def download_url(self, url: str) -> bytes:
        """Download an attachment from Discord's CDN (no auth header)."""
        status, data = self._send("GET", url, auth=False, retries=min(5, self.retries))
        return data
