"""The last few thousand log lines in memory, for the dashboard's Log tab (live, filterable)."""

import collections
import logging
import os
import re
import threading
import time

_LINE = re.compile(r"^(\d\d:\d\d:\d\d) \[(\w+)\] ([\w.]+): (.*)$")


class LogBuffer(logging.Handler):
    def __init__(self, size=5000):
        super().__init__(logging.INFO)
        self._lines = collections.deque(maxlen=size)
        self._seq = 0
        self._lock = threading.Lock()

    def _add(self, t, level, name, msg):
        with self._lock:
            self._seq += 1
            self._lines.append({"i": self._seq, "t": t, "l": level, "n": name.replace("discorddrive.", ""), "m": msg})

    def emit(self, record):
        try:
            self._add(record.created, record.levelname, record.name, record.getMessage())
        except Exception:
            pass

    def since(self, after=0, limit=1000):
        with self._lock:
            out = [r for r in self._lines if r["i"] > after]
        return out[-limit:]

    def seed_from_file(self, path, lines=400):
        """Start with the end of the log file, so the tab isn't empty right after a start."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(max(0, os.path.getsize(path) - 256 * 1024))
                tail = f.read().splitlines()[-lines:]
        except OSError:
            return
        day = time.strftime("%Y-%m-%d ")
        for line in tail:
            m = _LINE.match(line)
            if not m:
                continue
            try:
                t = time.mktime(time.strptime(day + m.group(1), "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                t = time.time()
            if t > time.time() + 60:
                t -= 86400
            self._add(t, m.group(2), m.group(3), m.group(4))


BUFFER = LogBuffer()
_installed = False


def install(log_path=None):
    global _installed
    if _installed:
        return BUFFER
    _installed = True
    if log_path:
        BUFFER.seed_from_file(log_path)
    root = logging.getLogger("discorddrive")
    root.addHandler(BUFFER)
    if root.getEffectiveLevel() > logging.INFO:
        root.setLevel(logging.INFO)          # the Log tab shows everything, not only warnings
    return BUFFER
