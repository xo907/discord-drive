"""Share links: a file or a folder for someone else, with an expiry, an optional password and a
choice whether it may be downloaded or only viewed.

Links are kept in this device's index (they are served by this device's dashboard), keyed by a
random id. Revoking or changing a link takes effect immediately. The visitor's page shows the
content itself (photo, video, music, PDF, text) or, for a folder, its files.
"""

import json
import secrets
import threading
import time

from .crypto import check_password, hash_password

KEY = "shares"


class Shares:
    def __init__(self, index):
        self.index = index
        self._lock = threading.Lock()

    def _load(self):
        try:
            return json.loads(self.index.kv_get(KEY) or "{}")
        except ValueError:
            return {}

    def _save(self, data):
        self.index.kv_set(KEY, json.dumps(data, separators=(",", ":")))

    def all(self):
        """Every link that hasn't expired (expired ones are dropped)."""
        with self._lock:
            data = self._load()
            now = time.time()
            alive = {k: v for k, v in data.items() if not v.get("e") or v["e"] > now}
            if len(alive) != len(data):
                self._save(alive)
            return alive

    def get(self, sid):
        return self.all().get(str(sid or ""))

    def create(self, uid, is_dir, hours=24 * 7, password="", download=True):
        sid = secrets.token_urlsafe(12)
        rec = {"u": uid, "d": bool(is_dir), "c": time.time(), "e": _expiry(hours),
               "pw": hash_password(password) if password else "", "dl": bool(download), "v": 0}
        with self._lock:
            data = self._load()
            data[sid] = rec
            self._save(data)
        return sid, rec

    def update(self, sid, hours=None, password=None, download=None):
        with self._lock:
            data = self._load()
            rec = data.get(sid)
            if rec is None:
                return None
            if hours is not None:
                rec["e"] = _expiry(hours)
            if password is not None:
                rec["pw"] = hash_password(password) if password else ""
            if download is not None:
                rec["dl"] = bool(download)
            self._save(data)
            return rec

    def revoke(self, sid):
        with self._lock:
            data = self._load()
            found = data.pop(sid, None) is not None
            self._save(data)
            return found

    def viewed(self, sid):
        with self._lock:
            data = self._load()
            if sid in data:
                data[sid]["v"] = data[sid].get("v", 0) + 1
                self._save(data)

    @staticmethod
    def password_ok(rec, password):
        return check_password(password or "", rec.get("pw") or "")


def _expiry(hours):
    hours = float(hours or 0)
    if hours <= 0:
        return None
    return time.time() + min(hours, 24 * 3650) * 3600
