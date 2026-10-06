"""Background upload queue, chunker and trash cleaner. (Index checkpoints live in journal.py.)"""

import hashlib
import json
import logging
import os
import secrets
import threading
import time

log = logging.getLogger("discorddrive.uploader")


class _Interrupted(Exception):
    pass


class Uploader:
    def __init__(self, cfg, index, backend, fs, crypto=None):
        self.cfg = cfg
        self.index = index
        self.backend = backend
        self.fs = fs
        self.crypto = crypto
        self.journal = None

        self._lock = threading.Lock()
        self._pending = {}  # nid -> scheduled_time
        self._active = set()  # set of nids currently being uploaded
        self._failures = {}  # nid -> consecutive failed attempts (for back-off)
        self._cv = threading.Condition(self._lock)
        self._running = False

        self._upload_threads = []
        self._trash_thread = None

    # ----------------------------------------------------- resumable uploads
    # After every uploaded piece, the list of pieces is saved under "upload:<nid>" in the
    # index, so an interrupted upload (restart, crash, network error) continues where it
    # stopped instead of starting over. A record only applies to the same file version.

    @staticmethod
    def _progress_key(nid):
        return f"upload:{nid}"

    def _load_progress(self, nid):
        try:
            return json.loads(self.index.kv_get(self._progress_key(nid)) or "null")
        except ValueError:
            return None

    def _save_progress(self, nid, version, size, chunk_size, chunks):
        self.index.kv_set(self._progress_key(nid), json.dumps(
            {"v": version, "size": size, "chunk_size": chunk_size, "chunks": chunks}, separators=(",", ":")))

    def _drop_progress(self, nid, trash=True):
        rec = self._load_progress(nid)
        self.index.kv_delete(self._progress_key(nid))
        if trash and rec and rec.get("chunks"):
            self.index.trash_add([c["message_id"] for c in rec["chunks"]])

    def _cleanup_stale_progress(self):
        for key in self.index.kv_keys("upload:"):
            try:
                nid = int(key.split(":", 1)[1])
            except ValueError:
                continue
            node = self.index.get(nid)
            if node is None or node["is_dir"] or node["state"] == "synced":
                self._drop_progress(nid)

    def start(self):
        try:
            self._cleanup_stale_progress()
        except Exception as e:
            log.debug("Could not clean up old upload records: %s", e)
        with self._lock:
            if self._running:
                return
            self._running = True
            n = max(1, int(getattr(self.cfg, "upload_threads", 1) or 1))
            self._upload_threads = [
                threading.Thread(target=self._upload_loop, name=f"UploaderWorker-{i}", daemon=True)
                for i in range(n)
            ]
            self._trash_thread = threading.Thread(target=self._trash_loop, name="TrashCleanerWorker", daemon=True)
            for t in self._upload_threads:
                t.start()
            self._trash_thread.start()
        log.info("Uploader and sync services started (%d upload worker(s)).", len(self._upload_threads))

    def stop(self, timeout: float = 10.0):
        with self._lock:
            was_running = self._running
            self._running = False
            self._cv.notify_all()
        if not was_running:
            return

        for t in (*self._upload_threads, self._trash_thread):
            if t and t.is_alive():
                t.join(timeout=timeout)

        log.info("Uploader services stopped.")

    def enqueue(self, nid: int, delay: float = None):
        if delay is None:
            delay = self.cfg.upload_delay
        when = time.time() + max(0.0, delay)
        with self._lock:
            self._pending[nid] = when
            self._cv.notify_all()

    def is_idle(self) -> bool:
        with self._lock:
            return len(self._pending) == 0 and len(self._active) == 0

    def wait_idle(self, timeout: float = None) -> bool:
        end = time.time() + timeout if timeout is not None else float("inf")
        with self._lock:
            while len(self._pending) > 0 or len(self._active) > 0:
                now = time.time()
                if now >= end:
                    return False
                wait_sec = min(1.0, end - now) if end != float("inf") else 1.0
                self._cv.wait(wait_sec)
            return True

    # ------------------------------------------------------------- upload loop
    def _upload_loop(self):
        while True:
            nid = None
            with self._lock:
                while self._running:
                    now = time.time()
                    # Find a candidate that is due and not being uploaded by another worker
                    for cand, due in self._pending.items():
                        if due <= now and cand not in self._active:
                            nid = cand
                            break
                    if nid is not None:
                        del self._pending[nid]
                        self._active.add(nid)
                        break

                    # Wait for next scheduled time or notification
                    if self._pending:
                        next_due = min(self._pending.values())
                        timeout = min(1.0, max(0.1, next_due - now))
                    else:
                        timeout = 1.0
                    self._cv.wait(timeout)

                if not self._running:
                    break

            try:
                self._process_upload(nid)
            except Exception as e:
                log.error("Unhandled error uploading node %s: %s", nid, e, exc_info=True)
            finally:
                with self._lock:
                    self._active.discard(nid)
                    self._cv.notify_all()

    def _retry_later(self, nid):
        with self._lock:
            n = self._failures.get(nid, 0) + 1
            self._failures[nid] = n
        delay = min(300.0, 10.0 * (2 ** (n - 1)))
        self.enqueue(nid, delay=delay)
        return delay

    def _process_upload(self, nid: int):
        # 1. Check if the file is still being actively written to
        if self.fs.is_busy(nid):
            log.debug("Node %s is still busy; delaying upload", nid)
            self.enqueue(nid, delay=self.cfg.upload_delay)
            return

        # 2. Lookup node in index
        node = self.index.get(nid)
        if node is None or node["is_dir"] or node["state"] == "synced":
            self._failures.pop(nid, None)
            self._drop_progress(nid)
            return

        staging_path = self.fs.staging_path(nid)
        if not os.path.exists(staging_path):
            log.warning("Staging file missing for node %s (%s)", nid, self.index.path_of(nid))
            return

        version = node["version"]
        name = node["name"]
        path = self.index.path_of(nid)
        file_size = os.path.getsize(staging_path)
        pinned = self.index.is_pinned(nid)

        # 3. Handle empty (0-byte) files
        if file_size == 0:
            if self.fs.commit_upload(nid, version, []):
                log.info("Uploaded empty file %s", path)
            return

        # 4. Chunk and upload
        chunk_size = self.cfg.chunk_size
        uploaded_chunks = []
        chunk_idx = 0

        try:
            with open(staging_path, "rb") as f:
                uploaded_chunks = self._resume_point(nid, f, version, file_size, chunk_size)
                chunk_idx = len(uploaded_chunks)
                total = (file_size + chunk_size - 1) // chunk_size
                if chunk_idx:
                    log.info("Resuming upload of %s at piece %d of %d", path, chunk_idx + 1, total)
                else:
                    log.info("Starting upload of %s (%d bytes, version %d)", path, file_size, version)
                f.seek(chunk_idx * chunk_size)
                last_report = time.time()
                while True:
                    if not self._running:
                        raise _Interrupted("shutting down")
                    if self.fs.is_busy(nid):
                        raise _Interrupted("file is being written to")
                    if self.index.get(nid) is None:
                        raise _Interrupted("file was deleted")

                    chunk_data = f.read(chunk_size)
                    if not chunk_data:
                        break

                    sha256 = hashlib.sha256(chunk_data).hexdigest()

                    if self.crypto:
                        upload_data = self.crypto.encrypt(chunk_data)
                        # Discord sees neither the original name nor the extension
                        filename = f"chk_{secrets.token_hex(8)}.bin"
                        content = ""
                    else:
                        upload_data = chunk_data
                        safe_name = name.replace(" ", "_")
                        filename = f"{safe_name}.part{chunk_idx:04d}"
                        content = (
                            f"DiscordDrive chunk #{chunk_idx} for `{name}`\n"
                            f"Size: {len(chunk_data)} bytes | Hash: {sha256[:16]}"
                        )

                    stored = self.backend.upload(filename, upload_data, content=content)
                    uploaded_chunks.append({
                        "idx": chunk_idx,
                        "message_id": stored.message_id,
                        "attachment_id": stored.attachment_id,
                        "url": stored.url,
                        "size": len(chunk_data),
                        "sha256": sha256,
                    })
                    self._save_progress(nid, version, file_size, chunk_size, uploaded_chunks)
                    done = len(uploaded_chunks)
                    if total > 1 and done < total and (done % 25 == 0 or time.time() - last_report >= 30):
                        last_report = time.time()
                        log.info("Uploading %s: %d of %d pieces (%d%%)", path, done, total, done * 100 // total)
                    if pinned:
                        # Offline-pinned: keep a local copy so it never has to be downloaded again
                        try:
                            self.fs.cache.put(stored.message_id, chunk_data, persist=True)
                        except Exception as ce:
                            log.debug("Could not cache chunk of pinned node %s: %s", nid, ce)
                    chunk_idx += 1

        except _Interrupted as why:
            # The pieces uploaded so far are recorded; the next attempt continues from there
            # (if the file is changed meanwhile, the record no longer matches and is discarded).
            if self.index.get(nid) is None:
                log.info("Stopped uploading %s: the file was deleted", path)
                self._drop_progress(nid)   # its uploaded pieces go to the trash
                self.fs._remove_staging(nid)  # Windows can't delete it while we had it open
                return
            if self._running:
                log.info("Upload of %s interrupted (%s); will continue later", path, why)
                self.enqueue(nid, delay=self.cfg.upload_delay)
            return
        except Exception as e:
            if self.index.get(nid) is None:
                self._drop_progress(nid)
            else:
                self.index.update(nid, state="error")
            delay = self._retry_later(nid)
            log.error("Failed uploading chunk %d for %s: %s (retrying in %.0fs)", chunk_idx, path, e, delay)
            return

        # 5. Commit freshly uploaded chunks (commit_upload trashes them if the file changed meanwhile)
        self._drop_progress(nid, trash=False)
        if self.fs.commit_upload(nid, version, uploaded_chunks):
            self._failures.pop(nid, None)
            if self.journal is not None:
                self.journal.wake()  # publish the new file to other devices right away
            log.info("Successfully uploaded %s (%d bytes across %d chunk(s))", path, file_size, len(uploaded_chunks))
        elif self.index.get(nid) is not None:
            log.info("%s changed during upload; re-queued", path)
            self.enqueue(nid, delay=self.cfg.upload_delay)

    def _resume_point(self, nid, f, version, file_size, chunk_size):
        """Pieces already uploaded for exactly this content, checked against the local file."""
        rec = self._load_progress(nid)
        if not rec:
            return []
        if rec.get("v") != version or rec.get("size") != file_size or rec.get("chunk_size") != chunk_size:
            self._drop_progress(nid)
            return []
        good = []
        for c in rec.get("chunks") or []:
            f.seek(c["idx"] * chunk_size)
            data = f.read(chunk_size)
            if c["idx"] != len(good) or len(data) != c["size"] or hashlib.sha256(data).hexdigest() != c["sha256"]:
                break
            good.append(c)
        stale = [c["message_id"] for c in (rec.get("chunks") or [])[len(good):]]
        if stale:
            self.index.trash_add(stale)
        return good

    # -------------------------------------------------------- backup & trash
    def _trash_loop(self):
        while self._running:
            try:
                time.sleep(15.0)
                if not self._running:
                    break
                if not self.cfg.delete_remote:
                    continue

                batch = self.index.trash_batch(10)
                if not batch:
                    continue

                for mid in batch:
                    if not self._running:
                        break
                    try:
                        self.backend.delete(mid)
                        self.index.trash_remove(mid)
                    except Exception as e:
                        log.debug("Failed deleting trashed message %s: %s", mid, e)
                        break  # back off until next round
            except Exception as e:
                log.error("Error during trash cleanup: %s", e)
