"""DiscordDrive runtime coordinator and mount manager."""

import errno
import logging
import os
import secrets
import signal
import subprocess
import sys
import threading

from .backend import DiscordBackend, LocalBackend, is_encrypted_index
from .cache import ChunkCache
from .config import Config
from .crypto import CryptoEngine, generate_key, parse_key
from .discord_api import DiscordAPI
from .fs import DiscordDriveFS
from .fuse_loader import find_winfsp_dll, fuse, FUSE_ERROR
from .index import Index
from .journal import Journal
from .uploader import Uploader

log = logging.getLogger("discorddrive.drive")


class DiscordDrive:
    def __init__(self, cfg: Config = None, local_test_dir: str = None):
        self.cfg = cfg or Config.load()
        self.local_test_dir = local_test_dir

        self.crypto = None
        self.api = None
        self.backend = None
        self.index = None
        self.cache = None
        self.fs = None
        self.uploader = None
        self.journal = None
        self._stop_event = threading.Event()
        self._stop_lock = threading.Lock()
        self._stopped = False

    def initialize(self):
        data_dir = self.cfg.resolved_data_dir
        staging_dir = os.path.join(data_dir, "staging")
        cache_dir = os.path.join(data_dir, "cache")
        db_path = os.path.join(data_dir, "index.db")

        os.makedirs(staging_dir, exist_ok=True)
        os.makedirs(cache_dir, exist_ok=True)

        if self.local_test_dir:
            log.info("Running in mock mode using local directory: %s", self.local_test_dir)
            self.backend = LocalBackend(self.local_test_dir)
        else:
            if not self.cfg.is_configured():
                raise ValueError(
                    "DiscordDrive is not configured yet. Run 'discorddrive setup' or provide bot_token and channel_id."
                )
            self.api = DiscordAPI(self.cfg.bot_token)
            self.backend = DiscordBackend(self.api, self.cfg.channel_id)

        if self.cfg.encryption_enabled:
            if not self.cfg.encryption_key:
                self._generate_key_if_safe()
            # Never fall back to uploading plaintext because of a bad key.
            try:
                self.crypto = CryptoEngine(parse_key(self.cfg.encryption_key))
            except Exception as e:
                raise RuntimeError(f"Encryption is enabled but the key could not be loaded: {e}") from e
            self.backend.crypto = self.crypto
            log.info("Zero-knowledge AES-256-GCM encryption ACTIVE.")

        if not self.cfg.device_id:
            self.cfg.device_id = secrets.token_hex(4)
            if not self.local_test_dir:
                # Persist only the id, not one-off command-line overrides such as --cache.
                saved = Config.load()
                saved.device_id = self.cfg.device_id
                saved.save()

        self.index = Index(db_path)
        self.index.keep_versions = bool(self.cfg.keep_versions)
        self.journal = Journal(self.cfg, self.index, self.backend, crypto=self.crypto, staging_dir=staging_dir)
        self.journal.bootstrap()

        self.cache = ChunkCache(
            cache_dir,
            max_bytes=self.cfg.cache_max_bytes,
            backend=self.backend,
            index=self.index,
            threads=self.cfg.download_threads,
            crypto=self.crypto,
            memory_bytes=self._memory_cache_bytes(),
        )
        if self.cache.memory_mode:
            freed = self.cache.free_space()
            log.info("Memory-only cache (%d MiB of RAM): viewed files are not stored on disk%s.",
                     self.cache.memory_bytes // 2**20,
                     f"; removed {freed / 2**20:.1f} MiB of previously cached data" if freed else "")

        self.fs = DiscordDriveFS(self.cfg, self.index, self.cache, staging_dir)
        self.uploader = Uploader(self.cfg, self.index, self.backend, self.fs, crypto=self.crypto)
        self.fs.uploader = self.uploader
        self.uploader.journal = self.journal
        self.journal.fs = self.fs

        # Recover any pending staging files from previous runs
        self.fs.recover()

    def _memory_cache_bytes(self):
        mode = (self.cfg.cache_mode or "disk").lower()
        if mode not in ("disk", "memory"):
            raise ValueError(f"cache_mode must be 'disk' or 'memory', not {self.cfg.cache_mode!r}")
        if mode == "disk":
            return 0
        # Room for the chunk being read plus read-ahead, whatever the setting says.
        return max(int(self.cfg.memory_cache_bytes or 0), (self.cfg.prefetch_chunks + 2) * self.cfg.chunk_size)

    def _generate_key_if_safe(self):
        """Auto-generate a key for a brand-new drive, but never for a channel that already holds encrypted data."""
        try:
            latest = self.backend.find_latest_index()
        except Exception as e:
            raise RuntimeError(
                f"No encryption key is configured and Discord could not be checked for existing data ({e}). "
                "Run 'discorddrive setup' to configure a key."
            ) from e
        if latest is not None and is_encrypted_index(latest):
            raise RuntimeError(
                "This channel already contains an encrypted DiscordDrive, but no encryption key is configured. "
                "Copy 'encryption_key' from the config of the machine that created it, or run "
                "'discorddrive setup -p <passphrase>' with the same passphrase."
            )
        self.cfg.encryption_key = generate_key().hex()
        self.cfg.save()
        log.info("Auto-generated and saved a new 256-bit AES master encryption key. Back it up!")

    def start_background_services(self):
        if self.uploader:
            self.uploader.start()
        if self.journal:
            self.journal.start()

    def stop_background_services(self):
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
        if self.uploader:
            self.uploader.stop()
        if self.journal:
            self.journal.stop()  # publishes the last changes and saves a checkpoint
        if self.cache:
            self.cache.shutdown()
        if self.index:
            self.index.close()
        if self.crypto:
            self.crypto.close()

    def mount(self, mount_point: str = None, foreground: bool = True):
        if FUSE_ERROR:
            raise RuntimeError(FUSE_ERROR)
        if sys.platform == "win32":
            dll = find_winfsp_dll()
            if not dll:
                raise RuntimeError(
                    "WinFsp not found. Please install WinFsp from https://winfsp.dev/rel/ to mount virtual drives."
                )

        mp = mount_point or self.cfg.mount_point
        volname = self.cfg.volume_name or "DiscordDrive"

        if sys.platform != "win32":
            _prepare_mount_dir(mp)

        self.initialize()
        self.start_background_services()

        log.info("Mounting DiscordDrive on %s...", mp)

        # Handle graceful shutdown
        def _sig_handler(sig, frame):
            log.info("Received signal %s; shutting down...", sig)
            self._stop_event.set()
            self.stop_background_services()
            sys.exit(0)

        try:
            if sys.platform == "win32":
                signal.signal(signal.SIGINT, _sig_handler)
                signal.signal(signal.SIGTERM, _sig_handler)
            else:
                # The main thread sits inside libfuse's C loop, where Python handlers never
                # run. With default dispositions libfuse installs its own SIGINT/SIGTERM/SIGHUP
                # handlers, which unmount and return from fuse_main -> cleanup in `finally`.
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
        except (ValueError, AttributeError):
            pass

        pid_file = os.path.join(self.cfg.resolved_data_dir, "discorddrive.pid")
        try:
            with open(pid_file, "w") as f:
                f.write(str(os.getpid()))
        except Exception:
            pass

        fuse_kwargs = {
            "foreground": foreground,
            "fsname": "DiscordDrive",
        }
        if sys.platform in ("win32", "darwin"):
            fuse_kwargs["volname"] = volname
        else:
            allow_other = getattr(self.cfg, "allow_other", False)
            if not allow_other:
                try:
                    if hasattr(os, "getuid") and os.getuid() == 0:
                        allow_other = True
                    elif os.path.exists("/etc/fuse.conf"):
                        with open("/etc/fuse.conf", "r") as f:
                            for line in f:
                                if line.strip().startswith("user_allow_other"):
                                    allow_other = True
                                    break
                except Exception:
                    pass
            if allow_other:
                fuse_kwargs["allow_other"] = True

        try:
            fuse.FUSE(
                self.fs,
                mp,
                **fuse_kwargs,
            )
        finally:
            log.info("Unmounting DiscordDrive from %s...", mp)
            try:
                if os.path.exists(pid_file):
                    os.remove(pid_file)
            except Exception:
                pass
            self.stop_background_services()


def _prepare_mount_dir(mp):
    """Create the mount directory, clear a stale FUSE mount left by a crash, and refuse
    to mount over existing files (they would be hidden, which looks like data loss)."""
    try:
        os.makedirs(mp, exist_ok=True)
        entries = os.listdir(mp)
    except OSError as e:
        if e.errno != errno.ENOTCONN:
            raise
        log.warning("Clearing stale mount on %s (previous instance did not exit cleanly)", mp)
        subprocess.run(["fusermount", "-uz", mp], capture_output=True)
        entries = os.listdir(mp)
    if os.path.ismount(mp):
        raise RuntimeError(f"Something is already mounted on {mp}. Run 'discorddrive stop' first.")
    if entries:
        raise RuntimeError(
            f"Mount directory {mp} is not empty; mounting over it would hide those files. "
            "Move them elsewhere or choose another mount point (discorddrive setup -m <dir>)."
        )
