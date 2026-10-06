# DiscordDrive

**DiscordDrive** turns a private Discord channel into an encrypted virtual drive: a drive letter
on Windows (e.g. `Z:\`) or a mount directory on Linux (e.g. `/mnt/discord`).

Files you save to the drive are staged locally, split into chunks, encrypted, and uploaded as
attachments to your channel. Reading only downloads the chunks that cover the requested byte range,
so videos stream and seek without downloading the whole file first.

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
git clone https://github.com/xo907/discord-drive.git "$HOME\DiscordDrive"; cd "$HOME\DiscordDrive"; .\DiscordDrive.cmd setup
```

Setup asks five questions:

| Question | What to type |
|---|---|
| Discord Bot Token | the token from Step 1 |
| Private Discord Channel ID | the channel ID from Step 1 |
| Mount Point Drive Letter `[Z:]` | press **Enter** (or type another free letter) |
| Enable Zero-Knowledge Encryption? `[Y/n]` | press **Enter** |
| Encryption Password | a password you will remember. **Use the same one on all your computers.** |

Start the drive:

```powershell
.\start_drive.cmd
```

Open **File Explorer**: your new drive is **Z:**. Anything you put there is stored in Discord.

### Step 2b: Linux (Debian, Ubuntu, Raspberry Pi OS)

Open a terminal and paste (works both as a normal user with `sudo` and as `root`):

```bash
S=$(command -v sudo); $S apt update && $S apt install -y git && git clone https://github.com/xo907/discord-drive.git ~/DiscordDrive && cd ~/DiscordDrive && ./install_debian.sh
```

Then run setup. Paste the bot token and channel ID, press **Enter** at "Enable encryption?", and type
an encryption password (the **same one on all your computers**):

```bash
./discorddrive.sh setup -m /mnt/discord
```

Start the drive:

```bash
./start_drive.sh
```

Your files are in **`/mnt/discord`**.

### Everyday use

| | Windows (in the `DiscordDrive` folder) | Linux (in `~/DiscordDrive`) |
|---|---|---|
| Start | `.\start_drive.cmd` | `./start_drive.sh` |
| Stop | `.\stop_drive.cmd` | `./stop_drive.sh` |
| Status | `.\DiscordDrive.cmd status` | `./discorddrive.sh status` |
| Update to the latest version | see [Updating](#updating) | see [Updating](#updating) |

On Windows you can also just double-click `start_drive.cmd` / `stop_drive.cmd` in File Explorer.

Stuck? See [Troubleshooting](#troubleshooting): it covers every problem we have run into on
Windows and Linux.

**Optional: keep nothing on this computer.** By default, files you open are cached on disk so they
open faster next time. To stream them from Discord every time instead (cached in RAM only), run this
once, then stop and start the drive:

```powershell
.\DiscordDrive.cmd config cache_mode memory
```
```bash
./discorddrive.sh config cache_mode memory
```

**Using a second computer?** Do Step 2 on it with the **same bot token, channel ID, and encryption
password**. Everything you stored appears there automatically, and changes sync both ways within seconds.
Setup checks the key against your existing drive. If it says the key doesn't match (for example
because the drive was set up with an older version or a random key), copy the key over instead:
run `export-key` on a computer where the drive works, then `setup -k <that key>` on the new one.

> **Back up your encryption password** (or the `encryption_key` from the config file). Without it,
> the data in Discord cannot be decrypted. Nobody can recover it for you.

---

## Features

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

Change settings with `config <name> <value>` (run `config` alone to list them), or edit the file.
`DISCORDDRIVE_CONFIG`, `DISCORDDRIVE_TOKEN` and `DISCORDDRIVE_CHANNEL` environment variables
override the config file location, token, and channel. See [`config.example.json`](config.example.json)
for every option.


---

## Usage

| Task | Windows | Linux |
|---|---|---|
| Start in background | `start_drive.cmd` | `./start_drive.sh` |
| Run in foreground (Ctrl+C to stop) | `DiscordDrive.cmd mount` | `./discorddrive.sh mount` |
| Stop | `stop_drive.cmd` | `./stop_drive.sh` |
| Status | `status_drive.cmd` | `./discorddrive.sh status` |
| Clear local cache | `clear_cache.cmd` | `./clear_cache.sh` |

Other commands (`DiscordDrive.cmd <cmd>` / `./discorddrive.sh <cmd>`):

```text
offline <path>        Pin a file/folder and download it for offline use   (alias: pin)
free-space [<path>]   Evict cached data (one path, or --all)               (alias: unpin)
versions <file>                      List the older versions kept for a file
restore-version <file> <n> [--as p]  Bring back version n (or save it as a new file p)
deleted [<folder>]                   List deleted files that can still be recovered
undelete <path>                      Recover a deleted file
config [<name> [<value>]]            Show or change a setting
export-key                           Show the encryption key, to copy it to another device
add-old-key [--from-config <file>]   Add an earlier key so files encrypted with it stay readable
verify [<path>]                      Check that files can be downloaded and decrypted
log [-n 30] [--errors]               Show the end of the log file
backup                Save an index checkpoint now (normally automatic)
restore               Rebuild the local index from the channel (drive must be stopped)
context-menu install  Add "Make available offline" / "Free up space" to Explorer (Windows)
```

Paths can be given as `Z:\Folder\file.mp4`, `/mnt/discord/Folder/file.mp4`, or `/Folder/file.mp4`.

### Start automatically on Linux (systemd)

`install_debian.sh` prints the exact commands. In short:

```bash
mkdir -p ~/.config/systemd/user
cp discorddrive.service ~/.config/systemd/user/    # edit the paths if the repo is not ~/DiscordDrive
systemctl --user daemon-reload
systemctl --user enable --now discorddrive
sudo loginctl enable-linger "$USER"                 # keep running when you are logged out
```

### Sharing over Samba / with other users (Linux)

Set `"allow_other": true` in the config, or pass `mount --allow-other`. This requires
`user_allow_other` in `/etc/fuse.conf`, which `install_debian.sh` enables.

---

## Using the same drive on several devices

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
| Files being written | `staging/` | Until the upload finishes, then deleted. Writing pauses when more than `staging_max_bytes` (10 GiB) is waiting to upload or the disk has less than `min_free_disk_bytes` (2 GiB) free, and resumes as uploads finish. A file must be complete before it can be split and encrypted, so this cannot be avoided. |
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

Stop the drive **before** updating and start it again afterwards. If you only run "start", it sees
the old version still running, prints `already mounted`, and keeps using the old code.

Windows (in the `DiscordDrive` folder):

```powershell
.\stop_drive.cmd; git pull; .\start_drive.cmd
```

Linux (in `~/DiscordDrive`):

```bash
./stop_drive.sh && git pull && ./start_drive.sh
```

Copying the files over yourself instead of using `git` (e.g. from Windows with `scp`)? Copying from
Windows drops Linux's "executable" permission, so restore it before starting:

```bash
chmod +x ~/DiscordDrive/*.sh
```

Your settings, key and data are stored outside the program folder, so updating never touches them.

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
  administrator are invisible to your normal Explorer. Run `.\stop_drive.cmd` there, then start it
  again from a normal PowerShell, or by double-clicking `start_drive.cmd`.
- **The drive letter does not appear at all.** A leftover process from an earlier run can block
  the mount: run `.\stop_drive.cmd`, then `.\start_drive.cmd`. `start_drive.cmd` is more reliable
  than `mount -b`. Also check that WinFsp is installed (`.\DiscordDrive.cmd status` shows it).
- **New files from another device don't show in an open Explorer window.** Press **F5**. Explorer
  does not refresh network-style drives by itself.

### Linux

- **`sudo: command not found`.** You're logged in as `root` on a system without `sudo` (typical for
  a VPS). The Quick Start command and `install_debian.sh` handle this automatically; just leave
  `sudo` out of any command you type yourself.
- **`python: command not found`.** Linux calls it `python3`. Use the scripts (`./start_drive.sh`,
  `./discorddrive.sh <command>`), which call the right one.
- **`apt` fails with "404 Not Found" for `python3-cryptography` (or another package).** Seen on
  Debian 11, which has reached end of life: its security mirror lists updates whose files were
  removed. `install_debian.sh` retries automatically with the release's own version. By hand:
  ```bash
  apt-get install -y -t "$(. /etc/os-release; echo $VERSION_CODENAME)" python3-cryptography
  ```
- **`apt` wants to remove `fuse3`.** Don't let it: other software (Docker volumes, rclone, sshfs…)
  may need it. DiscordDrive only needs the FUSE 2 *library* (`libfuse2`) and works with either
  `fuse` or `fuse3` tools. `install_debian.sh` keeps whichever one is installed.
- **`E: Unable to locate package libfuse2t64`** (or `libfuse2`). The library was renamed:
  `libfuse2` on Debian 11/12 and Ubuntu up to 22.04, `libfuse2t64` on Debian 13+ and Ubuntu 24.04+.
  The installer picks the right name.
- **The installer warns that `/dev/fuse` does not exist.** Some VPS types (OpenVZ/LXC containers)
  have no FUSE support, so the drive cannot be mounted. Ask the provider to enable FUSE, or use a
  KVM-based server.
- **"No space left on device" while copying a lot of files.** Files you copy *in* are kept on the
  local disk until they are uploaded (the memory-only setting only affects files you *read*). Current
  versions pause the copy instead of filling the disk; update, then re-run the copy (rsync skips what
  is already there). On a small disk you can also lower the backlog: `config staging_max_bytes 2147483648`.
- **`/mnt/discord` looks empty although the drive is running.** If your terminal was already
  *inside* that folder when the drive started, it keeps showing the plain folder underneath. Leave
  and come back: `cd ~ && ls /mnt/discord`.
- **`start_drive.sh` says "already mounted" after an update.** The old version is still running;
  see [Updating](#updating).
- **"Mount directory is not empty".** DiscordDrive refuses to mount on top of existing files,
  because they would be hidden. Move them away or pick another directory (`./discorddrive.sh setup -m <dir>`).
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
  - **Channel** must be the same.
  - **Journal** must show a message number (not "not started"). If it says "not started", that
    device is still running an old version; see [Updating](#updating).
  - **Pending Publish** on the device that made the change should be 0.
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
  1. On a device where the drive works: `export-key` (`DiscordDrive.cmd export-key` or `./discorddrive.sh export-key`).
  2. On this device: `setup -k <that key>`, then start the drive. Setup confirms the key matches.

  From Windows to a Linux machine in one step, without the key appearing on screen:
  ```powershell
  (Get-Content "$env:APPDATA\DiscordDrive\config.json" | ConvertFrom-Json).encryption_key | ssh user@host 'read k; cd ~/DiscordDrive && ./discorddrive.sh setup -m /mnt/discord -k "$k"'
  ```
- **A file won't open ("I/O error", "invalid argument", or the player just stops).** Run
  `verify <path>` (or `verify` for the whole drive; it downloads everything once). It lists every
  file that can't be downloaded or decrypted and why. "Encrypted with a different key" means that
  file was uploaded while this setup used another key, so it can only be read with that old key.
  If an older version of it exists, `versions <path>` and `restore-version` can bring it back.
- **A "Recovered files" folder appeared.** A change arrived for a file whose folder had been
  deleted on another device at the same time. The file was put here instead of being lost.
- **Bot invite says "successful" but the bot did not join.** The invite URL must include `scope=bot`.
- **Want to confirm encryption is on?** `status` shows `Encryption: ENABLED (AES-256-GCM | key
  fingerprint …)`, and the log says `Zero-knowledge AES-256-GCM encryption ACTIVE` at every start.
  In the Discord channel, attachments are named `chk_<random>.bin` with no message text.

## License

[MIT](LICENSE). The vendored `discorddrive/_vendor/fuse.py` keeps its original ISC license.
