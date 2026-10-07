<h1 align="center">
    <img src="docs/images/logo-128.png" height="64" width="64" alt=""><br>
    DiscordDrive
</h1>
<p align="center"><b>An encrypted virtual drive backed by a private Discord channel.</b><br>Made by <b>XO.ST</b> · <a href="https://github.com/xo907/discord-drive">github.com/xo907/discord-drive</a></p>

---

DiscordDrive turns a private Discord channel into an encrypted drive: a drive letter on Windows
(e.g. `Z:\`) or a folder on Linux (e.g. `/mnt/discord`). It works on Windows, Linux servers and
Raspberry Pi, and keeps all your devices in sync.

Files you save to the drive are staged locally, split into chunks, encrypted, and uploaded as
attachments to your channel. Reading only downloads the chunks that cover the requested byte range,
so videos stream and seek without downloading the whole file first.

<p align="center"><img src="docs/images/overview.svg" alt="Your devices sync through DiscordDrive, which stores encrypted pieces in a private Discord channel" width="100%"></p>

> **Heads-up:** using Discord as general-purpose file storage may violate Discord's Terms of
> Service, and Discord can delete messages, attachments, or your bot/account at any time. Treat
> DiscordDrive as an experiment, **not** as your only copy of anything important.

---

## Quick start

About 10 minutes. You need a Discord account and a server you own (any empty server works:
in Discord, click **+** in the server list → **Create My Own**).

### Step 1: Create the Discord bot (same for Windows and Linux)

1. Go to <https://discord.com/developers/applications> → **New Application** → type any name → **Create**.
2. On the left click **Bot** → **Reset Token** → **Yes, do it!** → **Copy**.
   Paste the token somewhere for a minute; you need it in Step 2.
3. On the left click **OAuth2** and copy the **Client ID**. Paste it into this link in place of
   `YOUR_CLIENT_ID`, open the link, choose your server, and click **Authorize**:
   ```text
   https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot&permissions=109568
   ```
4. In your server, create a text channel for storage (for example `#drive`). Only you and the bot
   should be able to see it: in the channel's settings → **Permissions**, make it private and add your bot.
5. In Discord, go to **User Settings → Advanced** and turn on **Developer Mode**. Then right-click
   the channel → **Copy Channel ID**. You need this in Step 2 as well.

### Step 2a: Windows 10 / 11

Open a normal **PowerShell** (Start menu → type `PowerShell` → Enter; **not** "Run as administrator")
and paste:

```powershell
winget install -e --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements; winget install -e --id WinFsp.WinFsp --source winget --accept-package-agreements --accept-source-agreements; winget install -e --id Git.Git --source winget --accept-package-agreements --accept-source-agreements
```

Click **Yes** if Windows asks for permission. "Found an existing package already installed" just means
you already have that program, which is fine. When it is done, **close PowerShell and open a new one**
(so it finds the programs you just installed), then paste:

```powershell
git clone https://github.com/xo907/discord-drive.git "$HOME\DiscordDrive"; cd "$HOME\DiscordDrive"; .\run.bat
```

The DiscordDrive menu opens. Choose **5 (Setup)** and answer the questions:

| Question | What to type |
|---|---|
| Discord Bot Token | the token from Step 1 |
| Private Discord Channel ID | the channel ID from Step 1 |
| Mount Point Drive Letter `[Z:]` | press **Enter** (or type another free letter) |
| Enable Zero-Knowledge Encryption? `[Y/n]` | press **Enter** |
| Encryption Password | a password you will remember. **Use the same one on all your computers.** |

When setup asks "Start the drive now?", press **Enter**. Open **File Explorer**: your new drive is
**Z:**. Anything you put there is stored in Discord.

From now on, just double-click **`run.bat`** in the `DiscordDrive` folder (your user folder) to get the menu.

### Step 2b: Linux (Debian, Ubuntu, Raspberry Pi OS)

Open a terminal and paste. It works both as a normal user with `sudo` and as `root`, installs what
DiscordDrive needs, and opens the menu:

```bash
S=$(command -v sudo); $S apt update && $S apt install -y git && git clone https://github.com/xo907/discord-drive.git ~/DiscordDrive && cd ~/DiscordDrive && bash discorddrive/scripts/linux/install.sh && ./run.sh
```

In the menu choose **5 (Setup)**. Paste the bot token and channel ID, type **`/mnt/discord`** as the
mount directory, press **Enter** at "Enable encryption?", and type an encryption password (the
**same one on all your computers**). Answer **Enter** to "Start the drive now?".

Your files are in **`/mnt/discord`**. From now on, run **`~/DiscordDrive/run.sh`** to get the menu.

### Everyday use

Everything is in the menu: **`run.bat`** on Windows (double-click it), **`./run.sh`** on Linux.

<p align="center"><img src="docs/images/menu.svg" alt="The DiscordDrive menu" width="640"></p>

| Menu option | What it does |
|---|---|
| 1 / 2 | Start or stop the drive |
| 3 | Status: what is stored in Discord, what is uploading, cache and disk space |
| 4 | Update DiscordDrive to the latest version (stops and restarts the drive for you) |
| 5 | Setup: bot token, channel, encryption password |
| 6 | Settings: memory-only cache, cache size, disk-space limits, max file size, drive letter |
| 7 | Old versions, deleted files, offline files |
| 8 | How to copy lots of files onto the drive |
| 9 | Tools: check files, logs, encryption keys, rebuild the file list, Explorer menu, autostart |
| 10 | Approve a new device: send it the key when it asks |

Every option is also a direct command, handy for scripts and remote servers:
`run.bat status`, `./run.sh start`, `./run.sh stop`, `./run.sh config max_file_size 2G`, and so on
(see [Usage](#usage)).

<p align="center"><img src="docs/images/status.svg" alt="Example output of the status command" width="720"></p>

Stuck? See [Troubleshooting](#troubleshooting): it covers every problem we have run into on
Windows and Linux.

**Optional: keep nothing on this computer.** By default, files you open are cached on disk so they
open faster next time. To stream them from Discord every time instead (cached in RAM only), choose
**6 (Settings) → Read cache → `memory`** in the menu.

**Using a second computer?** Do Step 2 on it with the **same bot token and channel ID**. Setup
notices that the channel already holds your drive and offers to **request the key from one of your
other devices**:

1. On the new computer, setup shows a verification code (e.g. `4F7-2A1`) and waits.
2. On a computer that already has the drive, open the menu and choose **10 (Approve a new device)**.
   Check that it shows the same code, and accept.
3. The key is sent across, encrypted, and the new computer catches up with all your files and
   folders before it starts.

(You can also type your encryption password, or paste the key from `export-key`, instead.)

> **Back up your encryption password** (or the `encryption_key` from the config file). Without it,
> the data in Discord cannot be decrypted. Nobody can recover it for you.

---

## Features

<p align="center"><img src="docs/images/what-discord-sees.svg" alt="What you see on the drive compared with what Discord stores: only random names and encrypted data" width="100%"></p>

- **Client-side encryption (AES-256-GCM).** Chunks and index backups are encrypted before upload.
  Attachments get random names (`chk_<random>.bin`) and empty message text, so Discord never sees
  file names, folder structure, or contents. It can still see how many chunks there are, their
  sizes, and when they were uploaded.
- **Real drive / mount.** Uses [WinFsp](https://winfsp.dev/) on Windows and libfuse on Linux,
  so any application can use it.
- **Streaming and seeking.** Byte-range reads, read-ahead, and an on-disk LRU chunk cache.
- **Files on demand.** After upload the local copy is removed. Files take no local space until opened.
  With the memory-only cache, opened files are not stored on disk either (see below).
- **Offline pinning.** Keep chosen files or folders cached locally (on Windows, also from the
  Explorer right-click menu).
- **Live sync between devices.** Changes made on one computer appear on the others within a few
  seconds. Edits made on two devices at the same time are merged without losing either one.
- **File versions and undelete.** Replaced and deleted files are kept for 30 days (configurable).
  You can list them, bring back an older version, or recover a deleted file.
- **Crash-safe.** A local SQLite (WAL) index. Unfinished uploads resume on the next start, and
  changes made while offline are sent when the connection comes back.
- **Disaster recovery.** Encrypted index checkpoints are pinned in the channel. A fresh install
  restores the whole folder tree automatically.
- **Back-pressure.** Large copies pause while the upload backlog exceeds `staging_max_bytes` or
  free disk space drops below `min_free_disk_bytes`, so a big `rsync` cannot fill your local disk.

## Requirements

| | Windows 10/11 | Linux (Debian, Ubuntu, Raspberry Pi OS, ...) |
|---|---|---|
| Python | 3.9+ | 3.9+ |
| Filesystem driver | [WinFsp](https://winfsp.dev/rel/) | `libfuse2` (`libfuse2t64` on Debian 13+) + `fuse` |
| Encryption | built in (Windows CNG) | `python3-cryptography` |
| HTTP | `curl` (ships with Windows) | `curl` (or Python's urllib fallback) |

There are no other dependencies. A copy of [fusepy](https://github.com/fusepy/fusepy) is
vendored in `discorddrive/_vendor/` (ISC license).

---

## Configuration

The bot only needs *View Channels, Send Messages, Attach Files, Read Message History* and
*Manage Messages* (plus *Pin Messages* where Discord lists it separately); that is what
`permissions=109568` in the invite link grants. No privileged gateway intents are needed.

The config is stored outside the repository:

| | Config (token + key) | Data (index, cache, staging, log) |
|---|---|---|
| Windows | `%APPDATA%\DiscordDrive\config.json` | `%LOCALAPPDATA%\DiscordDrive\` |
| Linux | `~/.config/DiscordDrive/config.json` (mode 600) | `~/.local/share/DiscordDrive/` |

Change settings in the menu (**6 Settings**), with `config <name> <value>` (run `config` alone to
list them), or by editing the file.
Sizes accept units, e.g. `config max_file_size 2G` or `config min_free_disk_bytes 4G`.

Useful limits:

| Setting | Default | What it does |
|---|---|---|
| `max_file_size` | `0` (no limit) | Refuse files larger than this ("File too large"), so one huge file can't tie up the disk and uploads for hours |
| `min_free_disk_bytes` | `2G` | Never take the local disk below this much free space |
| `staging_max_bytes` | `10G` | Pause writing while this much is waiting to upload |
| `cache_mode` | `disk` | `memory` keeps files you open in RAM only |

`DISCORDDRIVE_CONFIG`, `DISCORDDRIVE_TOKEN` and `DISCORDDRIVE_CHANNEL` environment variables
override the config file location, token, and channel. See [`docs/config.example.json`](docs/config.example.json)
for every option.


---

## Usage

The menu (`run.bat` / `./run.sh` with nothing after it) covers everything. The same actions are
available as commands: put them after `run.bat` on Windows or `./run.sh` on Linux, e.g.
`run.bat status` or `./run.sh stop`.

```text
start                                Start the drive in the background
stop                                 Stop the drive (uploads continue on the next start)
status                               What is stored, what is uploading, cache and disk space
mount                                Run the drive in this window (Ctrl+C to stop)
setup                                Bot token, channel, encryption password
config [<name> [<value>]]            Show or change a setting (sizes like 500M, 2G)
offline <path>                       Keep a file/folder on this computer for offline use
free-space [<path>] [--all]          Remove cached data (one path, or everything)
clear-cache                          Remove all cached data that isn't kept offline
versions <file>                      List the older versions kept for a file
restore-version <file> <n> [--as p]  Bring back version n (or save it as a new file p)
deleted [<folder>]                   List deleted files that can still be recovered
undelete <path>                      Recover a deleted file
verify [<path>]                      Check that files can be downloaded and decrypted
log [-n 30] [--errors]               Show the end of the log file
approve-keys                         Send the key to a new device that asked for it
request-key                          Ask one of your other devices for the key
export-key                           Show the encryption key, to copy it to another device
add-old-key [--from-config <file>]   Add an earlier key so files encrypted with it stay readable
restore                              Rebuild this device's file list from Discord (drive stopped)
backup                               Save an index checkpoint now (normally automatic)
context-menu install|uninstall       "Make available offline" / "Free up space" in Explorer (Windows)
```

Paths can be given as `Z:\Folder\file.mp4`, `/mnt/discord/Folder/file.mp4`, or `/Folder/file.mp4`.

### Project layout

```text
run.bat / run.sh       start here: the menu, or a command
discorddrive/          the program (Python)
  scripts/windows/     helpers used by run.bat (hidden start, Explorer menu)
  scripts/linux/       install.sh (requirements) and the systemd service
docs/                  images and config.example.json
```

### Start automatically on Linux (systemd)

The menu shows the exact commands under **9 (Tools) → "How to start the drive automatically at
boot"**. In short:

```bash
mkdir -p ~/.config/systemd/user
sed "s|%h/DiscordDrive|$HOME/DiscordDrive|g" ~/DiscordDrive/discorddrive/scripts/linux/discorddrive.service > ~/.config/systemd/user/discorddrive.service
systemctl --user daemon-reload && systemctl --user enable --now discorddrive
sudo loginctl enable-linger "$USER"                 # keep running when you are logged out
```

### Sharing over Samba / with other users (Linux)

Set `"allow_other": true` in the config, or pass `mount --allow-other`. This requires
`user_allow_other` in `/etc/fuse.conf`, which the Linux installer (`install.sh`) enables.

---

## Using the same drive on several devices

**Sharing the key with a new device.** The easiest way is the built-in key request (setup offers it
automatically; menu **10** on the device that has the key approves it). How it stays private:

- The new device posts a request with a one-time Diffie-Hellman public value (2048-bit, RFC 3526)
  and shows a verification code derived from it.
- After you confirm the code on the other device, that device answers with its own one-time public
  value and your keys, encrypted with AES-256-GCM under a key that only those two devices can
  compute. Discord, or anyone else who has your bot token, only ever sees public values and
  ciphertext. Comparing the code stops anyone from slipping in a request of their own.
- Requests expire after 15 minutes, and both messages are deleted once the key arrives.

Every device needs the **same bot token, channel, and encryption key**. Either use the same
passphrase during `setup` (the key is derived from the passphrase and the channel ID, so it comes
out identical), or copy `encryption_key` from the first device's config. If `setup` sees that the
channel already holds an encrypted drive, it refuses to generate a new random key.

Devices stay in sync while they are running:

- A new or changed file appears on the other devices as soon as its upload finishes, plus up to
  `poll_interval` seconds (default 2). New folders, renames, moves, and deletes appear within a few seconds.
- A device that was off catches up when it starts.
- **Simultaneous changes are merged, never overwritten:**
  - If two devices create a file with the same name, one keeps the name and the other becomes
    `name (conflict xxxxxx).ext`.
  - Folders with the same name are merged.
  - If the same file is edited on two devices, the edit that reaches Discord last wins. The other
    edit is kept as a version (`discorddrive versions <file>`).
  - If one device deletes a file while another edits it, the edit wins.
- Windows Explorer does not refresh open folders by itself; press F5 to see changes made elsewhere.

**Upgrading from an older DiscordDrive:** update and start **one** device first. It converts its
index and publishes it. Then update the others: they adopt the published index automatically. Any of
their files that were still waiting to upload are kept and uploaded afterwards.

---

## What is stored on your computer

File contents live in Discord. Locally, DiscordDrive only uses:

| What | Location (data dir) | How long |
|---|---|---|
| Index (file list, versions) | `index.db` | Always; usually a few MB |
| Files being written | `staging/` | Until the upload finishes, then deleted. Writing pauses when more than `staging_max_bytes` (10 GiB) is waiting to upload, and resumes as uploads finish. DiscordDrive **never takes the disk below `min_free_disk_bytes`** (2 GiB): if its own uploads can't free space, it refuses the write instead, so other programs on the machine keep running. A file must be complete before it can be split and encrypted, so this cannot be avoided. |
| Files being edited | `staging/` | An existing file is downloaded completely while it is open for writing, then removed after it is re-uploaded |
| Viewed files (read cache) | `cache/` | **Disk mode (default):** kept up to `cache_max_bytes` (5 GiB) so re-opening is instant. **Memory mode:** never written to disk |
| Offline-pinned files | `cache/` | Until you unpin them (`free-space`) |

**Memory-only cache.** To keep viewed files off the disk entirely, set `"cache_mode": "memory"`
in the config, or start with `mount --cache memory`. Chunks you view are held only in RAM
(`memory_cache_bytes`, 256 MiB by default, enough for smooth streaming and seeking), and anything
previously cached on disk is deleted at startup. Re-opening a file downloads it from Discord again,
so it is slower.

---

## How it works

```
 application ──► WinFsp / libfuse ──► DiscordDriveFS (fs.py)
                                         │
              ┌──────────────────────────┼─────────────────────────┐
              ▼                          ▼                         ▼
     SQLite index (index.py)    staging files (writes)    chunk cache (cache.py)
     tree, chunk map, trash              │                         ▲
              │                          ▼                         │
              │                   Uploader (uploader.py)    downloads on read
              │                   chunk → encrypt → POST           │
              ├──── change journal (ops) ◄────► Discord channel ◄┘
              └──── periodic checkpoint ───────►     (journal.py)
```

- **Writing:** data goes to a staging file. When the last handle closes, the file is queued.
  Upload workers (`upload_threads`, default 3) split it into `chunk_size` pieces (9 MiB, just under
  the 10 MiB attachment limit for non-boosted servers), encrypt each piece, and post it as its own
  message. When all pieces are uploaded, the chunk list in the index is swapped atomically. The
  previous content is kept as a version, and expired versions are deleted from Discord in the background.
- **Syncing:** every change to the tree (file uploaded, folder created, rename, move, delete,
  timestamp) is recorded together with the local change and posted to the channel as a small
  encrypted "operation" message. Every device reads the channel every `poll_interval` seconds and
  applies all operations in Discord's message order, which is the same on every device, so all
  devices converge on the same tree. Files and folders have stable random IDs, so renames and edits
  on one device are matched up on the others.
- **Reading:** if a staging copy exists it is used. Otherwise the needed chunks are downloaded
  (checked against their SHA-256, with expired CDN links refreshed), cached, and read ahead.
- **Checkpoints:** every `index_backup_interval` seconds (when something changed), a device uploads
  a gzip-compressed, encrypted SQLite snapshot of the index and pins it. The snapshot records its
  position in the journal, so a new device restores it and replays only the operations after it.
  Snapshots only reference data that is fully uploaded.

| Module | Purpose |
|---|---|
| `cli.py` | Command-line interface |
| `config.py` | Configuration file handling |
| `drive.py` | Startup, mount and shutdown |
| `fs.py` | FUSE operations, staging, back-pressure |
| `uploader.py` | Upload workers, trash cleanup |
| `journal.py` | Multi-device sync: publishing, polling, and applying operations; checkpoints |
| `index.py` | SQLite metadata index, conflict handling, versions, snapshots |
| `cache.py` | On-disk LRU chunk cache with de-duplicated parallel downloads |
| `backend.py` | Discord storage adapter (and a local folder backend for testing) |
| `discord_api.py` | Minimal Discord REST client (curl or urllib) with retry and rate-limit handling |
| `crypto.py` | AES-256-GCM via Windows CNG or the `cryptography` package |
| `fuse_loader.py` | Finds WinFsp / libfuse and loads the vendored fusepy |

You can try it without Discord: `python -m discorddrive mount --mock <folder>` stores "messages"
as files in `<folder>`.

---

## Updating

In the menu choose **4 (Update DiscordDrive)**. It stops the drive, downloads the latest version,
starts the drive again and reopens the menu. Your settings, key and data are stored outside the
program folder, so updating never touches them. (`git pull` alone isn't enough: a running drive
keeps using the old version until it is restarted.)

Copying the files over yourself instead of using `git` (e.g. from Windows with `scp`)? Copying from
Windows drops Linux's "executable" permission, so restore it, then restart the drive:

```bash
chmod +x ~/DiscordDrive/run.sh ~/DiscordDrive/discorddrive/scripts/linux/*.sh
```

---

## Troubleshooting

If the drive doesn't start, the start script now prints the reason. Otherwise the log is the first
place to look; `log --errors` shows recent problems without hunting for the file:
`%LOCALAPPDATA%\DiscordDrive\discorddrive.log` on Windows, `~/.local/share/DiscordDrive/discorddrive.log`
on Linux (background starts also write `mount.log` next to it).

### Windows

- **`winget` fails with "Failed when searching source: msstore" / "server certificate did not match".**
  The Microsoft Store source is blocked or intercepted (antivirus, company network). The Quick Start
  command already avoids it with `--source winget`. If you typed your own `winget` command, add that.
- **`winget` says "Found an existing package already installed… No available upgrade found".**
  Not an error: that program is already installed. Carry on with the next step.
- **`git`, `py` or `python` "is not recognized" right after installing.** Close PowerShell and open
  a new one; already-open windows don't see newly installed programs.
- **The drive started, but Z: is not in File Explorer.** You probably started it from an
  **Administrator** PowerShell (the prompt shows `C:\WINDOWS\system32>`). Drives started as
  administrator are invisible to your normal Explorer. Stop it there (`run.bat stop`), then start it
  again by double-clicking `run.bat` and choosing 1 (Start).
- **The drive letter does not appear at all.** A leftover process from an earlier run can block
  the mount: in the menu choose 2 (Stop), then 1 (Start). Also check that WinFsp is installed (the
  menu warns you if it isn't).
- **New files from another device don't show in an open Explorer window.** Press **F5**. Explorer
  does not refresh network-style drives by itself.

### Linux

- **`sudo: command not found`.** You're logged in as `root` on a system without `sudo` (typical for
  a VPS). The Quick Start command and the installer handle this automatically; just leave
  `sudo` out of any command you type yourself.
- **`python: command not found`.** Linux calls it `python3`. Use `./run.sh`, which calls the
  right one.
- **`apt` fails with "404 Not Found" for `python3-cryptography` (or another package).** Seen on
  Debian 11, which has reached end of life: its security mirror lists updates whose files were
  removed. The installer retries automatically with the release's own version. By hand:
  ```bash
  apt-get install -y -t "$(. /etc/os-release; echo $VERSION_CODENAME)" python3-cryptography
  ```
- **`apt` wants to remove `fuse3`.** Don't let it: other software (Docker volumes, rclone, sshfs…)
  may need it. DiscordDrive only needs the FUSE 2 *library* (`libfuse2`) and works with either
  `fuse` or `fuse3` tools. The installer keeps whichever one is installed.
- **`E: Unable to locate package libfuse2t64`** (or `libfuse2`). The library was renamed:
  `libfuse2` on Debian 11/12 and Ubuntu up to 22.04, `libfuse2t64` on Debian 13+ and Ubuntu 24.04+.
  The installer picks the right name.
- **The installer warns that `/dev/fuse` does not exist.** Some VPS types (OpenVZ/LXC containers)
  have no FUSE support, so the drive cannot be mounted. Ask the provider to enable FUSE, or use a
  KVM-based server.
- **"No space left on device" while copying a lot of files.** Files you copy *in* are kept on the
  local disk until they are uploaded (the memory-only setting only affects files you *read*). Current
  versions never take the disk below `min_free_disk_bytes` (2 GiB, raise it with
  `config min_free_disk_bytes 5368709120` for 5 GiB): they pause the copy while uploads free space,
  and refuse writes (instead of filling the disk) when something else used the space. Update, then
  re-run the copy (rsync skips what is already there). On a small disk you can also lower the backlog: `config staging_max_bytes 2147483648`.
  If it still happens, check what is using the disk (`df -h /`, `du -sh ~/.cache`): when copying
  *from* another cloud mount such as rclone, that mount's own cache can fill the disk. DiscordDrive's
  log says so. Limit it, e.g. remount with `rclone mount ... --vfs-cache-mode minimal --vfs-cache-max-size 1G`.
  If you set `max_file_size`, give rsync the same limit with `--max-size=2G` so it *skips* larger
  files; otherwise rsync stops at the first one with "File too large".
  To make a long copy resume by itself after any error:
  ```bash
  until rsync -rt --info=progress2 /source/ /mnt/discord/target/; do sleep 60; done
  ```
- **`/mnt/discord` looks empty although the drive is running.** If your terminal was already
  *inside* that folder when the drive started, it keeps showing the plain folder underneath. Leave
  and come back: `cd ~ && ls /mnt/discord`.
- **"already mounted" after an update.** The old version is still running. Update from the menu
  (option 4), which restarts it; see [Updating](#updating).
- **"Mount directory is not empty".** DiscordDrive refuses to mount on top of existing files,
  because they would be hidden. Move them away or pick another directory (`./run.sh setup -m <dir>`).
- **"Transport endpoint is not connected".** An earlier instance crashed. Starting again cleans
  this up automatically, or run `fusermount -uz /mnt/discord` (`fusermount3 -uz` on FUSE 3 systems).

### All platforms

- **Editing the config by hand broke it** ("not valid JSON", "Expecting ',' delimiter"). Every
  line except the last needs a comma at the end. Easier: change settings with
  `config <name> <value>` (e.g. `config cache_mode memory`) instead of editing the file. A comma
  after the *last* entry is tolerated.
- **Files from another device don't show up.** Run `status` on both devices and compare:
  - **key fingerprint** must be identical. If not, run `setup` again with the same encryption
    password. If setup says the key doesn't match the existing drive, copy the key instead: run
    `export-key` on a working device, then `setup -k <that key>` on this one.
  - **Discord** must show the same channel.
  - **Sync position** must show a message number (not "not started"). If it says "not started",
    that device is still running an old version; see [Updating](#updating).
  - **Changes to share** on the device that made the change should be 0.
- **One device is missing files that the others have** (or shows a "Recovered files" folder),
  although its key fingerprint matches. It missed some sync messages, for example while it had a
  different key. Rebuild its file list from the drive: stop the drive, run `restore`, start it again.
- **Some files can't be decrypted on one device but work on another, or a device stopped seeing new
  files.** The devices are using different keys, usually because `setup` was run again with a
  password and replaced the original key. Compare the fingerprints in `status`. Nothing is lost:
  give each device the key the others are missing with `add-old-key`; it keeps reading with every
  key it knows while new data uses its current key. Easiest: copy a working device's config file
  over and run `add-old-key --from-config <that file>`, then stop and start the drive. Current
  versions of `setup` always keep the previous key, and older keys travel inside the encrypted
  index, so a new device set up with the password can read everything.
- **"Found index checkpoint ... could not restore it" / "Decryption / authentication failed".** This
  device has a different encryption key from the one that wrote the drive, so it refuses to start
  rather than show (and later save) an empty drive. This happens when the drive was created with an
  older version, which turned the same password into a different key on each computer, or with a
  random key. Copy the real key over:
  1. On a device where the drive works: `export-key` (menu 9 → "Show my encryption key", or `run.bat export-key` / `./run.sh export-key`).
  2. On this device: `setup -k <that key>`, then start the drive. Setup confirms the key matches.

  From Windows to a Linux machine in one step, without the key appearing on screen:
  ```powershell
  (Get-Content "$env:APPDATA\DiscordDrive\config.json" | ConvertFrom-Json).encryption_key | ssh user@host 'read k; ~/DiscordDrive/run.sh setup -m /mnt/discord -k "$k"'
  ```
- **A file won't open ("I/O error", "invalid argument", or the player just stops).** Run
  `verify <path>` (or `verify` for the whole drive; it downloads everything once). It lists every
  file that can't be downloaded or decrypted and why. "Encrypted with a different key" means that
  file was uploaded while this setup used another key, so it can only be read with that old key.
  If an older version of it exists, `versions <path>` and `restore-version` can bring it back.
- **A "Recovered files" folder appeared.** A change arrived for a file whose folder had been
  deleted on another device at the same time. The file was put here instead of being lost.
- **Bot invite says "successful" but the bot did not join.** The invite URL must include `scope=bot`.
- **Want to confirm encryption is on?** `status` shows `Encryption: ON (AES-256-GCM) | key
  fingerprint …`, and the log says `Zero-knowledge AES-256-GCM encryption ACTIVE` at every start.
  In the Discord channel, attachments are named `chk_<random>.bin` with no message text.

## License

[MIT](LICENSE). The vendored `discorddrive/_vendor/fuse.py` keeps its original ISC license.
