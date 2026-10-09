"""Configuration handling.

Windows: config in %APPDATA%\\DiscordDrive\\config.json, data (index, caches) in
%LOCALAPPDATA%\\DiscordDrive.
Linux:   config in ~/.config/DiscordDrive/config.json, data in ~/.local/share/DiscordDrive.

Nothing is ever read from the current directory or the source checkout, so the
bot token and encryption key never end up inside a git repository or synced folder.
"""

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field, fields

APP_NAME = "DiscordDrive"


def default_config_dir() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg, APP_NAME)


def default_data_dir() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME)
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(xdg, APP_NAME)


DEFAULT_CONFIG_PATH = os.path.join(default_config_dir(), "config.json")


def parse_size(text: str) -> int:
    """'1500', '500M', '2G', '1.5T', '2GB' or '2GiB' -> bytes (binary units)."""
    t = text.strip().upper().replace(" ", "")
    for suffix in ("IB", "B"):
        if t.endswith(suffix) and len(t) > len(suffix) and t[-len(suffix) - 1] in "KMGT":
            t = t[:-len(suffix)]
            break
    mult = {"K": 2**10, "M": 2**20, "G": 2**30, "T": 2**40}.get(t[-1:], 1)
    if mult > 1:
        t = t[:-1]
    value = float(t)
    if value < 0:
        raise ValueError("must not be negative")
    return int(value * mult)


def format_size(n: int) -> str:
    for unit, mult in (("T", 2**40), ("G", 2**30), ("M", 2**20), ("K", 2**10)):
        if n >= mult:
            return f"{n / mult:.4g}{unit}"
    return f"{n} bytes"


def launcher() -> str:
    """How users run DiscordDrive commands on this system (for messages)."""
    return "run.bat" if sys.platform == "win32" else "./run.sh"


def config_path() -> str:
    """The config file in use (DISCORDDRIVE_CONFIG overrides the default location)."""
    return os.environ.get("DISCORDDRIVE_CONFIG") or DEFAULT_CONFIG_PATH

MiB = 1024 * 1024


@dataclass
class Config:
    bot_token: str = ""
    channel_id: str = ""
    mount_point: str = "Z:"
    volume_name: str = "DiscordDrive"
    # Discord's attachment limit for bots in a non-boosted server is 10 MiB.
    # Raise this if your server is boosted (Level 2: 50 MiB, Level 3: 100 MiB).
    chunk_size: int = 9 * MiB
    data_dir: str = ""                 # default: %LOCALAPPDATA%\DiscordDrive
    cache_max_bytes: int = 5 * 1024 * MiB
    cache_mode: str = "disk"           # "disk": keep viewed chunks on disk | "memory": RAM only, nothing on disk
    memory_cache_bytes: int = 256 * MiB  # RAM used for viewed chunks in memory mode
    upload_delay: float = 2.0          # seconds to wait after a file is closed before uploading
    prefetch_chunks: int = 2           # chunks to read ahead while streaming
    download_threads: int = 4
    upload_threads: int = 3            # chunks/files uploaded in parallel
    staging_max_bytes: int = 10 * 1024 * MiB  # pause new file creation while this much is waiting to upload (0 = no limit)
    min_free_disk_bytes: int = 2 * 1024 * MiB  # also pause while the local disk has less free space than this
    max_file_size: int = 0             # refuse files larger than this (0 = no limit)
    delete_remote: bool = True         # delete Discord messages when files are deleted/overwritten
    index_backup_interval: float = 600.0  # seconds between index checkpoints (when something changed)
    poll_interval: float = 2.0         # seconds between checks for changes made on other devices
    keep_versions: bool = True         # keep replaced/deleted file contents as restorable versions
    version_retention_days: float = 30.0  # drop versions older than this (0 = keep forever)
    max_versions: int = 0              # max versions kept per file (0 = no limit)
    device_id: str = ""                # random id of this device (generated on first mount)
    encryption_enabled: bool = True    # Zero-knowledge AES-256-GCM encryption
    encryption_key: str = ""           # 64-char hex string (256-bit key)
    encryption_salt: str = ""          # 32-char hex string
    old_encryption_keys: list = field(default_factory=list)  # earlier keys, kept to read older data
    allow_other: bool = False          # Allow other users/services to access mount on Linux
    extra_bot_tokens: list = field(default_factory=list)  # more bots in the same channel = faster uploads
    compression: bool = True           # compress pieces that shrink (lossless, before encryption)
    dedup: bool = True                 # store identical pieces once
    parity_enabled: bool = True        # spare pieces, so lost pieces can be rebuilt (self-healing)
    parity_group: int = 10             # data pieces per group...
    parity_pieces: int = 2             # ...and spare pieces per group (groups under 4 pieces get 1)
    scrub_enabled: bool = True         # check in the background that every piece is still on Discord
    scrub_days: float = 7.0            # how long one full check of every piece takes
    protect_existing: bool = True      # add spare pieces to files uploaded before self-healing existed
    snapshot_interval_hours: float = 24.0  # automatic snapshot of the whole drive (0 = off)
    snapshot_keep_days: float = 14.0   # how long snapshots are kept
    hidden_folders: list = field(default_factory=list)  # folders this device doesn't show
    web_enabled: bool = True           # the web dashboard (http://127.0.0.1:<web_port>)
    web_port: int = 8765
    web_hosts: list = field(default_factory=list)  # extra names the dashboard answers to (reverse proxy domains)
    web_lan: bool = False              # also reachable from other devices on your network (phone)
    web_token: str = ""                # secret that signs dashboard sessions and share links (generated)
    web_user: str = ""                 # dashboard sign-in: user name...
    web_password: str = ""             # ...and a scrypt hash of the password (set with 'web-password')

    @property
    def resolved_data_dir(self) -> str:
        return self.data_dir or default_data_dir()

    @classmethod
    def load(cls, path: str = None) -> "Config":
        path = path or config_path()
        cfg = cls()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as e:
                try:
                    # Forgive a comma after the last entry, the most common hand-editing slip.
                    raw = json.loads(re.sub(r",(\s*[}\]])", r"\1", text))
                except json.JSONDecodeError:
                    raise SystemExit(
                        f"[ERROR] The config file {path} is not valid JSON (line {e.lineno}, column {e.colno}: "
                        f"{e.msg}).\n        Usually a missing comma between two entries."
                    ) from None
            known = {f.name for f in fields(cls)}
            for k, v in raw.items():
                if k in known:
                    setattr(cfg, k, v)
        # Environment overrides (handy for scripts / not storing the token on disk).
        cfg.bot_token = os.environ.get("DISCORDDRIVE_TOKEN", cfg.bot_token)
        cfg.channel_id = os.environ.get("DISCORDDRIVE_CHANNEL", cfg.channel_id)
        cfg.mount_point = normalize_mount_point(cfg.mount_point)
        return cfg

    def save(self, path: str = None) -> None:
        path = path or config_path()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        # The file holds the bot token and encryption key: keep it private on POSIX.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)
        if sys.platform != "win32":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.channel_id)


def normalize_mount_point(mp: str) -> str:
    mp = (mp or "").strip()
    if sys.platform == "win32":
        if len(mp) == 1 and mp.isalpha():
            return mp.upper() + ":"
        if len(mp) in (2, 3) and mp[0].isalpha() and mp[1] == ":":
            return mp[0].upper() + ":"
        return mp or "Z:"
    else:
        if not mp or (len(mp) <= 2 and mp.endswith(":")):
            return os.path.expanduser("~/discorddrive")
        return os.path.abspath(os.path.expanduser(mp))
