"""SQLite metadata index: directory tree, file -> Discord chunk mapping, sync journal state and file versions.

Every node has a stable `uid` that is the same on all devices. Local changes are
recorded as operations in the `outbox` table (in the same transaction as the
change) and published to the channel by the journal (journal.py). Operations
read back from the channel are applied with `apply_ops`, in Discord's message
order, which is identical on every device; that is what keeps devices in sync.

`jstate` tracks how far a node has propagated:
    0  local only (a new file whose first upload has not finished)
    1  its creating operation is queued / posted, but not yet read back
    2  known: an operation for it has been applied from the journal
"""

import gzip
import hashlib
import json
import logging
import os
import posixpath
import secrets
import sqlite3
import tempfile
import threading
import time
from contextlib import contextmanager

log = logging.getLogger("discorddrive.index")

ROOT_ID = 1
ROOT_UID = "root"
RECOVERED_UID = "recovered"
RECOVERED_NAME = "Recovered files"

J_LOCAL, J_QUEUED, J_KNOWN = 0, 1, 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    parent  INTEGER,
    name    TEXT NOT NULL COLLATE NOCASE,
    is_dir  INTEGER NOT NULL,
    size    INTEGER NOT NULL DEFAULT 0,
    mtime   REAL NOT NULL,
    ctime   REAL NOT NULL,
    atime   REAL NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    state   TEXT NOT NULL DEFAULT 'synced',      -- synced | pending | error
    is_pinned INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS nodes_parent_name ON nodes(parent, name);
CREATE TABLE IF NOT EXISTS chunks(
    node_id       INTEGER NOT NULL,
    idx           INTEGER NOT NULL,
    message_id    TEXT NOT NULL,
    attachment_id TEXT,
    url           TEXT,
    size          INTEGER NOT NULL,
    sha256        TEXT,
    PRIMARY KEY(node_id, idx)
);
CREATE INDEX IF NOT EXISTS chunks_message ON chunks(message_id);
CREATE TABLE IF NOT EXISTS trash(message_id TEXT PRIMARY KEY, added REAL);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alias(uid TEXT PRIMARY KEY, target TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS versions(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    uid        TEXT NOT NULL,
    parent_uid TEXT,
    name       TEXT NOT NULL,
    path       TEXT,
    size       INTEGER NOT NULL,
    mtime      REAL,
    superseded REAL NOT NULL,
    reason     TEXT NOT NULL                     -- replaced | deleted | conflict
);
CREATE INDEX IF NOT EXISTS versions_uid ON versions(uid);
CREATE TABLE IF NOT EXISTS version_chunks(
    version_id INTEGER NOT NULL,
    idx        INTEGER NOT NULL,
    message_id TEXT NOT NULL,
    size       INTEGER NOT NULL,
    sha256     TEXT,
    PRIMARY KEY(version_id, idx)
);
CREATE INDEX IF NOT EXISTS version_chunks_message ON version_chunks(message_id);
"""

_UPDATABLE = {"size", "mtime", "ctime", "atime", "version", "state", "is_pinned"}


def new_uid() -> str:
    return secrets.token_hex(8)


def _legacy_uid(path: str) -> str:
    # Deterministic, so two devices upgrading the same tree agree on every uid.
    return hashlib.sha256(("legacy:" + path.lower()).encode("utf-8")).hexdigest()[:16]


def conflict_name(name: str, uid: str) -> str:
    stem, ext = os.path.splitext(name)
    if not stem:  # dotfiles such as ".bashrc"
        stem, ext = name, ""
    return f"{stem} (conflict {uid[:6]}){ext}"


class Index:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        self.keep_versions = True
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self._migrate()
        # Counts metadata changes made during this session (used to decide when to checkpoint).
        self.change_counter = 1
        self.last_change = time.time()
        self._stats_cache = (0.0, None)

    def _migrate(self):
        with self.lock:
            db = self.db
            db.executescript(SCHEMA)
            cols = {r[1] for r in db.execute("PRAGMA table_info(nodes)")}
            if "is_pinned" not in cols:
                db.execute("ALTER TABLE nodes ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0")
            if "uid" not in cols:
                db.execute("ALTER TABLE nodes ADD COLUMN uid TEXT")
            if "jstate" not in cols:
                # Nodes from before the journal existed count as known everywhere.
                db.execute("ALTER TABLE nodes ADD COLUMN jstate INTEGER NOT NULL DEFAULT 2")
            now = time.time()
            db.execute(
                "INSERT OR IGNORE INTO nodes(id, parent, name, is_dir, mtime, ctime, atime, uid, jstate) "
                "VALUES(?, NULL, '', 1, ?, ?, ?, ?, 2)",
                (ROOT_ID, now, now, now, ROOT_UID),
            )
            missing = db.execute("SELECT COUNT(*) FROM nodes WHERE uid IS NULL").fetchone()[0]
            if missing:
                tree = {r[0]: (r[1], r[2]) for r in db.execute("SELECT id, parent, name FROM nodes")}

                def path(nid):
                    parts = []
                    while nid is not None and nid != ROOT_ID and nid in tree:
                        parent, name = tree[nid]
                        parts.append(name)
                        nid = parent
                    return "/" + "/".join(reversed(parts))

                db.execute("BEGIN")
                for (nid,) in db.execute("SELECT id FROM nodes WHERE uid IS NULL").fetchall():
                    uid = ROOT_UID if nid == ROOT_ID else _legacy_uid(path(nid))
                    db.execute("UPDATE nodes SET uid=? WHERE id=?", (uid, nid))
                db.execute("COMMIT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS nodes_uid ON nodes(uid)")

    def close(self):
        with self.lock:
            self.db.close()

    # ------------------------------------------------------------- plumbing
    def _changed(self):
        self.change_counter += 1
        self.last_change = time.time()
        self._stats_cache = (0.0, None)

    @contextmanager
    def tx(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            else:
                self.db.execute("COMMIT")
                self._changed()

    def _one(self, sql, args=()):
        with self.lock:
            row = self.db.execute(sql, args).fetchone()
            return dict(row) if row else None

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _queue(self, db, op):
        db.execute("INSERT INTO outbox(op) VALUES(?)", (json.dumps(op, separators=(",", ":")),))

    @staticmethod
    def _uid(db, nid):
        row = db.execute("SELECT uid FROM nodes WHERE id=?", (nid,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _chunk_list(db, nid):
        return [(r[0], r[1], r[2]) for r in
                db.execute("SELECT message_id, size, sha256 FROM chunks WHERE node_id=? ORDER BY idx", (nid,))]

    @staticmethod
    def _path(db, nid):
        parts = []
        while nid is not None and nid != ROOT_ID:
            row = db.execute("SELECT parent, name FROM nodes WHERE id=?", (nid,)).fetchone()
            if row is None:
                break
            parts.append(row[1])
            nid = row[0]
        return "/" + "/".join(reversed(parts))

    # ---------------------------------------------------------------- nodes
    def get(self, nid):
        return self._one("SELECT * FROM nodes WHERE id=?", (nid,))

    def get_by_uid(self, uid):
        with self.lock:
            nid = self._nid(self.db, uid)
            return self.get(nid) if nid is not None else None

    def lookup(self, parent_id, name):
        return self._one("SELECT * FROM nodes WHERE parent=? AND name=?", (parent_id, name))

    def resolve(self, path: str):
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        with self.lock:
            node = self.get(ROOT_ID)
            for p in parts:
                if node is None or not node["is_dir"]:
                    return None
                node = self.lookup(node["id"], p)
            return node

    def children(self, nid, limit=-1):
        return self._all("SELECT * FROM nodes WHERE parent=? ORDER BY name LIMIT ?", (nid, limit))

    def create_node(self, parent_id, name, is_dir, state="synced", uid=None):
        """Create a node locally. Directories are published right away; files are
        published by `replace_chunks` once their content is uploaded."""
        now = time.time()
        uid = uid or new_uid()
        with self.tx() as db:
            cur = db.execute(
                "INSERT INTO nodes(parent, name, is_dir, size, mtime, ctime, atime, state, uid, jstate) "
                "VALUES(?,?,?,0,?,?,?,?,?,?)",
                (parent_id, name, 1 if is_dir else 0, now, now, now, state, uid, J_QUEUED if is_dir else J_LOCAL),
            )
            nid = cur.lastrowid
            if is_dir:
                self._queue(db, {"t": "mkdir", "u": uid, "p": self._uid(db, parent_id), "n": name, "m": now})
        return self.get(nid)

    def makedirs(self, path):
        """Return the directory node at `path`, creating missing directories."""
        node = self.get(ROOT_ID)
        for part in [p for p in path.replace("\\", "/").split("/") if p]:
            child = self.lookup(node["id"], part)
            if child is not None and not child["is_dir"]:
                child = self.lookup(node["id"], conflict_name(part, "dir"))
                part = conflict_name(part, "dir")
            node = child or self.create_node(node["id"], part, True)
        return node

    def update(self, nid, **fields):
        bad = set(fields) - _UPDATABLE
        if bad:
            raise ValueError(f"cannot update {bad}")
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        with self.tx() as db:
            db.execute(f"UPDATE nodes SET {cols} WHERE id=?", (*fields.values(), nid))

    def touch(self, nid, atime, mtime):
        """utimens: also publishes the new mtime of an already uploaded file."""
        with self.tx() as db:
            db.execute("UPDATE nodes SET atime=?, mtime=? WHERE id=?", (atime, mtime, nid))
            row = db.execute("SELECT uid, is_dir, state, jstate FROM nodes WHERE id=?", (nid,)).fetchone()
            if row and not row["is_dir"] and row["state"] == "synced" and row["jstate"] >= J_QUEUED:
                self._queue(db, {"t": "mt", "u": row["uid"], "m": mtime})

    def mark_modified(self, nid, size, mtime):
        with self.tx() as db:
            db.execute(
                "UPDATE nodes SET size=?, mtime=?, version=version+1, state='pending' WHERE id=?",
                (size, mtime, nid),
            )

    def rename(self, nid, new_parent, new_name):
        with self.tx() as db:
            row = db.execute("SELECT uid, jstate FROM nodes WHERE id=?", (nid,)).fetchone()
            db.execute("UPDATE nodes SET parent=?, name=?, ctime=? WHERE id=?",
                       (new_parent, new_name, time.time(), nid))
            # A file that was never published is published later under its new name.
            if row and row["jstate"] >= J_QUEUED:
                self._queue(db, {"t": "mv", "u": row["uid"], "p": self._uid(db, new_parent), "n": new_name})

    def delete_node(self, nid):
        """Delete a file or an empty directory. File content is kept as a version (or trashed)."""
        with self.tx() as db:
            row = db.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
            if row is None:
                return
            old = self._chunk_list(db, nid)
            if old:
                # Record the version before deleting, while its path still resolves.
                vid = self._add_version(db, row, old, "deleted")
            db.execute("DELETE FROM chunks WHERE node_id=?", (nid,))
            db.execute("DELETE FROM nodes WHERE id=?", (nid,))
            if old and vid is None:
                self._release(db, [c[0] for c in old])
            if row["jstate"] >= J_QUEUED:
                self._queue(db, {"t": "rm", "u": row["uid"]})

    def is_ancestor_or_self(self, ancestor_id, nid):
        with self.lock:
            return self._is_ancestor(self.db, ancestor_id, nid)

    @staticmethod
    def _is_ancestor(db, ancestor_id, nid):
        cur = nid
        while cur is not None:
            if cur == ancestor_id:
                return True
            row = db.execute("SELECT parent FROM nodes WHERE id=?", (cur,)).fetchone()
            cur = row[0] if row else None
        return False

    def path_of(self, nid):
        with self.lock:
            return self._path(self.db, nid)

    def unsynced_files(self):
        return self._all("SELECT * FROM nodes WHERE is_dir=0 AND state!='synced'")

    def unsynced_ids(self):
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT id FROM nodes WHERE is_dir=0 AND state!='synced'")]

    # --------------------------------------------------------------- chunks
    def get_chunks(self, nid):
        return self._all("SELECT * FROM chunks WHERE node_id=? ORDER BY idx", (nid,))

    def replace_chunks(self, nid, chunks, version):
        """Atomically swap a file's chunk list and publish it. Returns False if the file changed meanwhile."""
        with self.tx() as db:
            row = db.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
            if row is None or row["version"] != version:
                return False
            old = self._chunk_list(db, nid)
            size = sum(c["size"] for c in chunks)
            new_mids = [c["message_id"] for c in chunks]
            vid = None
            if old and [c[0] for c in old] != new_mids:
                vid = self._add_version(db, row, old, "replaced")
            db.execute("DELETE FROM chunks WHERE node_id=?", (nid,))
            db.executemany(
                "INSERT INTO chunks(node_id, idx, message_id, attachment_id, url, size, sha256) VALUES(?,?,?,?,?,?,?)",
                [(nid, c["idx"], c["message_id"], c["attachment_id"], c["url"], c["size"], c["sha256"]) for c in chunks],
            )
            db.execute("UPDATE nodes SET state='synced', size=?, jstate=MAX(jstate, 1) WHERE id=?", (size, nid))
            if old and vid is None:
                self._release(db, [c[0] for c in old if c[0] not in new_mids])
            self._queue(db, {
                "t": "put", "u": row["uid"], "p": self._uid(db, row["parent"]), "n": row["name"],
                "s": size, "m": row["mtime"],
                "c": [[c["message_id"], c["size"], c["sha256"]] for c in chunks],
            })
        return True

    def update_chunk_url(self, message_id, url):
        with self.lock:
            self.db.execute("UPDATE chunks SET url=? WHERE message_id=?", (url, message_id))

    # ---------------------------------------------------------------- trash
    def trash_add(self, mids):
        now = time.time()
        with self.lock:
            self.db.executemany("INSERT OR IGNORE INTO trash(message_id, added) VALUES(?, ?)", [(m, now) for m in mids])

    def trash_batch(self, n=10):
        return [r["message_id"] for r in self._all("SELECT message_id FROM trash ORDER BY added LIMIT ?", (n,))]

    def trash_remove(self, mid):
        with self.lock:
            self.db.execute("DELETE FROM trash WHERE message_id=?", (mid,))

    @staticmethod
    def _release(db, mids):
        """Trash messages that nothing (current files or versions) references any more."""
        now = time.time()
        for mid in mids:
            used = db.execute(
                "SELECT 1 FROM chunks WHERE message_id=? UNION ALL "
                "SELECT 1 FROM version_chunks WHERE message_id=? LIMIT 1", (mid, mid)).fetchone()
            if not used:
                db.execute("INSERT OR IGNORE INTO trash(message_id, added) VALUES(?, ?)", (mid, now))

    # ------------------------------------------------------------- versions
    def _add_version(self, db, row, chunks, reason, size=None, mtime=None):
        """Keep `chunks` as an old version of node `row`. Returns the version id, or None
        when versioning is off (the caller then releases the chunks)."""
        if not chunks:
            return None
        # Conflicting remote content is always kept: another device may still be using it.
        if not self.keep_versions and reason != "conflict":
            return None
        cur = db.execute(
            "INSERT INTO versions(uid, parent_uid, name, path, size, mtime, superseded, reason) VALUES(?,?,?,?,?,?,?,?)",
            (row["uid"], self._uid(db, row["parent"]), row["name"], self._path(db, row["id"]),
             size if size is not None else sum(c[1] for c in chunks),
             mtime if mtime is not None else (row["mtime"] if reason == "deleted" else None),
             time.time(), reason),
        )
        vid = cur.lastrowid
        db.executemany(
            "INSERT INTO version_chunks(version_id, idx, message_id, size, sha256) VALUES(?,?,?,?,?)",
            [(vid, i, c[0], c[1], c[2]) for i, c in enumerate(chunks)],
        )
        return vid

    def keep_as_version(self, nid, chunks, reason="conflict", size=None, mtime=None):
        """Store `chunks` [(message_id, size, sha256)] as a version of node `nid`."""
        with self.tx() as db:
            row = db.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
            if row is not None:
                self._add_version(db, row, chunks, reason, size=size, mtime=mtime)

    def versions_for(self, uid):
        return self._all("SELECT * FROM versions WHERE uid=? ORDER BY superseded DESC, id DESC", (uid,))

    def version_chunks(self, vid):
        return self._all("SELECT * FROM version_chunks WHERE version_id=? ORDER BY idx", (vid,))

    def deleted_files(self, prefix="/"):
        """Most recent 'deleted' version of every file that no longer exists."""
        prefix = "/" + prefix.strip("/")
        rows = self._all(
            "SELECT v.* FROM versions v WHERE v.reason='deleted' "
            "AND NOT EXISTS (SELECT 1 FROM nodes n WHERE n.uid=v.uid) "
            "AND v.id = (SELECT v2.id FROM versions v2 WHERE v2.uid=v.uid AND v2.reason='deleted' "
            "            ORDER BY v2.superseded DESC, v2.id DESC LIMIT 1) "
            "ORDER BY v.superseded DESC")
        if prefix == "/":
            return rows
        p = prefix.lower()
        return [r for r in rows if (r["path"] or "").lower() == p or (r["path"] or "").lower().startswith(p + "/")]

    def gc_versions(self, retention_days: float, max_versions: int) -> int:
        """Drop versions older than `retention_days` / beyond `max_versions` per file. 0 = no limit."""
        with self.tx() as db:
            expired = set()
            if retention_days and retention_days > 0:
                cutoff = time.time() - retention_days * 86400
                expired |= {r[0] for r in db.execute("SELECT id FROM versions WHERE superseded < ?", (cutoff,))}
            if max_versions and max_versions > 0:
                expired |= {r[0] for r in db.execute(
                    "SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY uid ORDER BY superseded DESC, id DESC) rn "
                    "FROM versions) WHERE rn > ?", (max_versions,))}
            for vid in expired:
                mids = [r[0] for r in db.execute("SELECT message_id FROM version_chunks WHERE version_id=?", (vid,))]
                db.execute("DELETE FROM version_chunks WHERE version_id=?", (vid,))
                db.execute("DELETE FROM versions WHERE id=?", (vid,))
                self._release(db, mids)
        return len(expired)

    # --------------------------------------------------------------- outbox
    def outbox_peek(self, n=200):
        with self.lock:
            return [(r[0], json.loads(r[1])) for r in
                    self.db.execute("SELECT id, op FROM outbox ORDER BY id LIMIT ?", (n,))]

    def outbox_remove(self, ids):
        with self.lock:
            self.db.executemany("DELETE FROM outbox WHERE id=?", [(i,) for i in ids])

    def outbox_count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    # ------------------------------------------------------- journal apply
    @staticmethod
    def _nid(db, uid):
        for _ in range(16):
            if uid is None:
                return None
            row = db.execute("SELECT id FROM nodes WHERE uid=?", (uid,)).fetchone()
            if row:
                return row[0]
            a = db.execute("SELECT target FROM alias WHERE uid=?", (uid,)).fetchone()
            if not a:
                return None
            uid = a[0]
        return None

    def _recovered_dir(self, db):
        nid = self._nid(db, RECOVERED_UID)
        if nid is not None:
            return nid
        name = self._free_name(db, ROOT_ID, RECOVERED_NAME)
        now = time.time()
        return db.execute(
            "INSERT INTO nodes(parent, name, is_dir, size, mtime, ctime, atime, uid, jstate) VALUES(?,?,1,0,?,?,?,?,2)",
            (ROOT_ID, name, now, now, now, RECOVERED_UID)).lastrowid

    def _parent_for(self, db, uid):
        nid = self._nid(db, uid)
        if nid is not None:
            row = db.execute("SELECT is_dir FROM nodes WHERE id=?", (nid,)).fetchone()
            if row and row[0]:
                return nid
        return self._recovered_dir(db)

    @staticmethod
    def _free_name(db, parent, name):
        cand, i = name, 2
        while db.execute("SELECT 1 FROM nodes WHERE parent=? AND name=?", (parent, cand)).fetchone():
            stem, ext = os.path.splitext(name)
            cand = f"{stem} ({i}){ext}"
            i += 1
        return cand

    def _place(self, db, parent, name, uid, changed):
        """Name for node `uid` in `parent`. On a clash the side that comes later in the
        journal order gets a conflict name; a local node that is not in the journal yet
        is always later, so it is the one renamed."""
        row = db.execute("SELECT * FROM nodes WHERE parent=? AND name=?", (parent, name)).fetchone()
        if row is None or row["uid"] == uid:
            return name
        if row["jstate"] < J_KNOWN:
            new = self._free_name(db, parent, conflict_name(row["name"], row["uid"]))
            db.execute("UPDATE nodes SET name=? WHERE id=?", (new, row["id"]))
            changed.add(row["id"])
            log.info("Name clash with a change from another device: renamed local '%s' to '%s'", row["name"], new)
            return name
        return self._free_name(db, parent, conflict_name(name, uid))

    def apply_ops(self, ops, cursor, busy=None):
        """Apply journal operations (from message `cursor`) and advance the cursor.
        Returns the set of local node ids that changed (including deleted ones)."""
        busy = busy or (lambda nid: False)
        changed = set()
        with self.tx() as db:
            for op in ops:
                fn = getattr(self, "_op_" + str(op.get("t")), None) if isinstance(op, dict) else None
                if fn is None:
                    log.warning("Ignoring unknown journal operation: %r", op)
                    continue
                db.execute("SAVEPOINT op")
                try:
                    fn(db, op, busy, changed)
                    db.execute("RELEASE op")
                except (KeyError, TypeError, ValueError, IndexError, sqlite3.IntegrityError) as e:
                    db.execute("ROLLBACK TO op")
                    db.execute("RELEASE op")
                    log.warning("Skipping journal operation %r: %s", op, e)
            db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES('journal_cursor', ?)", (str(cursor),))
        return changed

    def _op_mkdir(self, db, op, busy, changed):
        uid = op["u"]
        nid = self._nid(db, uid)
        if nid is not None:
            db.execute("UPDATE nodes SET jstate=2 WHERE id=? AND jstate<2", (nid,))
            return
        parent = self._parent_for(db, op.get("p"))
        same = db.execute("SELECT * FROM nodes WHERE parent=? AND name=?", (parent, op["n"])).fetchone()
        if same is not None and same["is_dir"]:
            # Two devices created the same folder: treat them as one.
            db.execute("INSERT OR REPLACE INTO alias(uid, target) VALUES(?, ?)", (uid, same["uid"]))
            return
        name = self._place(db, parent, op["n"], uid, changed)
        m = float(op.get("m") or time.time())
        nid = db.execute(
            "INSERT INTO nodes(parent, name, is_dir, size, mtime, ctime, atime, uid, jstate) VALUES(?,?,1,0,?,?,?,?,2)",
            (parent, name, m, m, m, uid)).lastrowid
        changed.add(nid)

    def _op_put(self, db, op, busy, changed):
        uid = op["u"]
        chunks = [(str(c[0]), int(c[1]), c[2]) for c in op["c"]]
        size = int(op.get("s", sum(c[1] for c in chunks)))
        mtime = float(op.get("m") or time.time())
        nid = self._nid(db, uid)
        if nid is not None:
            row = db.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
            if row["is_dir"]:
                return
            db.execute("UPDATE nodes SET jstate=2 WHERE id=? AND jstate<2", (nid,))
            old = self._chunk_list(db, nid)
            local_edit = row["state"] != "synced" or busy(nid)
            if [c[0] for c in old] == [c[0] for c in chunks]:
                if not local_edit and row["mtime"] != mtime:
                    db.execute("UPDATE nodes SET mtime=? WHERE id=?", (mtime, nid))
                    changed.add(nid)
                return
            if local_edit:
                # This device has newer edits that will be published after this op and win;
                # keep the other device's content as a version so nothing is lost.
                self._add_version(db, row, chunks, "conflict", size=size, mtime=mtime)
                log.info("Conflicting edit of %s from another device kept as a version", self._path(db, nid))
                return
            vid = self._add_version(db, row, old, "replaced") if old else None
            self._set_chunks(db, nid, chunks)
            db.execute("UPDATE nodes SET size=?, mtime=?, version=version+1, state='synced' WHERE id=?",
                       (size, mtime, nid))
            if old and vid is None:
                self._release(db, [c[0] for c in old])
            changed.add(nid)
            return
        parent = self._parent_for(db, op.get("p"))
        name = self._place(db, parent, op["n"], uid, changed)
        nid = db.execute(
            "INSERT INTO nodes(parent, name, is_dir, size, mtime, ctime, atime, state, uid, jstate) "
            "VALUES(?,?,0,?,?,?,?,'synced',?,2)",
            (parent, name, size, mtime, mtime, mtime, uid)).lastrowid
        self._set_chunks(db, nid, chunks)
        changed.add(nid)

    @staticmethod
    def _set_chunks(db, nid, chunks):
        db.execute("DELETE FROM chunks WHERE node_id=?", (nid,))
        db.executemany(
            "INSERT INTO chunks(node_id, idx, message_id, attachment_id, url, size, sha256) VALUES(?,?,?,NULL,NULL,?,?)",
            [(nid, i, c[0], c[1], c[2]) for i, c in enumerate(chunks)])

    def _op_mv(self, db, op, busy, changed):
        nid = self._nid(db, op["u"])
        parent = self._nid(db, op.get("p"))
        if nid is None or parent is None or nid == ROOT_ID:
            return
        prow = db.execute("SELECT is_dir FROM nodes WHERE id=?", (parent,)).fetchone()
        row = db.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
        if not prow or not prow[0]:
            return
        if row["is_dir"] and self._is_ancestor(db, nid, parent):
            return  # concurrent moves would create a cycle
        if row["parent"] == parent and row["name"] == op["n"]:
            return
        name = self._place(db, parent, op["n"], row["uid"], changed)
        db.execute("UPDATE nodes SET parent=?, name=?, ctime=? WHERE id=?", (parent, name, time.time(), nid))
        changed.add(nid)

    def _op_rm(self, db, op, busy, changed):
        nid = self._nid(db, op["u"])
        if nid is None or nid == ROOT_ID:
            return
        row = db.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
        if row["is_dir"]:
            if db.execute("SELECT 1 FROM nodes WHERE parent=? LIMIT 1", (nid,)).fetchone():
                return  # something was added to it concurrently; keep it
        elif row["state"] != "synced" or busy(nid):
            return  # local edits win; they are published after this op
        old = self._chunk_list(db, nid)
        vid = self._add_version(db, row, old, "deleted") if old else None
        db.execute("DELETE FROM chunks WHERE node_id=?", (nid,))
        db.execute("DELETE FROM nodes WHERE id=?", (nid,))
        if old and vid is None:
            self._release(db, [c[0] for c in old])
        changed.add(nid)

    def _op_mt(self, db, op, busy, changed):
        nid = self._nid(db, op["u"])
        if nid is None:
            return
        row = db.execute("SELECT is_dir, state FROM nodes WHERE id=?", (nid,)).fetchone()
        if not row["is_dir"] and row["state"] == "synced" and not busy(nid):
            db.execute("UPDATE nodes SET mtime=? WHERE id=?", (float(op["m"]), nid))
            changed.add(nid)

    # ------------------------------------------------------------------- kv
    def kv_get(self, key, default=None):
        row = self._one("SELECT value FROM kv WHERE key=?", (key,))
        return row["value"] if row else default

    def kv_set(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv(key, value) VALUES(?, ?)", (key, value))

    # ---------------------------------------------------------------- stats
    def stats(self, max_age=5.0):
        t, cached = self._stats_cache
        if cached is not None and time.time() - t < max_age:
            return cached
        with self.lock:
            r = self.db.execute(
                "SELECT COUNT(*) FILTER (WHERE is_dir=0), COUNT(*) FILTER (WHERE is_dir=1) - 1, "
                "COALESCE(SUM(size) FILTER (WHERE is_dir=0), 0), "
                "COUNT(*) FILTER (WHERE is_dir=0 AND state!='synced'), "
                "COUNT(*) FILTER (WHERE is_dir=0 AND is_pinned=1), "
                "COALESCE(SUM(size) FILTER (WHERE is_dir=0 AND is_pinned=1), 0) FROM nodes"
            ).fetchone()
            chunks = self.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            trash = self.db.execute("SELECT COUNT(*) FROM trash").fetchone()[0]
            outbox = self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
            v = self.db.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM versions").fetchone()
        s = {
            "files": r[0], "dirs": r[1], "bytes": r[2], "unsynced": r[3],
            "pinned_files": r[4], "pinned_bytes": r[5],
            "chunks": chunks, "trash": trash, "outbox": outbox,
            "versions": v[0], "version_bytes": v[1],
        }
        self._stats_cache = (time.time(), s)
        return s

    # ------------------------------------------------------------- pinning
    def set_pinned(self, nid: int, pinned: bool = True, recursive: bool = True):
        val = 1 if pinned else 0
        with self.tx() as db:
            if not recursive:
                db.execute("UPDATE nodes SET is_pinned=? WHERE id=?", (val, nid))
            else:
                to_visit = [nid]
                all_ids = []
                while to_visit:
                    cur = to_visit.pop()
                    all_ids.append(cur)
                    to_visit.extend(r[0] for r in db.execute("SELECT id FROM nodes WHERE parent=?", (cur,)))
                db.executemany("UPDATE nodes SET is_pinned=? WHERE id=?", [(val, i) for i in all_ids])

    def is_pinned(self, nid: int) -> bool:
        with self.lock:
            cur = nid
            while cur is not None:
                row = self.db.execute("SELECT parent, is_pinned FROM nodes WHERE id=?", (cur,)).fetchone()
                if not row:
                    break
                if row[1]:
                    return True
                cur = row[0]
            return False

    def get_pinned_message_ids(self) -> set:
        with self.lock:
            pinned_nodes = {r[0] for r in self.db.execute("SELECT id FROM nodes WHERE is_pinned=1").fetchall()}
            if not pinned_nodes:
                return set()
            all_pinned = set(pinned_nodes)
            to_visit = list(pinned_nodes)
            while to_visit:
                cur = to_visit.pop()
                for (c,) in self.db.execute("SELECT id FROM nodes WHERE parent=?", (cur,)).fetchall():
                    if c not in all_pinned:
                        all_pinned.add(c)
                        to_visit.append(c)
            placeholders = ",".join("?" * len(all_pinned))
            rows = self.db.execute(
                f"SELECT message_id FROM chunks WHERE node_id IN ({placeholders})", tuple(all_pinned)
            ).fetchall()
            return {r[0] for r in rows}

    # --------------------------------------------------------------- backup
    def snapshot_bytes(self) -> bytes:
        """Consistent, gzip-compressed copy of the index for upload as a checkpoint.

        Only state that is fully published is included: files whose first upload
        has not finished are left out, files with unpublished edits are rolled back
        to their last uploaded content, and device-local state (outbox, trash queue,
        offline pins, settings) is stripped. The journal cursor is kept, so a device
        restoring the checkpoint replays exactly the operations that came after it.
        """
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            dst = sqlite3.connect(tmp)
            with self.lock:
                self.db.backup(dst)
            dst.execute("DELETE FROM nodes WHERE id != ? AND jstate < 2", (ROOT_ID,))
            dst.execute(
                "DELETE FROM nodes WHERE is_dir=0 AND state!='synced' "
                "AND NOT EXISTS (SELECT 1 FROM chunks WHERE chunks.node_id=nodes.id)"
            )
            while dst.execute("DELETE FROM nodes WHERE id != ? AND parent NOT IN (SELECT id FROM nodes)",
                              (ROOT_ID,)).rowcount:
                pass
            dst.execute("DELETE FROM chunks WHERE node_id NOT IN (SELECT id FROM nodes)")
            dst.execute(
                "UPDATE nodes SET size=(SELECT COALESCE(SUM(size), 0) FROM chunks WHERE chunks.node_id=nodes.id), "
                "state='synced' WHERE state!='synced'"
            )
            dst.execute("UPDATE nodes SET is_pinned=0")
            dst.execute("DELETE FROM outbox")
            dst.execute("DELETE FROM trash")
            dst.execute("DELETE FROM kv WHERE key NOT IN ('journal_cursor', 'keyring')")
            dst.commit()
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.execute("VACUUM")
            dst.close()
            with open(tmp, "rb") as f:
                return gzip.compress(f.read(), 6)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def restore_from_snapshot(self, gz_data: bytes):
        """Replace the index with a snapshot, keeping this device's offline pins and trash queue."""
        raw_db = gzip.decompress(gz_data)
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with open(tmp, "wb") as f:
                f.write(raw_db)
            src = sqlite3.connect(tmp)
            with self.lock:
                pinned = [r[0] for r in self.db.execute("SELECT uid FROM nodes WHERE is_pinned=1")]
                trash = self.db.execute("SELECT message_id, added FROM trash").fetchall()
                src.backup(self.db)
                self._migrate()
                self.db.executemany("UPDATE nodes SET is_pinned=1 WHERE uid=?", [(u,) for u in pinned])
                self.db.executemany("INSERT OR IGNORE INTO trash(message_id, added) VALUES(?, ?)",
                                    [tuple(t) for t in trash])
                self._changed()
            src.close()
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
