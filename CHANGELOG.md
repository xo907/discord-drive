# Changelog

Every change to DiscordDrive gets a new version number and an entry here. The dashboard shows this
list under the account menu, "What's new".

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
