# Changelog

Every change to DiscordDrive gets a new version number and an entry here. The dashboard shows this
list under the account menu, "What's new".

## 1.1.0 (2026-10-09)

- Bookmarks: a new tab in the dashboard. Paste a link (in the box, or Ctrl+V anywhere on the page;
  several at once work too) and it is saved as a card with the page's title, description, site name,
  icon and banner picture, read the way link previews are (Open Graph / Twitter card tags). Pages
  without a banner get a coloured card with the site's icon.
- Tags, notes and your own titles: Edit on a card; click a tag to show only those; a filter box
  searches titles, descriptions, sites, notes and tags. "Read the preview again" refreshes a card and
  keeps your title.
- Bookmarks live on the drive in /Bookmarks (the list and the pictures), so they are encrypted, synced
  to every device and versioned, and looking at them loads nothing from the sites themselves. Locking
  /Bookmarks with a password hides them like any folder.
- A link to something on this computer or the home network is saved without a preview (nothing is
  fetched from there).

## 1.0.2 (2026-10-09)

- Folder sync, backup mode: each file is copied once. The job remembers what it has backed up, so a
  copy you move, rename, change or delete on the drive is no longer put back by the next pass (before,
  moving files out of a backup folder made them upload again). A file is copied again only when it
  changes on the computer. The job's status says how many files this applies to.
- "Copy everything again" (the job's menu in the dashboard, or `sync run <n> --again`) puts back whatever
  is missing in the drive folder. Mirror and two-way sync are unchanged: they keep both sides the same.

## 1.0.1 (2026-10-09)

- Tests: the request pacing tests no longer fail now and then on Windows. They measured real waits
  with a clock that only moves in 15.6 ms steps there, so a 75 ms wait could read as 62.5 ms; they now
  run on a pretend clock and check the exact waits, including the 4x limit and the return to normal
  after five minutes. Nothing changes in how the drive behaves.

## 1.0.0 (2026-10-09)

- Home: the dashboard opens on an overview with what is on the drive, how well it is protected, folder
  sync and shared links, your starred items, the most recent files and the latest activity.
- Starred: star any file or folder (right-click, or in its details). Stars sync to all your devices.
- Activity: what was added, changed, renamed, moved and deleted, when, and on which device. Recent: the
  files changed last, anywhere on the drive.
- Storage: space by kind of file, the biggest folders and files, and identical files with one click to
  keep the oldest and delete the copies. Folders show their size in Files.
- File requests: right-click a folder, "Request files". People with the link send files into that folder
  from a simple page, without seeing what is in it; names never overwrite. With an expiry, an optional
  password and a size limit; listed under Shared with the number of files received.
- Edit text files in the browser (notes, code, config files): Edit in the menu or the details, Ctrl+S
  saves, and the version before is kept.
- Save from a link: paste a web address and the drive downloads the file itself into a folder, with
  progress and Cancel. Addresses on this computer or the home network are refused.
- Find anything with Ctrl+K: files, pages and actions from one box. Paste a screenshot or copied files
  anywhere to upload them. Download a selection of files and folders as one ZIP.
- Install as an app: the dashboard can be added to a phone's home screen or installed from the browser
  on a computer, and opens in its own window.
- Other apps (WebDAV): the drive can be opened by file managers on phones, "Map network drive", Finder,
  rclone and backup apps at /dav/, with the dashboard's user name and password. Off until turned on in
  Settings; password-locked folders are never shown there.

## 0.12.0 (2026-10-09)

- The config file no longer holds its secrets readable. Bot tokens, encryption keys and the dashboard
  sign-in are stored encrypted for the computer and account they belong to: on Windows with the
  account's own protection (DPAPI), on Linux and Raspberry Pi with a key file kept apart from the
  config (<data dir>/machine.key, readable by you only) together with the machine's id. A copy of the
  file (a backup, a synced folder, a screenshot, a support request) gives nothing away.
- Automatic on every device: nothing to set up or type, and the drive still starts by itself. An
  existing config is converted the first time this version of the drive starts. Ordinary settings stay
  readable and can still be edited by hand; a token or key typed into the file is picked up and
  encrypted at the next start.
- Because a copy of the config file is no longer a copy of your key, keep your encryption password (or
  the key from `export-key`) somewhere outside the computer. A config moved to another computer or
  account says clearly that its secrets can't be read there and asks for `setup`.
- `config` shows how the secrets are kept. `config protect_config false` turns this off (the secrets
  are then written readable again).

## 0.11.0 (2026-10-09)

- Password-locked folders and files. A locked item, and everything in it, is gone from the drive
  letter and from the dashboard (files, search, gallery, deleted files, snapshots, shared links, the
  log and upload progress) on every device, until its password is typed. Not even its name is shown.
- Unlocking is by password alone: every lock with that password opens. In the dashboard (the padlock
  at the top) it opens in that browser only; "Also show on the drive" or the `unlock` command shows it
  on that device's drive letter. It locks again after 15 minutes without use (Settings, or
  `config lock_timeout_minutes`), on sign-out, with "Lock again now" / `relock`, and when the drive
  restarts.
- Lock: right-click a folder or file in the dashboard, "Lock with a password", or `lock <path>`
  (menu 7). Remove a lock with its password: "Remove the lock" or `unprotect <path>`; with a forgotten
  password, `unprotect <path> --forgot` asks for the dashboard's password instead.
- Wrong passwords are slowed down like wrong sign-ins. Browsers keep no copy of pictures and files from
  locked folders. Folder sync keeps copying into a locked folder.
- A lock is a gate, not a second encryption: locked files are encrypted with the drive's key like all
  others, so it keeps out people using your computer, drive letter or dashboard, not somebody who has
  your config file. Both devices need this version for a lock to apply on both.
- Each sign-in to the dashboard is now its own session.

## 0.10.0 (2026-10-09)

- Gallery: a new tab in the dashboard with every photo and video on the drive, newest first, month by
  month. Click one for a full-screen viewer (arrow keys or the buttons go to the next and previous;
  download and details from there). Any folder opens as a gallery too: the picture button in Files, or
  right-click a folder, "Open as gallery".
- Thumbnails for photos and videos (a frame of the video). They are made the first time a picture
  comes into view, and "Create all thumbnails" in the gallery makes them for everything at once, with
  progress and Stop. Photos uploaded through the dashboard get theirs straight away.
- Thumbnails are kept on the computer running the drive (<data dir>/thumbs), encrypted with the drive's
  key, renewed when a file changes and removed when it is deleted.
- Files can be shown as a grid with thumbnails (the grid button next to New folder); selecting,
  dragging and right-click work as in the list.

## 0.9.1 (2026-10-09)

- Sync: Windows folders that OneDrive (or Windows settings) moved elsewhere are recognised. Choosing
  the empty old place, e.g. C:\Users\you\Documents when Windows keeps it in
  C:\Users\you\OneDrive\Documents, is refused with the right folder named; pairs set up that way show
  a note saying where the files really are. "Add a folder" in the menu suggests the real Downloads.
- Sync: an empty folder now says so ("the folder is empty, so there is nothing to copy") instead of
  "everything was already in step"; that message also shows how many files were compared.
- Sync: folders OneDrive keeps in the cloud (Files On-Demand) are synced; only shortcuts to other
  places (junctions, symbolic links) are skipped.

## 0.9.0 (2026-10-09)

- Sync and back up folders: keep a folder on this computer in step with a folder on the drive, e.g.
  C:\Users\you\Downloads backed up to Z:\Downloads by itself. Six ways: back up (new and changed
  files; deleting here keeps them on the drive), mirror (an exact copy), two-way sync (a file changed
  on both sides is kept twice), move (deleted here once it is safely in Discord, to free space),
  download and download mirror (a local copy of a drive folder, e.g. on an external disk).
- Runs live (a few seconds after something changes; Windows reports changes at once), every N minutes,
  daily at a set time, or only when started. Copies keep the file's date so nothing is copied twice;
  files still being written and unfinished downloads (*.crdownload, *.part, ...) wait; more files or
  folders can be skipped.
- Safe by default: a missing folder (a disk that isn't connected) changes nothing, a side that is
  suddenly empty deletes nothing on the other, files a sync removes from this computer are kept aside
  for 30 days, and files deleted on the drive stay under Deleted.
- Dashboard: a new Sync tab with folder browsers for this computer and the drive, live progress,
  Sync now, Stop, Pause, recent runs and problems. Folders can only be chosen on the computer itself,
  unless it allows other devices.
- Terminal: menu 12, and `sync list | add | edit | remove | run | stop | pause | resume | status | modes`
  (e.g. `sync add C:\Users\you\Downloads Z:\Downloads --mode backup --when live`).

## 0.8.0 (2026-10-09)

- Share links work on every device: they are synced through the change journal like files. A link
  made on a PC at home can be opened through another device's dashboard, e.g. a Raspberry Pi that is
  reachable from the internet (set "Address for share links" on the PC to the Pi's address). Changing
  or turning off a link applies everywhere, and the view count adds up the views on all devices.
- Links made with earlier versions are published to the other devices on the first start.

## 0.7.0 (2026-10-09)

- Direct links for shared files (`/s/<id>/<file name>`): the file itself instead of a page. Post one on
  its own in Discord and the picture, GIF, video or song shows up with no link text. Shown in the
  share dialog and in Shared → "Copy direct link". Works for files in shared folders too
  (`/s/<id>/<path inside the folder>`). Not available for password-protected links.
- Share pages carry preview tags (Open Graph), so posting the page link shows the photo, video or
  song as well.

## 0.6.0 (2026-10-09)

- Encrypted contacts: a Contacts tab in the dashboard. All contacts live in one vCard file,
  /Contacts/Contacts.vcf, on the drive, so they are encrypted, synced to every device and every change
  keeps the previous version.
- Import from an iPhone, Android, iCloud, Google Contacts or Outlook: vCard (.vcf, versions 2.1, 3.0
  and 4.0) and Google / Outlook CSV. Duplicates are skipped. Instructions for each are in the app.
- Create and edit contacts: name, company, job title, any number of phone numbers, emails, addresses
  and websites, birthday, notes and a photo. Call, message and email buttons; search; letters;
  select several to export or delete; export all as one .vcf to load back into a phone.

## 0.5.0 (2026-10-09)

- Check files in the dashboard (Health → Check files, or right-click a folder → Check for problems):
  reads every file under a folder in the background with live progress, repairs what spare pieces
  can rebuild, and lists files that can't be read with the reason (another encryption key, gone from
  Discord, damaged). Select some or all and delete them for good.
- Clearer message when a piece can't be read: it no longer always says "missing from Discord" (it may
  have been encrypted with another key).

## 0.4.1 (2026-10-09)

- Talks to Discord gently, so it no longer runs into Discord's rate limits: every request is spaced out
  on our side (per bot, per minute: 30 uploads, 15 deletes, 90 other requests by default), and if
  Discord still says "slow down", the drive goes slower for a few minutes by itself.
- New settings (dashboard Settings → Discord, the menu, or `config`): `discord_pace` gentle (default),
  balanced, fast or off, and `uploads_per_minute`, `deletes_per_minute`, `requests_per_minute`.
- Rate limits are no longer logged one line each; a short summary appears now and then.
- Files whose old pieces can't be read are reported once instead of after every start.

## 0.4.0 (2026-10-09)

- Live progress for every upload: a bar with the percentage, speed and time left, for files sent from
  the browser and for the upload to Discord (also in the note editor). Progress refreshes every second
  while something is moving.
- New Log tab: what is uploading and downloading right now (with progress, speed and time left), what
  is waiting, and every log line as it happens, with filters, search, pause and download.
- Box selection in Files: press on empty space and drag to select several items. Every row also has a
  checkbox (on hover, or after choosing Select on a phone).
- Version numbers and this changelog; "What's new" in the dashboard's account menu.

## 0.3.0 (2026-10-09)

- Drag and drop in the dashboard: drag files and folders onto a folder, the path at the top or Files to
  move them, onto Deleted to delete them; Ctrl/Cmd-click and Shift-click select several; files dragged
  in from the computer upload into the folder they are dropped on; a folder browser for Move to.
- Notes tab: notes are files in /Notes on the drive. Typing saves at once and uploads when you pause;
  Save (Ctrl+S) uploads right away. Changes from other devices appear by themselves.
- Share links: choose how long a link works, an optional password, and view-only. The page shows the
  photo, video, music, PDF or text; whole folders can be shared. New Shared tab to manage links.
- Settings page in the dashboard; domain names and the share-link address in the menu too. Share links
  use your domain.
- Password setup falls back to PBKDF2 when there isn't enough memory for scrypt.

## 0.2.2 (2026-10-09)

- The dashboard works behind a reverse proxy (Nginx Proxy Manager): `config web_hosts <domain>`.

## 0.2.1 (2026-10-09)

- Dashboard sign-in with a user name and password (stored as a scrypt hash), sign out, and a lockout
  after repeated wrong passwords. Replaces the secret sign-in link.
- Right-click (and long-press on phones) menus for files, folders, empty space and snapshots; folders
  download as ZIP; Duplicate.
- Deleted: select several or all, restore, or delete forever on every device (`purge`).
- Fixed: restoring a file right after deleting it could be undone by the delete arriving later.
  Restoring a file whose folder was deleted re-creates the folder.

## 0.2.0 (2026-10-09)

- Self-healing: Reed-Solomon spare pieces, rebuilt on read, repaired everywhere, background check,
  older files protected in the background.
- Faster uploads (pieces in parallel, extra bots), compression and de-duplication.
- Web dashboard; snapshots; offline folders that stay in sync; hidden folders per device; scrypt for
  new passwords; tests on Windows and Linux; Windows .exe and .deb builds.

## 0.1.0

- The encrypted drive in a Discord channel: Windows and Linux, live sync between devices, versions and
  undelete, offline files, key sharing between devices, autostart.
