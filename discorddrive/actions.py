"""Operations shared by the command line and the web dashboard (restoring versions and snapshots)."""

import posixpath
import time

from .index import new_uid


def version_put_op(idx, v, uid, parent_uid, name):
    """A put operation that brings back version row `v` as file `uid` (named `name` in `parent_uid`)."""
    chunks = idx.version_chunks(v["id"])
    return {"t": "put", "u": uid, "p": parent_uid, "n": name, "s": v["size"],
            "m": v["mtime"] or time.time(),
            "c": [[c["message_id"], c["size"], c["sha256"]] for c in chunks],
            "r": 1}   # an explicit restore: allowed even though the file was deleted


def _folder_ops(idx, path, made):
    """(uid of folder `path`, ops creating whichever part of it doesn't exist yet)."""
    path = "/" + path.strip("/")
    if path in made:
        return made[path], []
    node = idx.resolve(path)
    if node is not None and node["is_dir"]:
        made[path] = node["uid"]
        return node["uid"], []
    parent, name = posixpath.split(path)
    puid, ops = _folder_ops(idx, parent, made)
    uid = new_uid()
    ops.append({"t": "mkdir", "u": uid, "p": puid, "n": name, "m": time.time()})
    made[path] = uid
    return uid, ops


def snapshot_restore_ops(idx, snap_id, prefix="/", target=None, in_place=False):
    """Operations restoring snapshot `snap_id` (everything under `prefix`).

    By default into a new folder `target` (e.g. "/Restored 2026-10-07 14.00"), which never touches
    current files. `in_place` puts each file back at its original path instead; whatever is there
    now is kept as an older version, so that is reversible too. Returns (ops, files restored)."""
    prefix = "/" + prefix.strip("/")
    entries = idx.snapshot_entries(snap_id, prefix)
    if not entries:
        return [], 0
    base = posixpath.dirname(prefix) if prefix != "/" else "/"
    made, ops, files = {}, [], 0
    for e in sorted(entries, key=lambda e: (e["path"].count("/"), e["path"])):
        rel = e["path"][len(base):].lstrip("/") if base != "/" else e["path"].lstrip("/")
        dest = "/" + rel if in_place else posixpath.join("/" + target.strip("/"), rel)
        if e["is_dir"]:
            _, more = _folder_ops(idx, dest, made)
            ops += more
            continue
        parent, name = posixpath.split(dest)
        puid, more = _folder_ops(idx, parent, made)
        ops += more
        current = idx.resolve(dest) if in_place else None
        uid = current["uid"] if current is not None and not current["is_dir"] else new_uid()
        ops.append({"t": "put", "u": uid, "p": puid, "n": name, "s": e["size"], "m": e["mtime"] or time.time(),
                    "c": [list(c) for c in e["chunks"]], "r": 1})
        files += 1
    return ops, files


def default_restore_folder(snap):
    return "/Restored " + time.strftime("%Y-%m-%d %H.%M", time.localtime(snap["at"]))
