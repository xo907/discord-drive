# Changelog

Every change to DiscordDrive gets a new version number and an entry here. The dashboard shows this
list under the account menu, "What's new".

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
