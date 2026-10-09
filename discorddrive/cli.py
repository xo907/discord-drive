"""Command-line interface for DiscordDrive."""

import argparse
import json
import logging
import os
import subprocess
import sys
import time

from .backend import DiscordBackend, is_encrypted_index
from .cache import ChunkCache
from .config import Config, config_path, default_data_dir, format_size, launcher, normalize_mount_point, parse_size
from .crypto import AuthenticationError, CryptoEngine, KeyRing, channel_salt, derive_key, generate_key, key_fingerprint, parse_key
from .discord_api import DiscordAPI, DiscordError
from .drive import DiscordDrive
from .fuse_loader import find_winfsp_dll, find_linux_fuse_lib, unmount, FUSE_ERROR
from .index import Index
from .journal import Journal
from .ui import embedded, theme_output

log = logging.getLogger("discorddrive.cli")


def is_mounted(mount_point: str) -> bool:
    """True if DiscordDrive (or anything) is mounted at the given drive letter / directory."""
    if sys.platform == "win32":
        letter = mount_point.rstrip(":\\")
        return os.path.exists(letter + ":\\")
    return os.path.ismount(mount_point)


def setup_logging(verbose: bool = False, log_to_file: bool = True):
    level = logging.DEBUG if verbose else logging.INFO
    handlers = []
    if sys.stderr is not None:
        try:
            handlers.append(logging.StreamHandler(sys.stderr))
        except Exception:
            pass
    if log_to_file:
        try:
            log_dir = default_data_dir()
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "discorddrive.log")
            handlers.append(logging.FileHandler(log_path, mode="a", encoding="utf-8"))
        except Exception:
            pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers if handlers else None,
        force=True,
    )


def normalize_virtual_path(p: str, mount_point: str = "Z:") -> str:
    p = p.strip().replace("\\", "/")
    mp = mount_point.replace("\\", "").rstrip(":")
    if len(p) >= 2 and p[1] == ":":
        p = p[2:]
    p = "/" + p.lstrip("/")
    return p


def get_crypto_from_cfg(cfg: Config):
    """KeyRing for the configured key(s), or None if encryption is off.

    Exits on a broken key: silently continuing would upload plaintext.
    """
    if not cfg.encryption_enabled:
        return None
    if not cfg.encryption_key:
        raise SystemExit(f"[ERROR] Encryption is enabled but no key is configured. Run '{launcher()} setup'.")
    try:
        return KeyRing.from_hex(cfg.encryption_key, cfg.old_encryption_keys)
    except Exception as e:
        raise SystemExit(f"[ERROR] Failed to load encryption key: {e}")


def cmd_setup(args):
    setup_logging(args.verbose)
    cfg = Config.load()
    if not embedded():
        print("=" * 60)
        print("          DiscordDrive Configuration Setup")
        print("=" * 60)
    print()

    token = args.token or cfg.bot_token
    if not token:
        try:
            token = input("Enter Discord Bot Token: ").strip()
        except EOFError:
            pass

    channel_id = args.channel or cfg.channel_id
    if not channel_id:
        try:
            channel_id = input("Enter Private Discord Channel ID: ").strip()
        except EOFError:
            pass

    mount_point = args.mount or cfg.mount_point or "Z:"
    if not args.mount:
        label = "Drive Letter" if sys.platform == "win32" else "Mount Directory"
        try:
            val = input(f"Enter Mount Point {label} [{mount_point}]: ").strip()
            if val:
                mount_point = val
        except EOFError:
            pass
    mount_point = normalize_mount_point(mount_point)

    if not token or not channel_id:
        print("\n[ERROR] Bot token and channel ID are required.")
        return 1

    print("\nValidating Discord bot credentials and permissions...")
    api = DiscordAPI(token, timeout=30, retries=3)
    try:
        bot_user = api.get_me()
        bot_name = f"{bot_user.get('username')}#{bot_user.get('discriminator', '0')}"
        print(f"  [OK] Authenticated as Bot: {bot_name} (ID: {bot_user.get('id')})")
    except DiscordError as e:
        print(f"  [FAIL] Failed to authenticate bot: {e}")
        return 1

    try:
        channel = api.get_channel(channel_id)
        ch_name = channel.get("name", channel_id)
        guild_id = channel.get("guild_id", "DM")
        print(f"  [OK] Channel accessible: #{ch_name} in Server ID: {guild_id}")
    except DiscordError as e:
        print(f"  [FAIL] Failed to access channel {channel_id}: {e}")
        print("         Make sure the bot has been invited to your server and has access to this channel!")
        return 1

    # Check WinFsp / FUSE
    if sys.platform == "win32":
        dll = find_winfsp_dll()
        if dll:
            print(f"  [OK] WinFsp driver found: {dll}")
        else:
            print("  [WARNING] WinFsp was not found! Install it from https://winfsp.dev/rel/ to mount virtual drives.")
    else:
        lib = find_linux_fuse_lib()
        if lib:
            print(f"  [OK] Linux FUSE library found: {lib}")
        else:
            print("  [WARNING] libfuse2 was not found! Open ./run.sh -> Tools -> Install requirements (or: apt install libfuse2)")

    # Configure End-to-End Encryption
    print("\nConfiguring Zero-Knowledge Encryption (AES-256-GCM)...")
    enc_enabled = True
    enc_key_hex = cfg.encryption_key
    enc_salt_hex = cfg.encryption_salt
    received_old_keys = []

    # Is there already an encrypted drive in this channel? Then a new random key would be useless.
    existing_encrypted = False
    try:
        latest = DiscordBackend(api, channel_id).find_latest_index()
        existing_encrypted = latest is not None and is_encrypted_index(latest)
    except Exception as e:
        log.debug("Could not look for an existing index backup: %s", e)

    if getattr(args, "key", None):
        try:
            enc_key_hex = parse_key(args.key).hex()
        except ValueError as e:
            print(f"  [FAIL] Invalid --key: {e}")
            return 1
        enc_salt_hex = ""
        enc_enabled = True
        print(f"  [OK] Custom encryption key configured (fingerprint {key_fingerprint(enc_key_hex)}).")
    elif getattr(args, "passphrase", None):
        salt = channel_salt(channel_id)
        key, _ = derive_key(args.passphrase, salt)
        enc_key_hex = key.hex()
        enc_salt_hex = salt.hex()
        enc_enabled = True
        print(f"  [OK] Key derived from provided passphrase (fingerprint {key_fingerprint(enc_key_hex)}).")
    elif not enc_key_hex and existing_encrypted:
        print("  [!] This channel already holds an encrypted DiscordDrive. How do you want to get its key?")
        print("      1) Request it from one of your other devices (recommended)")
        print("      2) Enter the encryption password")
        print("      3) Paste the key (from 'export-key' on another device)")
        try:
            how = input("Choose 1, 2 or 3 [1]: ").strip() or "1"
        except EOFError:
            how = "1"
        if how == "2":
            try:
                passphrase = input("Encryption password: ").strip()
            except EOFError:
                passphrase = ""
            if not passphrase:
                print("  [FAIL] No password entered.")
                return 1
            salt = channel_salt(channel_id)
            enc_key_hex = derive_key(passphrase, salt)[0].hex()
            enc_salt_hex = salt.hex()
        elif how == "3":
            try:
                enc_key_hex = parse_key(input("Key: ")).hex()
            except (ValueError, EOFError) as e:
                print(f"  [FAIL] Not a valid key: {e}")
                return 1
            enc_salt_hex = ""
        else:
            payload = _request_key(DiscordBackend(api, channel_id))
            if payload is None:
                return 1
            enc_key_hex = payload["key"]
            received_old_keys = payload.get("old") or []
            enc_salt_hex = ""
        enc_enabled = True
        print(f"  [OK] Key ready (fingerprint {key_fingerprint(enc_key_hex)}).")
    elif not enc_key_hex:
        try:
            enc_ans = input("Enable Zero-Knowledge Encryption? (Discord will see only encrypted data) [Y/n]: ").strip().lower()
        except EOFError:
            enc_ans = "y"
        if enc_ans != "n":
            try:
                passphrase = input("Enter an Encryption Password (or press Enter to auto-generate a random key): ").strip()
            except EOFError:
                passphrase = ""
            if passphrase:
                salt = channel_salt(channel_id)
                key, _ = derive_key(passphrase, salt)
                enc_key_hex = key.hex()
                enc_salt_hex = salt.hex()
                print("  [OK] Key derived with PBKDF2-HMAC-SHA256 (200,000 iterations).")
                print("       Use the same passphrase and channel on other machines to get the same key.")
            elif existing_encrypted:
                print("  [FAIL] Refusing to generate a new key for a channel that already holds encrypted data.")
                return 1
            else:
                key = generate_key()
                enc_key_hex = key.hex()
                enc_salt_hex = ""
                print("  [OK] Generated random 256-bit AES master key.")
                print("       BACK IT UP: without 'encryption_key' from the config file your data is unrecoverable.")
            enc_enabled = True
        else:
            enc_enabled = False
            enc_key_hex = ""
            enc_salt_hex = ""
            print("  [WARNING] Encryption disabled.")
    else:
        print(f"  [OK] Existing encryption key retained (fingerprint {key_fingerprint(enc_key_hex)}).")

    # Never throw a key away: data written with it would become unreadable.
    old_keys = [k for k in cfg.old_encryption_keys if k != enc_key_hex]
    for k in received_old_keys:
        if k != enc_key_hex and k not in old_keys:
            old_keys.append(k)
    if cfg.encryption_key and cfg.encryption_key != enc_key_hex and cfg.encryption_key not in old_keys:
        old_keys.append(cfg.encryption_key)
        print(f"  [OK] Previous key (fingerprint {key_fingerprint(cfg.encryption_key)}) kept for reading older files.")

    # A key that cannot read the drive already in this channel would only fail later, at mount.
    if existing_encrypted and enc_enabled and enc_key_hex:
        print("Checking the key against the drive already stored in this channel...")
        crypto = KeyRing.from_hex(enc_key_hex, old_keys)
        try:
            DiscordBackend(api, channel_id, crypto=crypto).load_index_message(latest)
            print("  [OK] The key matches the existing drive.")
        except AuthenticationError:
            print("  [FAIL] This key cannot read the drive already stored in this channel. Nothing was saved.")
            print("         Copy the key from a device where the drive works:")
            print(f"           on that device:  {launcher()} export-key")
            print(f"           on this device:  {launcher()} setup -k <the key it shows>")
            print("         (Drives set up with older versions derived keys from passwords differently,")
            print("          so the same password can give a different key.)")
            return 1
        except Exception as e:
            print(f"  [WARNING] Could not verify the key right now ({e}); saving it anyway.")
        finally:
            crypto.close()

    cfg.bot_token = token
    cfg.channel_id = channel_id
    cfg.mount_point = mount_point
    cfg.encryption_enabled = enc_enabled
    cfg.encryption_key = enc_key_hex
    cfg.encryption_salt = enc_salt_hex
    cfg.old_encryption_keys = old_keys
    cfg.save()

    print(f"\n[SUCCESS] Configuration saved to: {config_path()}")
    if existing_encrypted and not is_mounted(cfg.mount_point):
        _catch_up(cfg)
    print(f"Start the drive from the menu ({launcher()}, option 1), or run: {launcher()} start")
    return 0


def _request_key(backend):
    """New device: ask another device for the key. Returns {'key', 'old'} or None."""
    from . import keyshare
    req = keyshare.KeyRequest(backend)
    req.post()
    print()
    print("--- Waiting for another device to approve ---")
    print(f"Verification code:  {req.code}")
    print(f"On a device that already has the key, open the menu ({launcher()}) and choose")
    print("'Approve a new device'. Check it shows the same code, then accept.")
    print("Waiting up to 10 minutes. Press Ctrl+C to cancel.")
    try:
        payload = req.wait(timeout=600)
    except KeyboardInterrupt:
        req._cleanup()
        print("\n[!] Cancelled.")
        return None
    except keyshare.Rejected as e:
        print(f"[FAIL] {e}")
        return None
    except TimeoutError:
        print("[FAIL] Nobody approved the request within 10 minutes. Run it again when ready.")
        return None
    try:
        payload["key"] = parse_key(payload.get("key", "")).hex()
        payload["old"] = [parse_key(k).hex() for k in payload.get("old") or []]
    except ValueError as e:
        print(f"[FAIL] The received key is not valid: {e}")
        return None
    print(f"[OK] Key received from your other device (fingerprint {key_fingerprint(payload['key'])}).")
    return payload


def _catch_up(cfg):
    """Bring this device's file list fully up to date: latest checkpoint + every change since."""
    print()
    print("--- Catching up with your drive ---")
    idx, j, crypto = _open_journal(cfg)
    try:
        latest = j.backend.find_latest_index()
        if latest is None:
            print("[OK] The drive is still empty.")
            return
        j.restore(latest)
        j.poll()
        st = idx.stats(max_age=0)
        print(f"[OK] Up to date: {st['files']:,} files in {st['dirs']:,} folders.")
    except Exception as e:
        print(f"[WARNING] Could not catch up right now ({e}); it happens automatically on the first start.")
    finally:
        _close(idx, crypto)


def cmd_request_key(args):
    """Ask one of your other devices for the encryption key (e.g. after a key mix-up)."""
    setup_logging(args.verbose)
    cfg = Config.load()
    if not cfg.is_configured():
        print(f"[ERROR] Run '{launcher()} setup' first.")
        return 1
    backend = DiscordBackend(DiscordAPI(cfg.bot_token, timeout=60, retries=3), cfg.channel_id)
    payload = _request_key(backend)
    if payload is None:
        return 1
    saved = Config.load()
    keys = [payload["key"]] + payload["old"]
    if saved.encryption_key and saved.encryption_key not in keys:
        keys.append(saved.encryption_key)           # never lose a key
    saved.encryption_enabled = True
    saved.encryption_key = payload["key"]
    saved.old_encryption_keys = [k for k in dict.fromkeys(keys[1:] + saved.old_encryption_keys)
                                 if k != payload["key"]]
    saved.save()
    print("[OK] Saved.")
    if is_mounted(saved.mount_point):
        print(f"[!] Restart the drive (stop, then start) so it uses the new key.")
    else:
        _catch_up(saved)
    return 0


def cmd_approve_keys(args):
    """Device with the key: approve (or reject) another device asking for it."""
    from . import keyshare
    setup_logging(args.verbose)
    cfg = Config.load()
    if not cfg.is_configured() or not cfg.encryption_key:
        print("[ERROR] This device has no encryption key to share.")
        return 1
    backend = DiscordBackend(DiscordAPI(cfg.bot_token, timeout=60, retries=3), cfg.channel_id)
    print("Looking for devices asking for the key (requests from the last 15 minutes)...")
    try:
        pending = keyshare.pending_requests(backend)
        if not pending:
            print("None yet. Start the request on the new device: setup, option 1.")
            print("Waiting for one... (Ctrl+C to stop)")
            end = time.time() + 600
            while not pending and time.time() < end:
                time.sleep(3)
                pending = keyshare.pending_requests(backend)
        if not pending:
            print("[!] No request arrived.")
            return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    print()
    for i, r in enumerate(pending, 1):
        age = max(0, int(time.time() - r["time"]))
        print(f"  {i}) {r['device']}, {age // 60} min {age % 60} s ago, code {r['code']}")
    print()
    try:
        pick = input(f"Which request? [1]: ").strip() or "1"
        req = pending[int(pick) - 1]
    except (ValueError, IndexError, EOFError):
        print("[!] Nothing chosen.")
        return 0
    print()
    print(f"The new device must show this code:  {req['code']}")
    try:
        same = input("Does it show exactly the same code? [y/N]: ").strip().lower().startswith("y")
    except EOFError:
        same = False
    if not same:
        keyshare.answer(backend, req, False)
        print("[OK] Rejected. If you didn't start this request yourself, someone else may have your bot")
        print("     token: reset it in the Discord Developer Portal.")
        return 0
    keyshare.answer(backend, req, True, {"key": cfg.encryption_key, "old": cfg.old_encryption_keys})
    print("[SUCCESS] Key sent (encrypted, only the new device can read it).")
    print("          The new device now catches up with your files by itself.")
    return 0


_SECRET_FIELDS = {"bot_token", "encryption_key", "encryption_salt", "old_encryption_keys"}


def cmd_config(args):
    """Show or change one setting: `config`, `config <key>`, `config <key> <value>`."""
    import dataclasses
    cfg = Config.load()
    types = {f.name: f.type for f in dataclasses.fields(Config)}
    if not args.key:
        for name in types:
            value = getattr(cfg, name)
            shown = (f"({len(value)} key(s))" if isinstance(value, list) else "(set)") \
                if name in _SECRET_FIELDS and value else value
            print(f"{name:24} {shown}")
        print(f"\nConfig file: {config_path()}  (restart the drive after changing settings)")
        return 0
    if args.key not in types:
        print(f"[ERROR] Unknown setting '{args.key}'. Run 'config' to list them.")
        return 1
    if args.value is None:
        value = getattr(cfg, args.key)
        print("(set)" if args.key in _SECRET_FIELDS and value else value)
        return 0
    if args.key in ("bot_token", "channel_id", "encryption_key", "encryption_salt", "encryption_enabled",
                    "old_encryption_keys"):
        print("[ERROR] Use 'setup' to change the bot token, channel or encryption.")
        return 1
    kind, raw = types[args.key], args.value.strip()
    try:
        if kind in (bool, "bool"):
            if raw.lower() not in ("true", "false", "yes", "no", "on", "off", "1", "0"):
                raise ValueError("expected true or false")
            value = raw.lower() in ("true", "yes", "on", "1")
        elif kind in (int, "int"):
            # sizes accept units: 500M, 2G, 1.5T ...
            value = parse_size(raw) if args.key.endswith("_bytes") or args.key == "max_file_size" else int(raw)
        elif kind in (float, "float"):
            value = float(raw)
        else:
            value = raw
    except ValueError as e:
        print(f"[ERROR] Invalid value for {args.key}: {e}")
        return 1
    if args.key == "cache_mode" and value not in ("disk", "memory"):
        print("[ERROR] cache_mode must be 'disk' or 'memory'.")
        return 1
    if args.key == "mount_point":
        value = normalize_mount_point(value)
    setattr(cfg, args.key, value)
    cfg.save()
    shown = f"{value} ({format_size(value)})" if isinstance(value, int) and value >= 2**10 and (
        args.key.endswith("_bytes") or args.key == "max_file_size") else value
    print(f"[OK] {args.key} = {shown}  (restart the drive for it to take effect)")
    return 0


def cmd_verify(args):
    """Download and decrypt every chunk of the files under a path, without caching, and report failures."""
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    setup_logging(args.verbose, log_to_file=False)
    cfg = Config.load()
    if not cfg.is_configured():
        print("[ERROR] DiscordDrive is not configured.")
        return 1
    idx, j, crypto = _open_journal(cfg)
    try:
        vpath = normalize_virtual_path(args.path or "/", cfg.mount_point)
        node = idx.resolve(vpath)
        if node is None:
            print(f"[ERROR] Not found in DiscordDrive: {args.path}")
            return 1
        files, todo = [], [node]
        while todo:
            n = todo.pop()
            if n["is_dir"]:
                todo.extend(idx.children(n["id"]))
            elif n["state"] == "synced":
                files.append((idx.path_of(n["id"]), idx.get_chunks(n["id"]), n["id"]))
        files.sort()
        total = sum(c["size"] for _, chunks, _ in files for c in chunks)
        print(f"Checking {len(files)} file(s), {total / 2**20:.1f} MiB under {vpath} (downloads everything once)...")

        def check(chunk):
            try:
                data, _ = j.backend.download(chunk["message_id"], chunk.get("url"))
                if data.startswith(b"DENC"):
                    if not crypto:
                        return "encrypted, but encryption is off on this device"
                    data = crypto.decrypt(data)
                if chunk.get("sha256") and hashlib.sha256(data).hexdigest() != chunk["sha256"]:
                    return "checksum mismatch (damaged)"
                return None
            except AuthenticationError:
                return "cannot decrypt: encrypted with a different key, or damaged"
            except DiscordError as e:
                return "missing from Discord" if e.status == 404 else f"download failed ({e})"
            except Exception as e:
                return f"download failed ({e})"

        bad = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            unreadable = []
            for i, (path, chunks, nid) in enumerate(files, 1):
                problems = [p for p in pool.map(check, chunks) if p]
                if problems:
                    bad += 1
                    print(f"  [BAD] {path}: {problems[0]}")
                    if problems[0].startswith(("cannot decrypt", "missing from Discord", "checksum")):
                        unreadable.append((nid, path))
                elif args.verbose:
                    print(f"  [OK]  {path}")
                if i % 25 == 0:
                    print(f"  ... {i}/{len(files)} checked")
        if bad:
            print(f"\n{bad} of {len(files)} file(s) cannot be read. Older versions may still work: "
                  f"{launcher()} versions <path>")
            if unreadable and getattr(args, "remove", False):
                for nid, path in unreadable:
                    idx.purge_node(nid)
                print(f"[OK] Removed {len(unreadable)} unreadable file(s) from the drive (on every device).")
                print("     Copy them onto the drive again from their originals if you still have them.")
                return 0
            if unreadable:
                print(f"To remove the {len(unreadable)} file(s) that can never be read (e.g. encrypted with a lost key):")
                print(f"  {launcher()} verify {args.path} --remove")
            return 1
        print(f"\n[OK] All {len(files)} file(s) downloaded and decrypted correctly.")
        return 0
    finally:
        _close(idx, crypto)


def _log_message(line):
    """'12:00:00 [ERROR] discorddrive.cli: text' -> 'text'."""
    msg = line.split("] ", 1)[-1]
    name, sep, rest = msg.partition(": ")
    return rest if sep and name.startswith("discorddrive") else msg


def cmd_log(args):
    """Show the end of the log file (optionally only warnings and errors)."""
    path = os.path.join(default_data_dir(), "discorddrive.log")
    if not os.path.exists(path):
        print(f"No log yet ({path}).")
        return 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    if args.errors:
        lines = [l for l in lines if "[ERROR]" in l or "[WARNING]" in l]
        # The same problem is often logged many times in a row; show it once with a count.
        grouped = []
        for line in lines:
            key = line.split(" ", 1)[-1]                 # ignore the time
            if grouped and grouped[-1][0] == key:
                grouped[-1][2] += 1
            else:
                grouped.append([key, line, 1])
        lines = [line + (f"  (x{n})" if n > 1 else "") for _, line, n in grouped]
        if not lines:
            print("[OK] No recent problems.")
    for line in lines[-args.lines:]:
        print(line)
    if not args.errors:
        print(f"\n({path})")
    return 0


def cmd_add_old_key(args):
    """Add an earlier encryption key so data encrypted with it can still be read."""
    cfg = Config.load()
    candidates = []
    if args.from_config:
        import json
        try:
            with open(args.from_config, "r", encoding="utf-8") as f:
                other = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[ERROR] Could not read {args.from_config}: {e}")
            return 1
        candidates = [other.get("encryption_key", "")] + list(other.get("old_encryption_keys") or [])
    else:
        raw = args.key if args.key and args.key != "-" else sys.stdin.readline()
        candidates = [raw]
    added = 0
    for raw in candidates:
        if not (raw or "").strip():
            continue
        try:
            hex_key = parse_key(raw).hex()
        except ValueError as e:
            print(f"[ERROR] Not a valid key: {e}")
            return 1
        fp = key_fingerprint(hex_key)
        if hex_key == cfg.encryption_key or hex_key in cfg.old_encryption_keys:
            print(f"[OK] Key {fp} is already known.")
            continue
        cfg.old_encryption_keys.append(hex_key)
        added += 1
        print(f"[OK] Added older key {fp}; data encrypted with it can be read again.")
    if added:
        cfg.save()
        print("Restart the drive for this to take effect.")
    return 0


def cmd_cancel_uploads(args):
    """Cancel uploads that are stuck: a changed file goes back to its last uploaded version,
    a file that was never uploaded is removed. The drive has to be stopped."""
    setup_logging(args.verbose)
    cfg = Config.load()
    if is_mounted(cfg.mount_point):
        print("[ERROR] Stop the drive first (uploads run inside it), then try again.")
        return 1
    idx = Index(os.path.join(cfg.resolved_data_dir, "index.db"))
    try:
        pending = idx.unsynced_files()
        if not pending:
            print("[OK] Nothing is waiting to upload.")
            return 0
        for i, n in enumerate(pending, 1):
            print(f"  {i}) {idx.path_of(n['id'])}  ({_human(n['size'])})")
        if args.all:
            chosen = pending
        else:
            try:
                pick = input("\nCancel which? (a number, or 'all') [all]: ").strip().lower() or "all"
            except EOFError:
                pick = "all"
            if pick == "all":
                chosen = pending
            else:
                try:
                    chosen = [pending[int(pick) - 1]]
                except (ValueError, IndexError):
                    print("[!] Nothing cancelled.")
                    return 0
        staging = os.path.join(cfg.resolved_data_dir, "staging")
        for n in chosen:
            path = idx.path_of(n["id"])
            rec = idx.kv_get(f"upload:{n['id']}")
            if rec:
                try:
                    idx.trash_add([c["message_id"] for c in json.loads(rec).get("chunks") or []])
                except ValueError:
                    pass
                idx.kv_delete(f"upload:{n['id']}")
            chunks = idx.get_chunks(n["id"])
            if chunks:
                idx.update(n["id"], state="synced", size=sum(c["size"] for c in chunks))
                print(f"[OK] {path}: back to its last uploaded version.")
            else:
                idx.delete_node(n["id"])
                print(f"[OK] {path}: removed (it had never been uploaded).")
            try:
                os.remove(os.path.join(staging, f"{n['id']}.dat"))
            except OSError:
                pass
        return 0
    finally:
        idx.close()


_AUTOSTART_TAG = "# DiscordDrive autostart"


def autostart_enabled() -> bool:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, "DiscordDrive")
                return True
        except OSError:
            return False
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except OSError:
        return False
    return _AUTOSTART_TAG in out


def cmd_autostart(args):
    """Start the drive in the background automatically when this computer starts (on/off)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    action = args.action or "status"
    if action == "status":
        print(f"[OK] Autostart is {'ON' if autostart_enabled() else 'OFF'}.")
        return 0
    on = action == "on"
    if sys.platform == "win32":
        import winreg
        vbs = os.path.join(root, "discorddrive", "scripts", "windows", "mount_hidden.vbs")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            if on:
                winreg.SetValueEx(k, "DiscordDrive", 0, winreg.REG_SZ, f'wscript.exe "{vbs}"')
            else:
                try:
                    winreg.DeleteValue(k, "DiscordDrive")
                except OSError:
                    pass
    else:
        try:
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        except OSError:
            print("[ERROR] crontab is not available. Install it: sudo apt install -y cron")
            return 1
        lines = [l for l in current.splitlines() if _AUTOSTART_TAG not in l]
        if on:
            lines.append(f'@reboot sleep 20 && "{root}/run.sh" start >/dev/null 2>&1 {_AUTOSTART_TAG}')
        new = "\n".join(lines) + "\n" if lines else ""
        r = subprocess.run(["crontab", "-"], input=new, text=True, capture_output=True)
        if r.returncode != 0:
            print(f"[ERROR] Could not update crontab: {r.stderr.strip()}")
            return 1
    print(f"[OK] Autostart is now {'ON: the drive starts in the background when this computer starts' if on else 'OFF'}.")
    return 0


def cmd_export_key(args):
    """Print the encryption key so it can be copied to another device (setup -k <key>)."""
    cfg = Config.load()
    if not cfg.encryption_key:
        print("[ERROR] No encryption key is configured on this device.")
        return 1
    if sys.stdout.isatty():
        print("Your encryption key (keep it secret; anyone with it and your bot token can read your files):",
              file=sys.stderr)
    print(cfg.encryption_key)
    if sys.stdout.isatty():
        print(f"Fingerprint {key_fingerprint(cfg.encryption_key)}. On the other device run: "
              f"{launcher()} setup -k <key>", file=sys.stderr)
    return 0


def _human(n):
    """Readable size: 0 bytes, 512 KB, 94.3 MB, 129.9 GB (binary units)."""
    n = float(n or 0)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024


def _dir_size(path, suffix=None):
    total = 0
    try:
        with os.scandir(path) as it:
            for e in it:
                if e.is_file() and (suffix is None or e.name.endswith(suffix)):
                    try:
                        total += e.stat().st_size
                    except OSError:
                        pass
    except OSError:
        pass
    return total


def cmd_status(args):
    import shutil
    setup_logging(args.verbose)
    cfg = Config.load()
    data_dir = cfg.resolved_data_dir
    w = 20

    def row(label, value):
        print(f"{label + ':':{w}}{value}")

    if not embedded():
        print("=" * 60)
        print("DiscordDrive Status".center(60))
        print("=" * 60)

    # --- overview -------------------------------------------------------
    if not cfg.is_configured():
        row("Setup", f"NOT CONFIGURED - run '{launcher()} setup'")
    mounted = is_mounted(cfg.mount_point)
    row("Drive", f"{cfg.mount_point}  " + ("RUNNING (mounted)" if mounted else "not running"))

    if cfg.encryption_enabled and cfg.encryption_key:
        try:
            enc = f"ON (AES-256-GCM) | key fingerprint {key_fingerprint(cfg.encryption_key)}"
            if cfg.old_encryption_keys:
                enc += f" + {len(cfg.old_encryption_keys)} older key(s): " + ", ".join(
                    key_fingerprint(k) for k in cfg.old_encryption_keys)
        except ValueError:
            enc = "ON, but the configured key is INVALID (run setup again)"
    elif cfg.encryption_enabled:
        enc = f"ON (no key yet: one is generated on first start, or run '{launcher()} setup')"
    else:
        enc = "OFF - files are uploaded unencrypted"
    row("Encryption", enc)

    if cfg.is_configured():
        api = DiscordAPI(cfg.bot_token, timeout=20, retries=2)
        try:
            bot = api.get_me()
            ch = api.get_channel(cfg.channel_id)
            row("Discord", f"connected as {bot.get('username')}, channel #{ch.get('name')}")
        except Exception as e:
            row("Discord", f"NOT REACHABLE ({e})")

    # --- index ----------------------------------------------------------
    db_path = os.path.join(data_dir, "index.db")
    stats, idx = None, None
    if os.path.exists(db_path):
        try:
            idx = Index(db_path)
            stats = idx.stats(max_age=0)
        except Exception as e:
            print(f"\nCould not read the file list: {e}")

    if stats:
        print("\n--- Your files (stored in Discord) ---")
        row("Files", f"{stats['files']:,} in {stats['dirs']:,} folders")
        row("Total size", _human(stats["bytes"]))
        if cfg.keep_versions:
            row("Old versions", f"{stats['versions']:,} ({_human(stats['version_bytes'])}), "
                                f"kept {cfg.version_retention_days:g} days" if cfg.version_retention_days
                                else f"{stats['versions']:,} ({_human(stats['version_bytes'])}), kept forever")
        else:
            row("Old versions", "off")
        if stats["trash"]:
            row("Being deleted", f"{stats['trash']:,} old pieces, removed from Discord in the background")

        print("\n--- Syncing ---")
        row("Waiting to upload", f"{stats['unsynced']:,} file(s)")
        for key in idx.kv_keys("upload:"):
            try:
                rec = json.loads(idx.kv_get(key) or "null") or {}
                nid, size, cs = int(key.split(":", 1)[1]), int(rec["size"]), int(rec["chunk_size"])
            except (ValueError, KeyError, TypeError):
                continue
            total = max(1, (size + cs - 1) // cs)
            done = len(rec.get("chunks") or [])
            row("  Uploading now", f"{idx.path_of(nid)}  {done * 100 // total}% "
                                   f"({done} of {total} pieces, {_human(size)})")
        row("Changes to share", f"{stats['outbox']:,} (new/changed/deleted items not yet sent to other devices)")
        cursor = idx.kv_get("journal_cursor")
        row("Sync position", f"message {cursor}" if cursor else "not started (start the drive once)")
        row("This device", cfg.device_id or "(gets an ID on first start)")

    # --- local ----------------------------------------------------------
    print("\n--- On this computer ---")
    if (cfg.cache_mode or "disk").lower() == "memory":
        row("Read cache", f"memory only (up to {_human(cfg.memory_cache_bytes)} RAM), nothing stored on disk")
    else:
        used = _dir_size(os.path.join(data_dir, "cache"), ".chunk")
        row("Read cache", f"{_human(used)} used of {_human(cfg.cache_max_bytes)} (recently opened files)")
    if stats:
        row("Offline files", f"{stats.get('pinned_files', 0):,} ({_human(stats.get('pinned_bytes', 0))}) "
                             f"kept for offline use" if stats.get("pinned_files") else "none")
    queue = _dir_size(os.path.join(data_dir, "staging"), ".dat")
    row("Upload queue", f"{_human(queue)} waiting to upload (limit {_human(cfg.staging_max_bytes)})"
        if cfg.staging_max_bytes else f"{_human(queue)} waiting to upload")
    try:
        free = shutil.disk_usage(data_dir if os.path.isdir(data_dir) else os.path.expanduser("~")).free
        reserve = f" (DiscordDrive always leaves {_human(cfg.min_free_disk_bytes)} free)" if cfg.min_free_disk_bytes else ""
        row("Free disk space", _human(free) + reserve)
    except OSError:
        pass
    if cfg.max_file_size:
        row("Max file size", _human(cfg.max_file_size))
    if sys.platform == "win32":
        dll = find_winfsp_dll()
        row("Drive software", "WinFsp installed" if dll else "WinFsp NOT FOUND - install it from https://winfsp.dev/rel/")
    else:
        lib = find_linux_fuse_lib()
        row("Drive software", f"libfuse ({lib})" if lib else "libfuse NOT FOUND - ./run.sh -> Tools -> Install requirements")
    row("Settings file", config_path())
    row("Data folder", data_dir)
    if not embedded():
        print("=" * 60)
    if idx is not None:
        idx.close()
    return 0


def cmd_mount(args):
    setup_logging(args.verbose)
    if FUSE_ERROR:
        print(f"\n[ERROR] FUSE driver is not ready:\n{FUSE_ERROR}\n")
        return 1

    cfg = Config.load()
    if not cfg.is_configured() and not args.mock:
        print(f"[ERROR] DiscordDrive is not configured. Run '{launcher()} setup' first.")
        return 1

    mount_point = normalize_mount_point(args.mount or cfg.mount_point)

    if is_mounted(mount_point):
        print(f"[INFO] DiscordDrive is already mounted and active on {mount_point}!")
        return 0

    if args.background:
        print(f"Starting DiscordDrive in background on {mount_point}...")
        python_exe = sys.executable
        if sys.platform == "win32":
            pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
            python_exe = pythonw_exe if os.path.exists(pythonw_exe) else python_exe
        # Global flags (-v) must come before the subcommand.
        sub_args = [python_exe, "-m", "discorddrive"]
        if args.verbose:
            sub_args.append("-v")
        sub_args += ["mount", "-m", mount_point]
        if getattr(args, "allow_other", False):
            sub_args.append("--allow-other")
        if getattr(args, "cache", None):
            sub_args += ["--cache", args.cache]
        # Remember where the logs end, to show only what the new process writes.
        main_log = os.path.join(default_data_dir(), "discorddrive.log")
        mount_log = os.path.join(cfg.resolved_data_dir, "mount.log")
        log_starts = {p: (os.path.getsize(p) if os.path.exists(p) else 0) for p in (main_log, mount_log)}
        if sys.platform == "win32":
            proc = subprocess.Popen(
                sub_args,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
                close_fds=True,
            )
        else:
            os.makedirs(cfg.resolved_data_dir, exist_ok=True)
            with open(mount_log, "a") as log_f:
                proc = subprocess.Popen(
                    sub_args,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                )
        # The first start on a device can take a while (it downloads the index).
        deadline = time.time() + 60
        while time.time() < deadline and not is_mounted(mount_point) and proc.poll() is None:
            time.sleep(0.5)
        if is_mounted(mount_point):
            print(f"[SUCCESS] Drive {mount_point} mounted in background.")
            return 0
        if proc.poll() is not None:
            print("[ERROR] DiscordDrive stopped while starting:")
            shown = set()
            for path, start in log_starts.items():
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(start)
                        new = f.read()
                except OSError:
                    continue
                for line in new.splitlines():
                    msg = _log_message(line) if "[ERROR]" in line or "[WARNING]" in line else None
                    if msg is None and line.startswith("[ERROR]"):
                        msg = line
                    if msg and msg not in shown:
                        shown.add(msg)
                        print("  " + msg)
            if not shown:
                print(f"  (no details; see {main_log})")
            return 1
        print("DiscordDrive is still starting up. Check progress with the 'status' command or the log file:")
        print(f"  {main_log}")
        return 0

    if getattr(args, "allow_other", False):
        cfg.allow_other = True
    if getattr(args, "cache", None):
        cfg.cache_mode = args.cache

    drive = DiscordDrive(cfg, local_test_dir=args.mock)
    print("=" * 60)
    print(f"Starting DiscordDrive on {mount_point}...")
    if cfg.encryption_enabled:
        print("Zero-Knowledge Encryption: AES-256-GCM (Discord sees no file names or contents)")
    print("Press Ctrl+C to unmount and exit cleanly.")
    print("=" * 60)
    try:
        drive.mount(mount_point=mount_point, foreground=True)
    except (RuntimeError, ValueError) as e:
        log.error("%s", e)
        print(f"\n[ERROR] {e}")
        return 1
    return 0


def cmd_stop(args):
    """Stops the running DiscordDrive background daemon and unmounts the virtual drive."""
    import signal
    setup_logging(args.verbose)
    cfg = Config.load()
    pid_file = os.path.join(cfg.resolved_data_dir, "discorddrive.pid")
    stopped = False

    if sys.platform == "win32":
        # 1. Try stopping via PID file
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                res = subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True)
                if res.returncode == 0:
                    stopped = True
                try:
                    os.remove(pid_file)
                except OSError:
                    pass
            except Exception as e:
                log.debug("Could not stop via PID file: %s", e)

        # 2. Also search for any running python processes with discorddrive mount
        ps_cmd = (
            'Get-CimInstance Win32_Process | '
            f'Where-Object {{ $_.CommandLine -like "*discorddrive*mount*" -and $_.ProcessId -ne {os.getpid()} -and $_.ProcessId -ne $PID }} | '
            'ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output $_.ProcessId }'
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        if res.stdout.strip():
            stopped = True
        mp = cfg.mount_point.rstrip(":\\")
    else:
        mp = cfg.mount_point
        pid = None
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
            except (OSError, ValueError):
                pid = None
        # Unmounting makes the FUSE loop return so the daemon shuts down cleanly
        # (flushing uploads and backing up the index).
        unmount(mp)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                stopped = True
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
        res = subprocess.run(["pkill", "-TERM", "-f", "discorddrive (-v |--verbose )?mount"], capture_output=True)
        if res.returncode == 0:
            stopped = True
        # Give the daemon time to finish its final index backup.
        for _ in range(30):
            alive = subprocess.run(["pgrep", "-f", "discorddrive (-v |--verbose )?mount"], capture_output=True).returncode == 0
            if not alive:
                break
            time.sleep(0.5)
        if os.path.ismount(mp):
            unmount(mp, lazy=True)
        try:
            os.remove(pid_file)
        except OSError:
            pass
        is_mounted_now = os.path.ismount(mp)

    if sys.platform == "win32":
        time.sleep(1.5)
        is_mounted_now = os.path.exists(f"{mp}:\\")

    if stopped:
        print(f"[SUCCESS] DiscordDrive daemon stopped. Drive {mp} unmounted.")
    elif not is_mounted_now:
        print("[INFO] DiscordDrive is not currently running.")
    else:
        print("[WARNING] Could not find running DiscordDrive process to terminate.")
    return 0


def _open_journal(cfg):
    """(index, journal, crypto) for CLI commands that talk to the channel."""
    db_path = os.path.join(cfg.resolved_data_dir, "index.db")
    crypto = get_crypto_from_cfg(cfg)
    backend = DiscordBackend(DiscordAPI(cfg.bot_token, timeout=60, retries=3), cfg.channel_id, crypto=crypto)
    idx = Index(db_path)
    idx.keep_versions = bool(cfg.keep_versions)
    j = Journal(cfg, idx, backend, crypto=crypto, staging_dir=os.path.join(cfg.resolved_data_dir, "staging"))
    if not cfg.device_id:
        j.device = "cli"
    return idx, j, crypto


def _close(idx, crypto):
    idx.close()
    if crypto:
        crypto.close()


def _fmt_time(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t)) if t else "-"


def _fmt_size(n):
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def cmd_backup(args):
    setup_logging(args.verbose)
    cfg = Config.load()
    if not cfg.is_configured():
        print("[ERROR] DiscordDrive is not configured.")
        return 1
    if not os.path.exists(os.path.join(cfg.resolved_data_dir, "index.db")):
        print("[ERROR] No local index database found.")
        return 1
    idx, j, crypto = _open_journal(cfg)
    try:
        if not idx.kv_get("journal_cursor"):
            print("[ERROR] This index has not been synced yet. Mount the drive once first.")
            return 1
        if idx.outbox_count():
            print("[ERROR] There are local changes that have not been published yet. "
                  "Mount the drive (or wait for it to sync) and try again.")
            return 1
        print("Uploading index checkpoint to Discord...")
        j.poll()
        j.checkpoint(force=True)
        print(f"[SUCCESS] Checkpoint saved (message {idx.kv_get('last_backup_mid')}).")
        return 0
    finally:
        _close(idx, crypto)


def cmd_restore(args):
    setup_logging(args.verbose)
    cfg = Config.load()
    if not cfg.is_configured():
        print("[ERROR] DiscordDrive is not configured.")
        return 1
    if is_mounted(cfg.mount_point) and not getattr(args, "force", False):
        print(f"[ERROR] The drive is currently mounted on {cfg.mount_point}. Stop it first "
              "(restoring underneath a running drive can corrupt its index), or pass --force.")
        return 1

    print("Searching Discord channel for the newest index checkpoint...")
    idx, j, crypto = _open_journal(cfg)
    try:
        latest = j.backend.find_latest_index()
        if latest is None:
            print("[FAIL] No index checkpoint found in the Discord channel.")
            return 1
        j.restore(latest)
        if latest.get("cursor"):
            n = j.poll()
            print(f"Replayed changes made after the checkpoint ({n} updated).")
        else:
            idx.kv_set("journal_cursor", "")
            print("Restored a backup from an older version; the journal starts on the next mount.")
        stats = idx.stats(max_age=0)
        print(f"[SUCCESS] Restored {stats['files']} files and {stats['dirs']} folders from Discord.")
        return 0
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return 1
    finally:
        _close(idx, crypto)


def _resolve_file(idx, cfg, path):
    vpath = normalize_virtual_path(path, cfg.mount_point)
    node = idx.resolve(vpath)
    if node is None:
        print(f"[ERROR] Not found in DiscordDrive: {path}")
    elif node["is_dir"]:
        print(f"[ERROR] {path} is a folder; versions are kept per file.")
        node = None
    return vpath, node


def _put_op_for_version(idx, v, uid, parent_uid, name):
    chunks = idx.version_chunks(v["id"])
    return {"t": "put", "u": uid, "p": parent_uid, "n": name, "s": v["size"],
            "m": v["mtime"] or time.time(),
            "c": [[c["message_id"], c["size"], c["sha256"]] for c in chunks],
            "r": 1}   # an explicit restore: allowed even though the file was deleted


def _publish(j, ops, what):
    j.post_ops(ops)
    print(f"[SUCCESS] {what}")
    print("It appears on every running device within a few seconds (others pick it up when they start).")


def cmd_versions(args):
    setup_logging(args.verbose, log_to_file=False)
    cfg = Config.load()
    idx = Index(os.path.join(cfg.resolved_data_dir, "index.db"))
    try:
        vpath, node = _resolve_file(idx, cfg, args.path)
        if node is None:
            return 1
        rows = idx.versions_for(node["uid"])
        print(f"{vpath}")
        print(f"  current  {_fmt_time(node['mtime'])}  {_fmt_size(node['size']):>10}")
        if not rows:
            print("  (no older versions)")
        labels = {"replaced": "replaced", "deleted": "deleted", "conflict": "conflicting edit"}
        for i, v in enumerate(rows, 1):
            print(f"  {i:>7}  {_fmt_time(v['superseded'])}  {_fmt_size(v['size']):>10}  "
                  f"{labels.get(v['reason'], v['reason'])}")
        if rows:
            print(f"\nRestore one with: {launcher()} restore-version <path> <number> [--as <new path>]")
        return 0
    finally:
        idx.close()


def cmd_restore_version(args):
    setup_logging(args.verbose)
    cfg = Config.load()
    idx, j, crypto = _open_journal(cfg)
    try:
        vpath, node = _resolve_file(idx, cfg, args.path)
        if node is None:
            return 1
        rows = idx.versions_for(node["uid"])
        if not 1 <= args.number <= len(rows):
            print(f"[ERROR] {vpath} has {len(rows)} version(s); pick a number from '{launcher()} versions'.")
            return 1
        v = rows[args.number - 1]
        if args.as_path:
            target = normalize_virtual_path(args.as_path, cfg.mount_point)
            parent_path, name = target.rsplit("/", 1)
            parent = idx.resolve(parent_path or "/")
            if parent is None or not parent["is_dir"] or not name:
                print(f"[ERROR] Folder not found: {parent_path or '/'}")
                return 1
            from .index import new_uid
            op = _put_op_for_version(idx, v, new_uid(), parent["uid"], name)
            what = f"Version {args.number} of {vpath} restored as {target}."
        else:
            parent_uid = idx.get(node["parent"])["uid"]
            op = _put_op_for_version(idx, v, node["uid"], parent_uid, node["name"])
            what = f"{vpath} restored to version {args.number} (the current content is kept as a version)."
        _publish(j, [op], what)
        return 0
    finally:
        _close(idx, crypto)


def cmd_deleted(args):
    setup_logging(args.verbose, log_to_file=False)
    cfg = Config.load()
    idx = Index(os.path.join(cfg.resolved_data_dir, "index.db"))
    try:
        prefix = normalize_virtual_path(args.path or "/", cfg.mount_point)
        rows = idx.deleted_files(prefix)
        if not rows:
            print("No deleted files are being kept" + (f" under {prefix}." if prefix != "/" else "."))
            return 0
        for v in rows:
            print(f"{_fmt_time(v['superseded'])}  {_fmt_size(v['size']):>10}  {v['path']}")
        print(f"\nRecover one with: {launcher()} undelete <path>")
        return 0
    finally:
        idx.close()


def cmd_undelete(args):
    setup_logging(args.verbose)
    cfg = Config.load()
    idx, j, crypto = _open_journal(cfg)
    try:
        vpath = normalize_virtual_path(args.path, cfg.mount_point)
        matches = [v for v in idx.deleted_files(vpath) if (v["path"] or "").lower() == vpath.lower()]
        if not matches:
            print(f"[ERROR] No deleted file kept at {vpath}. See '{launcher()} deleted'.")
            return 1
        v = matches[0]
        op = _put_op_for_version(idx, v, v["uid"], v["parent_uid"], v["name"])
        _publish(j, [op], f"{vpath} recovered (into 'Recovered files' if its folder no longer exists).")
        return 0
    finally:
        _close(idx, crypto)


def cmd_offline(args):
    """Marks a file or folder as available offline and prefetches all chunks."""
    setup_logging(args.verbose)
    cfg = Config.load()
    if not cfg.is_configured():
        print("[ERROR] DiscordDrive is not configured.")
        return 1

    vpath = normalize_virtual_path(args.path, cfg.mount_point)
    db_path = os.path.join(cfg.resolved_data_dir, "index.db")
    cache_dir = os.path.join(cfg.resolved_data_dir, "cache")

    idx = Index(db_path)
    node = idx.resolve(vpath)
    if not node:
        print(f"[ERROR] Path not found in DiscordDrive: {args.path}")
        idx.close()
        return 1

    print(f"Saving '{vpath}' for offline usage...")
    idx.set_pinned(node["id"], pinned=True, recursive=True)

    crypto = get_crypto_from_cfg(cfg)
    api = DiscordAPI(cfg.bot_token)
    backend = DiscordBackend(api, cfg.channel_id, crypto=crypto)
    cache = ChunkCache(cache_dir, max_bytes=cfg.cache_max_bytes, backend=backend, index=idx, crypto=crypto)

    try:
        count = cache.prefetch_node(node["id"])
        print(f"[SUCCESS] '{vpath}' is now pinned and saved offline! ({count} chunk(s) cached)")
    finally:
        cache.shutdown()
        idx.close()
        if crypto:
            crypto.close()
    return 0


def cmd_free_space(args):
    """Evicts cached chunks from local disk to free up space."""
    setup_logging(args.verbose)
    cfg = Config.load()
    db_path = os.path.join(cfg.resolved_data_dir, "index.db")
    cache_dir = os.path.join(cfg.resolved_data_dir, "cache")

    idx = Index(db_path)
    crypto = get_crypto_from_cfg(cfg)
    api = DiscordAPI(cfg.bot_token) if cfg.is_configured() else None
    backend = DiscordBackend(api, cfg.channel_id, crypto=crypto) if api else None
    cache = ChunkCache(cache_dir, max_bytes=cfg.cache_max_bytes, backend=backend, index=idx, crypto=crypto)

    try:
        if args.all or not args.path:
            print("Freeing up local cache across all files...")
            freed = cache.free_space(node_id=None, force=args.force)
            print(f"[SUCCESS] Freed {freed / (1024 * 1024):.2f} MiB ({freed} bytes) of local cache!")
        else:
            vpath = normalize_virtual_path(args.path, cfg.mount_point)
            node = idx.resolve(vpath)
            if not node:
                print(f"[ERROR] Path not found in DiscordDrive: {args.path}")
                return 1

            idx.set_pinned(node["id"], pinned=False, recursive=True)
            freed = cache.free_space(node_id=node["id"], force=True)
            print(f"[SUCCESS] Freed {freed / (1024 * 1024):.2f} MiB for '{vpath}'. File is now online-only!")
    finally:
        cache.shutdown()
        idx.close()
        if crypto:
            crypto.close()
    return 0


def cmd_clear_cache(args):
    """Convenience command for clearing all locally cached chunks across the drive."""
    args.all = True
    args.path = ""
    return cmd_free_space(args)


def cmd_context_menu(args):
    """Installs or uninstalls Windows Explorer right-click context menu entries."""
    if sys.platform != "win32":
        print("[ERROR] The context menu integration is only available on Windows.")
        return 1
    import winreg

    launch = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts", "windows", "launch.cmd")

    reg_entries = [
        (
            r"Software\Classes\*\shell\DiscordDrive_Offline",
            "DiscordDrive: Make available offline",
            f'"{launch}" offline "%1"',
        ),
        (
            r"Software\Classes\*\shell\DiscordDrive_FreeSpace",
            "DiscordDrive: Free up space",
            f'"{launch}" free-space "%1"',
        ),
        (
            r"Software\Classes\Directory\shell\DiscordDrive_Offline",
            "DiscordDrive: Make available offline",
            f'"{launch}" offline "%1"',
        ),
        (
            r"Software\Classes\Directory\shell\DiscordDrive_FreeSpace",
            "DiscordDrive: Free up space",
            f'"{launch}" free-space "%1"',
        ),
    ]

    if args.action == "uninstall":
        for subkey, _, _ in reg_entries:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey + r"\command")
            except OSError:
                pass
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
            except OSError:
                pass
        print("[SUCCESS] Windows Explorer context menu entries removed.")
        return 0

    # Install into HKCU (no admin privileges required)
    for subkey, title, cmd_str in reg_entries:
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, title)
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, "shell32.dll,275")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey + r"\command") as ck:
                winreg.SetValueEx(ck, "", 0, winreg.REG_SZ, cmd_str)
        except Exception as e:
            print(f"[FAIL] Could not register {subkey}: {e}")
            return 1

    print("[SUCCESS] Windows Explorer context menu installed!")
    print("You can now right-click any file or folder in Windows Explorer to:")
    print("  - 'DiscordDrive: Make available offline'")
    print("  - 'DiscordDrive: Free up space'")
    return 0


def main():
    theme_output()   # the same colours and style for every command (menu pages or direct)
    parser = argparse.ArgumentParser(
        prog="discorddrive",
        description="DiscordDrive: an encrypted virtual drive (Windows/Linux) backed by a private Discord channel.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    subparsers = parser.add_subparsers(dest="command")

    # mount
    p_mount = subparsers.add_parser("mount", help="Mount the virtual drive")
    p_mount.add_argument("-m", "--mount", help="Mount point or drive letter")
    p_mount.add_argument("-b", "--background", action="store_true", help="Run in background")
    p_mount.add_argument("--allow-other", action="store_true", help="Allow other users/processes to access mount")
    p_mount.add_argument("--mock", help="Test mode using local directory instead of Discord")
    p_mount.add_argument("--cache", choices=["disk", "memory"],
                         help="Where viewed files are cached: disk (default) or memory (nothing stored on disk)")

    # setup
    p_setup = subparsers.add_parser("setup", help="Configure Discord bot token and channel ID")
    p_setup.add_argument("-t", "--token", help="Discord bot token")
    p_setup.add_argument("-c", "--channel", help="Discord channel ID")
    p_setup.add_argument("-m", "--mount", help="Drive letter (e.g. Z:)")
    p_setup.add_argument("-p", "--passphrase", help="Encryption password for zero-knowledge encryption")
    p_setup.add_argument("-k", "--key", help="Raw 256-bit encryption key (hex)")

    # status
    subparsers.add_parser("status", help="Show current status and sync statistics")
    subparsers.add_parser("mountpoint", help="Print the configured mount point (for scripts)")
    subparsers.add_parser("menu", help="Open the interactive menu (what run.bat / run.sh show)")
    subparsers.add_parser("start", help="Start the drive in the background")
    subparsers.add_parser("menu-start", help=argparse.SUPPRESS)
    subparsers.add_parser("export-key", help="Show the encryption key, to copy it to another device")
    subparsers.add_parser("approve-keys", help="Send the key to a new device that asked for it")
    p_auto = subparsers.add_parser("autostart", help="Start the drive automatically at startup: on, off or status")
    p_auto.add_argument("action", nargs="?", choices=["on", "off", "status"])
    subparsers.add_parser("request-key", help="Ask one of your other devices for the key")
    p_old = subparsers.add_parser("add-old-key", help="Add an earlier encryption key, to read data encrypted with it")
    p_old.add_argument("key", nargs="?", default="-", help="The key in hex, or - to read it from input (default)")
    p_old.add_argument("--from-config", help="Take the key(s) from another device's config.json")
    p_verify = subparsers.add_parser("verify", help="Check that files can be downloaded and decrypted")
    p_verify.add_argument("path", nargs="?", default="/", help="File or folder to check (default: everything)")
    p_verify.add_argument("--remove", action="store_true",
                          help="Remove files that can never be read (lost key, missing from Discord)")
    p_cancel = subparsers.add_parser("cancel-uploads", help="Cancel uploads that are stuck (drive must be stopped)")
    p_cancel.add_argument("--all", action="store_true", help="Cancel every pending upload without asking")
    p_log = subparsers.add_parser("log", help="Show the end of the log file")
    p_log.add_argument("-n", "--lines", type=int, default=30, help="Number of lines (default 30)")
    p_log.add_argument("--errors", action="store_true", help="Only warnings and errors")
    p_config = subparsers.add_parser("config", help="Show or change a setting (e.g. config cache_mode memory)")
    p_config.add_argument("key", nargs="?", help="Setting name")
    p_config.add_argument("value", nargs="?", help="New value")

    # stop
    subparsers.add_parser("stop", help="Stop the background DiscordDrive daemon and unmount")

    # clear-cache
    p_clear = subparsers.add_parser("clear-cache", aliases=["clearcache"], help="Clear all locally cached chunks")
    p_clear.add_argument("--force", action="store_true", help="Force evict even pinned offline files")

    # backup / restore
    subparsers.add_parser("backup", help="Manually upload index backup to Discord")
    p_restore = subparsers.add_parser("restore", help="Restore local index from Discord backup (drive must be stopped)")
    p_restore.add_argument("--force", action="store_true", help="Restore even if the drive appears to be mounted")

    # versions
    p_versions = subparsers.add_parser("versions", help="List the older versions kept for a file")
    p_versions.add_argument("path", help="File path (e.g. Z:\\Docs\\report.docx or /Docs/report.docx)")
    p_rv = subparsers.add_parser("restore-version", help="Bring back an older version of a file")
    p_rv.add_argument("path", help="File path")
    p_rv.add_argument("number", type=int, help="Version number from 'versions'")
    p_rv.add_argument("--as", dest="as_path", help="Restore as a new file instead of replacing the current one")
    p_deleted = subparsers.add_parser("deleted", help="List deleted files that can still be recovered")
    p_deleted.add_argument("path", nargs="?", default="/", help="Only show files under this folder")
    p_undelete = subparsers.add_parser("undelete", help="Recover a deleted file")
    p_undelete.add_argument("path", help="Original path of the deleted file")

    # offline / free-space
    p_offline = subparsers.add_parser("offline", aliases=["pin"], help="Save a file or folder for offline use")
    p_offline.add_argument("path", help="Path of the file or folder (e.g. Z:\\MyFolder or /MyFolder)")

    p_free = subparsers.add_parser("free-space", aliases=["unpin"], help="Free up local space by evicting cached chunks")
    p_free.add_argument("path", nargs="?", default="", help="Path of file or folder to free up")
    p_free.add_argument("--all", action="store_true", help="Free up all cached space across the drive")
    p_free.add_argument("--force", action="store_true", help="Force evict even pinned offline files")

    # context-menu
    p_menu = subparsers.add_parser("context-menu", help="Install Windows Explorer right-click menu")
    p_menu.add_argument("action", choices=["install", "uninstall"], default="install", nargs="?")

    args = parser.parse_args()

    if args.command == "mount":
        return cmd_mount(args)
    elif args.command == "stop":
        return cmd_stop(args)
    elif args.command in ("clear-cache", "clearcache"):
        return cmd_clear_cache(args)
    elif args.command == "setup":
        return cmd_setup(args)
    elif args.command == "config":
        return cmd_config(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "log":
        return cmd_log(args)
    elif args.command == "add-old-key":
        return cmd_add_old_key(args)
    elif args.command == "cancel-uploads":
        return cmd_cancel_uploads(args)
    elif args.command == "autostart":
        return cmd_autostart(args)
    elif args.command == "approve-keys":
        return cmd_approve_keys(args)
    elif args.command == "request-key":
        return cmd_request_key(args)
    elif args.command == "export-key":
        return cmd_export_key(args)
    elif args.command == "menu":
        from .menu import main as menu_main
        try:
            return menu_main()
        except KeyboardInterrupt:
            print()
            return 0
    elif args.command in ("start", "menu-start"):
        from .menu import menu_start
        return menu_start()
    elif args.command == "mountpoint":
        print(Config.load().mount_point)
        return 0
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "backup":
        return cmd_backup(args)
    elif args.command == "restore":
        return cmd_restore(args)
    elif args.command == "versions":
        return cmd_versions(args)
    elif args.command == "restore-version":
        return cmd_restore_version(args)
    elif args.command == "deleted":
        return cmd_deleted(args)
    elif args.command == "undelete":
        return cmd_undelete(args)
    elif args.command in ("offline", "pin"):
        return cmd_offline(args)
    elif args.command in ("free-space", "unpin"):
        return cmd_free_space(args)
    elif args.command == "context-menu":
        return cmd_context_menu(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
