"""Interactive menu shown by run.bat / run.sh when they are started without arguments.

Every choice opens its own page: the screen is cleared, the XO banner and a breadcrumb are
shown, the action runs, and Enter goes back to the page it came from.
"""

import os
import shutil
import subprocess
import sys
import threading
import time

from .config import Config, default_data_dir, format_size
from .ui import ANSI, BOLD, GRAY, GREEN, RED, RESET, YELLOW, banner

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "discorddrive", "scripts")
WINDOWS = sys.platform == "win32"
RESTART = 75          # exit code asking run.bat / run.sh to reopen the menu (after an update)
MAIN = "Main menu"


# ------------------------------------------------------------------ output
def clear():
    sys.stdout.flush()
    os.system("cls" if WINDOWS else "clear")


def page(*crumbs):
    """Start a new page: clear the screen, banner, breadcrumb and title."""
    clear()
    banner()
    if len(crumbs) > 1:
        print(f"  {GRAY}{'  >  '.join(crumbs[:-1])}{RESET}")
    print(f"  {RED}==>{RESET} {BOLD}{crumbs[-1]}{RESET}")
    print()


def step(msg):
    print(f"  {RED}==>{RESET} {msg}")


def info(msg):
    print(f"    {GRAY}{msg}{RESET}")


def done(msg):
    print(f"    {GREEN}{msg}{RESET}")


def warn(msg):
    print(f"    {YELLOW}{msg}{RESET}")


def ask(prompt, default=""):
    try:
        value = input(f"  {prompt}" + (f" {GRAY}[{default}]{RESET}" if default else "") + ": ").strip()
    except EOFError:
        raise SystemExit(0)
    return value or default


def confirm(prompt, default=True):
    answer = ask(f"{prompt} {GRAY}{'[Y/n]' if default else '[y/N]'}{RESET}").lower()
    return default if not answer else answer.startswith("y")


def back(to=MAIN):
    try:
        input(f"\n  {GRAY}Press Enter to go back to {to}...{RESET}")
    except EOFError:
        raise SystemExit(0)


def choose(title, options, live=None):
    """Print a list of (key, label) options (None = spacer) and ask for one.
    Returns the chosen key, None for back/exit, or '?' for anything else.
    live: (render_function, lines_between_it_and_the_title) keeps a status line up to date."""
    print(f"  {BOLD}{title}{RESET}")
    for key, label in options:
        if key is None:
            print()
            continue
        print(f"   {RED}{key:>2}{RESET}  {label}")
    print(f"   {RED} 0{RESET}  {'Exit' if title == MAIN else 'Back'}")
    print()
    updater = None
    if live:
        render, offset = live
        # from the prompt line up to the live line: blank, exit, options, title, the lines
        # between title and live line (offset), and one more to land on the live line itself
        updater = LiveLine(render, 1 + 1 + len(options) + 1 + offset + 1).start()
    try:
        pick = ask("Choose an option")
    finally:
        if updater:
            updater.stop()
    if pick in ("0", "q", "exit", "back"):
        return None
    return pick if any(pick == k for k, _ in options if k) else "?"


class LiveLine:
    """Rewrites one line further up the screen every few seconds while the menu waits for input.

    Uses ANSI 'save cursor / move up / clear line / restore cursor', so whatever the user is
    typing at the prompt stays where it is. Only active in a real terminal with ANSI support.
    """

    def __init__(self, render, lines_up, interval=2.0):
        self.render = render
        self.lines_up = lines_up
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._last = None

    def start(self):
        if not ANSI or self.lines_up <= 0:
            return self
        size = shutil.get_terminal_size((0, 0))
        # Wrapped lines (narrow window) or a scrolled-off status line (short window) would make
        # the cursor land on the wrong line, so only update when everything fits.
        if size.columns < 90 or size.lines <= self.lines_up + 1:
            return self
        self._thread = threading.Thread(target=self._run, name="LiveStatus", daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                text = self.render()
            except Exception:
                continue
            if self._stop.is_set() or text == self._last:
                continue
            self._last = text
            sys.stdout.write(f"\0337\033[{self.lines_up}A\r\033[2K  {text}\0338")
            sys.stdout.flush()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


# ------------------------------------------------------------- the drive
def cli(*args, stdin_text=None):
    """Run a DiscordDrive command in a fresh process; its output appears on the current page,
    in the same theme (DISCORDDRIVE_EMBEDDED tells it the page already has a banner and title)."""
    cmd = [sys.executable, "-m", "discorddrive", *args]
    env = dict(os.environ, DISCORDDRIVE_EMBEDDED="1")
    sys.stdout.flush()   # the page header must appear before the command's own output
    if stdin_text is None:
        return subprocess.call(cmd, cwd=ROOT, env=env)
    return subprocess.run(cmd, cwd=ROOT, env=env, input=stdin_text, text=True).returncode


def is_mounted(cfg):
    from .cli import is_mounted as _m
    return _m(cfg.mount_point)


def _winfsp():
    from .fuse_loader import find_winfsp_dll
    return find_winfsp_dll()


def drive_line(cfg):
    """'Drive Z: RUNNING  |  4,372 files, 141.4 GB in Discord  |  3 uploading'"""
    running = is_mounted(cfg)
    state = f"{GREEN}RUNNING{RESET}" if running else f"{GRAY}not running{RESET}"
    parts = [f"Drive {BOLD}{cfg.mount_point}{RESET} {state}"]
    db = os.path.join(cfg.resolved_data_dir, "index.db")
    if os.path.exists(db):
        try:
            from .index import Index
            from .cli import _human
            idx = Index(db)
            try:
                st = idx.stats(max_age=0)
            finally:
                idx.close()
            parts.append(f"{st['files']:,} files, {_human(st['bytes'])} in Discord")
            if st["unsynced"]:
                parts.append(f"{YELLOW}{st['unsynced']:,} uploading{RESET}")
        except Exception:
            pass
    return "  |  ".join(parts)


def quick_status(cfg):
    """Print the status lines at the top of the main menu. Returns how many lines were printed
    after the drive line (so the live updater can find it again)."""
    if not cfg.is_configured():
        print(f"  {YELLOW}Not set up yet: choose {BOLD}5{RESET}{YELLOW} (Setup) first.{RESET}")
    print(f"  {drive_line(cfg)}")
    after = []
    if not WINDOWS:
        from .fuse_loader import find_linux_fuse_lib
        if not find_linux_fuse_lib():
            after.append(f"{YELLOW}FUSE is not installed: choose 9 (Tools), then 'Install requirements'.{RESET}")
    elif not _winfsp():
        after.append(f"{YELLOW}WinFsp is not installed: get it from https://winfsp.dev/rel/ "
                     f"(or: winget install -e --id WinFsp.WinFsp --source winget){RESET}")
    for line in after:
        print(f"  {line}")
    print()
    return len(after) + 1


def _log_path():
    return os.path.join(default_data_dir(), "discorddrive.log")


def _new_log_errors(since):
    try:
        with open(_log_path(), "r", encoding="utf-8", errors="replace") as f:
            f.seek(since)
            text = f.read()
    except OSError:
        return []
    from .cli import _log_message
    return [_log_message(l) for l in text.splitlines() if "[ERROR]" in l]


def start_drive():
    cfg = Config.load()
    if not cfg.is_configured():
        warn("DiscordDrive is not set up yet. Choose 5 (Setup) first.")
        return
    if is_mounted(cfg):
        done(f"Already running on {cfg.mount_point}.")
        return
    step(f"Starting DiscordDrive on {cfg.mount_point}")
    if not WINDOWS:
        cli("mount", "-b")
        return
    # Windows: start hidden (no console window stays open) through the VBScript helper.
    try:
        since = os.path.getsize(_log_path())
    except OSError:
        since = 0
    subprocess.Popen(["wscript.exe", os.path.join(SCRIPTS, "windows", "mount_hidden.vbs")])
    for _ in range(120):
        time.sleep(0.5)
        if is_mounted(cfg):
            done(f"Running. Open File Explorer: your drive is {cfg.mount_point}")
            return
        errors = _new_log_errors(since)
        if errors:
            print(f"    {RED}DiscordDrive stopped while starting:{RESET}")
            for e in dict.fromkeys(errors):
                print(f"      {e}")
            return
    warn("Still starting (the first start can take a minute). Check again with Status.")


def stop_drive():
    step("Stopping DiscordDrive")
    cli("stop")


def update():
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        warn("This copy wasn't downloaded with git, so it can't update itself.")
        info("Download the latest version from https://github.com/xo907/discord-drive")
        return False
    if not shutil.which("git"):
        warn("git is not installed." + (" Install it: winget install -e --id Git.Git --source winget"
                                         if WINDOWS else " Install it: sudo apt install -y git"))
        return False
    cfg = Config.load()
    was_running = is_mounted(cfg)
    if was_running:
        stop_drive()
        print()
    step("Downloading the latest version")
    result = subprocess.run(["git", "pull", "--ff-only"], cwd=ROOT, capture_output=True, text=True)
    for line in (result.stdout + result.stderr).strip().splitlines():
        info(line)
    ok = result.returncode == 0
    if not ok:
        warn("Could not update (see above). Your current version is unchanged.")
    if was_running:
        print()
        cli("menu-start")   # a fresh process, so the new code is used
    return ok


# --------------------------------------------------------- settings page
SETTINGS = [
    ("cache_mode", "Read cache", "disk = keep opened files on disk (faster), memory = RAM only (nothing on disk)"),
    ("cache_max_bytes", "Read cache size (disk mode)", "e.g. 5G"),
    ("min_free_disk_bytes", "Always keep this much disk free", "e.g. 2G (protects your other programs)"),
    ("staging_max_bytes", "Upload queue limit", "e.g. 2G (pause copying while this much waits to upload)"),
    ("max_file_size", "Max file size", "e.g. 100M, 2G, or 0 for no limit"),
    ("version_retention_days", "Keep old versions for (days)", "0 = forever"),
    ("mount_point", "Drive letter / mount folder", "e.g. Z: on Windows, /mnt/discord on Linux"),
]


def _shown(key, value):
    if isinstance(value, int) and not isinstance(value, bool) and (key.endswith("_bytes") or key == "max_file_size"):
        return "no limit" if value == 0 and key == "max_file_size" else format_size(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def settings_menu():
    while True:
        page(MAIN, "Settings")
        cfg = Config.load()
        options = [(str(i), f"{label}: {BOLD}{_shown(k, getattr(cfg, k))}{RESET}")
                   for i, (k, label, _) in enumerate(SETTINGS, 1)]
        from .cli import autostart_enabled
        auto = autostart_enabled()
        options += [(None, None),
                    ("9", f"Start automatically when this computer starts: {BOLD}{'ON' if auto else 'OFF'}{RESET}"),
                    ("8", "Show every setting")]
        pick = choose("Choose a setting to change", options)
        if pick is None:
            return
        if pick == "9":
            page(MAIN, "Settings", "Start automatically")
            cli("autostart", "off" if auto else "on")
            back("Settings")
            continue
        if pick == "8":
            page(MAIN, "Settings", "Every setting")
            cli("config")
            back("Settings")
            continue
        if not pick.isdigit() or not 1 <= int(pick) <= len(SETTINGS):
            continue
        key, label, hint = SETTINGS[int(pick) - 1]
        page(MAIN, "Settings", label)
        print(f"  Current value: {BOLD}{_shown(key, getattr(cfg, key))}{RESET}")
        info(hint)
        print()
        value = ask("New value (Enter = keep)", "")
        if value:
            print()
            if cli("config", key, value) == 0 and is_mounted(cfg):
                print()
                if confirm("Restart the drive now so this takes effect?"):
                    print()
                    stop_drive()
                    start_drive()
        back("Settings")


# ----------------------------------------------------------- files page
def files_menu():
    title = "Files: versions, recovery and offline"
    while True:
        page(MAIN, title)
        pick = choose("What would you like to do?", [
            ("1", "List the old versions of a file"),
            ("2", "Bring back an old version of a file"),
            ("3", "List deleted files that can be recovered"),
            ("4", "Recover a deleted file"),
            (None, None),
            ("5", "Make a file or folder available offline"),
            ("6", "Free up space used by a file or folder"),
            ("7", "Clear the whole read cache"),
        ])
        if pick is None:
            return
        if pick == "1":
            page(MAIN, title, "Old versions of a file")
            p = ask("File (e.g. Z:\\Docs\\a.docx or /Docs/a.docx)")
            if p:
                print()
                cli("versions", p)
        elif pick == "2":
            page(MAIN, title, "Bring back an old version")
            p = ask("File")
            if p:
                print()
                cli("versions", p)
                print()
                n = ask("Version number to bring back (Enter = cancel)")
                if n:
                    target = ask("Save as a new file instead? Enter a path, or leave empty to replace", "")
                    print()
                    cli("restore-version", p, n, *(["--as", target] if target else []))
        elif pick == "3":
            page(MAIN, title, "Deleted files")
            folder = ask("Only inside this folder (Enter = everywhere)", "/")
            print()
            cli("deleted", folder)
        elif pick == "4":
            page(MAIN, title, "Recover a deleted file")
            p = ask("Original path of the deleted file")
            if p:
                print()
                cli("undelete", p)
        elif pick == "5":
            page(MAIN, title, "Make available offline")
            p = ask("File or folder to keep on this computer")
            if p:
                print()
                cli("offline", p)
        elif pick == "6":
            page(MAIN, title, "Free up space")
            p = ask("File or folder (Enter = everything that isn't kept offline)", "")
            print()
            if p:
                cli("free-space", p)
            else:
                cli("free-space", "--all")
        elif pick == "7":
            page(MAIN, title, "Clear the read cache")
            cli("clear-cache")
        else:
            continue
        back(title)


# ----------------------------------------------------------- tools page
def tools_menu():
    title = "Tools and troubleshooting"
    while True:
        page(MAIN, title)
        options = [
            ("1", "Check that files can be downloaded and decrypted (verify)"),
            ("2", "Show recent problems"),
            ("3", "Show the log"),
            (None, None),
            ("4", "Show my encryption key (to set up another device)"),
            ("5", "Add an older encryption key"),
            ("6", "Rebuild this device's file list from Discord"),
            ("7", "Save an index checkpoint now"),
            ("10", "Request the key from another device"),
            ("11", "Cancel stuck uploads"),
            (None, None),
        ]
        if WINDOWS:
            options += [("8", "Add 'offline / free up space' to the Explorer right-click menu"),
                        ("9", "Remove it from the Explorer right-click menu")]
        else:
            options += [("8", "Install / repair requirements (FUSE, cryptography; needs root)"),
                        ("9", "How to start the drive automatically at boot")]
        pick = choose("What would you like to do?", options)
        if pick is None:
            return
        labels = {k: v for k, v in options if k}
        if pick not in labels:
            continue
        page(MAIN, title, labels[pick].split(" (")[0])
        if pick == "1":
            p = ask("File or folder to check (Enter = everything; downloads it all once)", "") or "/"
            print()
            if cli("verify", p) != 0:
                print()
                if confirm("Remove the files that can never be read (lost key / missing) from the drive?",
                           default=False):
                    print()
                    cli("verify", p, "--remove")
        elif pick == "2":
            cli("log", "--errors", "-n", "25")
        elif pick == "3":
            cli("log", "-n", "40")
        elif pick == "4":
            warn("Anyone with this key and your bot token can read your files. Don't share it publicly.")
            print()
            if confirm("Show it?", default=False):
                print()
                cli("export-key")
        elif pick == "5":
            info("Paste the key (64 hex characters), or the path of another device's config.json.")
            print()
            value = ask("Key or file")
            if value:
                print()
                if os.path.isfile(value):
                    cli("add-old-key", "--from-config", value)
                else:
                    cli("add-old-key", "-", stdin_text=value + "\n")
        elif pick == "6":
            info("Use this when this device is missing files that your other devices show.")
            print()
            cfg = Config.load()
            if is_mounted(cfg):
                if not confirm("The drive has to stop for this. Stop it now?"):
                    back(title)
                    continue
                print()
                stop_drive()
                print()
            cli("restore")
            print()
            if confirm("Start the drive again?"):
                print()
                start_drive()
        elif pick == "7":
            cli("backup")
        elif pick == "11":
            cfg = Config.load()
            running = is_mounted(cfg)
            if running:
                if not confirm("The drive has to stop for this. Stop it now?"):
                    back(title)
                    continue
                print()
                stop_drive()
                print()
            cli("cancel-uploads")
            if running:
                print()
                start_drive()
        elif pick == "10":
            info("For a device that is missing the key, or has the wrong one. Another device approves it")
            info("from its menu: 'Approve a new device'.")
            print()
            cli("request-key")
        elif pick == "8":
            if WINDOWS:
                cli("context-menu", "install")
            else:
                subprocess.call(["bash", os.path.join(SCRIPTS, "linux", "install.sh")], cwd=ROOT)
        elif pick == "9":
            if WINDOWS:
                cli("context-menu", "uninstall")
            else:
                service = os.path.join(SCRIPTS, "linux", "discorddrive.service")
                print("  Run these once, as the user that runs the drive:\n")
                print(f"    {BOLD}mkdir -p ~/.config/systemd/user{RESET}")
                print(f"    {BOLD}sed \"s|%h/DiscordDrive|{ROOT}|g\" {service} > "
                      f"~/.config/systemd/user/discorddrive.service{RESET}")
                print(f"    {BOLD}systemctl --user daemon-reload && systemctl --user enable --now discorddrive{RESET}")
                print(f"    {BOLD}sudo loginctl enable-linger \"$USER\"{RESET}")
        back(title)


# ------------------------------------------------------------- copy help
def copy_help(cfg):
    mp = cfg.mount_point
    print(f"  Copy files onto {BOLD}{mp}{RESET} like any other drive: they upload in the background.")
    print()
    if WINDOWS:
        info("Drag and drop in File Explorer works. For very large folders, robocopy can resume:")
        print()
        print(f"    {BOLD}robocopy \"C:\\Source\\Folder\" \"{mp}\\Folder\" /E /Z{RESET}")
    else:
        info("For big copies, rsync skips what is already there and can be re-run any time.")
        info("This keeps retrying by itself after errors, and stops when everything is copied:")
        print()
        print(f"    {BOLD}nohup sh -c 'until rsync -rt --info=progress2 /source/folder/ "
              f"{mp}/folder/; do sleep 60; done; echo COPY COMPLETE' > ~/copy.log 2>&1 &{RESET}")
        print()
        info("Watch it with:  tail -f ~/copy.log")
    print()
    info("Status (option 3) shows uploads in progress. Files appear on your other devices as soon")
    info("as their upload finishes.")


# ------------------------------------------------------------- main menu
MAIN_OPTIONS = [
    ("1", "Start the drive"),
    ("2", "Stop the drive"),
    ("3", "Status (everything in detail)"),
    ("4", "Update DiscordDrive"),
    (None, None),
    ("5", "Setup (bot token, channel, encryption password)"),
    ("6", "Settings (cache, limits, drive letter...)"),
    ("7", "Files: old versions, deleted files, offline"),
    ("8", "Copy files onto the drive (help)"),
    ("9", "Tools and troubleshooting"),
    ("10", "Approve a new device (send it the key)"),
]
PAGE_TITLES = {"1": "Start the drive", "2": "Stop the drive", "3": "Status", "4": "Update DiscordDrive",
               "5": "Setup", "8": "Copy files onto the drive", "10": "Approve a new device"}


def main():
    while True:
        clear()
        banner()
        cfg = Config.load()
        offset = quick_status(cfg)
        pick = choose(MAIN, MAIN_OPTIONS, live=(lambda: drive_line(cfg), offset))
        if pick is None:
            clear()
            return 0
        if pick == "6":
            settings_menu()
            continue
        if pick == "7":
            files_menu()
            continue
        if pick == "9":
            tools_menu()
            continue
        if pick not in PAGE_TITLES:
            continue
        page(MAIN, PAGE_TITLES[pick])
        if pick == "1":
            start_drive()
        elif pick == "2":
            stop_drive()
        elif pick == "3":
            cli("status")
        elif pick == "4":
            if update():
                print()
                done("Updated. Reopening the menu with the new version...")
                time.sleep(1.5)
                return RESTART
        elif pick == "5":
            if cli("setup") == 0 and not is_mounted(Config.load()):
                print()
                if confirm("Start the drive now?"):
                    print()
                    start_drive()
        elif pick == "8":
            copy_help(cfg)
        elif pick == "10":
            info("Use this when you set up DiscordDrive on another device and it asks for the key.")
            print()
            cli("approve-keys")
        back()


def menu_start():
    """'start' / 'menu-start': start the drive the same way the menu does."""
    start_drive()
    return 0
