#!/usr/bin/env bash
# Builds dist/discorddrive_<version>_all.deb (Debian, Ubuntu, Raspberry Pi OS).
# Usage: packaging/build_deb.sh        (needs dpkg-deb; run on Linux or in CI)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' discorddrive/__init__.py)"
PKG="build/deb/discorddrive_${VERSION}_all"
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/discorddrive" "$PKG/usr/bin" "$PKG/usr/lib/systemd/user"

cp -r discorddrive run.sh README.md CHANGELOG.md LICENSE "$PKG/opt/discorddrive/"
find "$PKG/opt/discorddrive" -name "__pycache__" -prune -exec rm -rf {} +
find "$PKG/opt/discorddrive" -type d -exec chmod 755 {} +
find "$PKG/opt/discorddrive" -type f -exec chmod 644 {} +
chmod 755 "$PKG/opt/discorddrive/run.sh" "$PKG/opt/discorddrive/discorddrive/scripts/linux/install.sh"

cat > "$PKG/usr/bin/discorddrive" <<'EOF'
#!/bin/sh
# DiscordDrive - Made by XO.ST. With no arguments: the menu.
exec /opt/discorddrive/run.sh "$@"
EOF
chmod 755 "$PKG/usr/bin/discorddrive"

cat > "$PKG/usr/lib/systemd/user/discorddrive.service" <<'EOF'
# Start the drive when you log in:  systemctl --user enable --now discorddrive
# Keep it running without a login:  sudo loginctl enable-linger "$USER"
[Unit]
Description=DiscordDrive encrypted Discord-backed drive
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/discorddrive mount
ExecStop=/usr/bin/discorddrive stop
KillSignal=SIGTERM
TimeoutStopSec=60
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

SIZE="$(du -sk "$PKG" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: discorddrive
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.9), python3-cryptography, libfuse2t64 | libfuse2, fuse3 | fuse, curl
Installed-Size: ${SIZE}
Maintainer: XO.ST <https://github.com/xo907/discord-drive>
Homepage: https://github.com/xo907/discord-drive
Description: Encrypted drive backed by a private Discord channel
 DiscordDrive mounts a private Discord channel as an encrypted folder, keeps
 several devices in sync, rebuilds pieces Discord loses from spare pieces,
 and has a web dashboard. Run "discorddrive" for the menu.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# Let the drive be shared with other users / Samba when allow_other is set.
if [ -f /etc/fuse.conf ] && ! grep -q '^[[:space:]]*user_allow_other' /etc/fuse.conf; then
    echo "user_allow_other" >> /etc/fuse.conf
fi
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst"

mkdir -p dist
dpkg-deb --build --root-owner-group "$PKG" "dist/discorddrive_${VERSION}_all.deb"
echo "Built dist/discorddrive_${VERSION}_all.deb"
