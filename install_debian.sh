#!/usr/bin/env bash
# DiscordDrive installer for Debian / Ubuntu / Raspberry Pi OS.
# Usage: ./install_debian.sh [mount-dir]      (default mount dir: /mnt/discord)
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
MOUNT_DIR="${1:-/mnt/discord}"

echo "============================================================"
echo "          DiscordDrive - Debian / Linux Installer"
echo "============================================================"

echo "[1/4] Installing dependencies (libfuse2, fuse, python3-cryptography, curl)..."
sudo apt-get update -qq
# Debian 11/12 and Ubuntu use libfuse2; Debian 13+ (Trixie) / Ubuntu 24.04+ use libfuse2t64
if ! sudo apt-get install -y libfuse2 fuse python3 python3-cryptography curl; then
    echo "  -> Retrying with libfuse2t64..."
    sudo apt-get install -y libfuse2t64 fuse3 python3 python3-cryptography curl
fi

echo "[2/4] Enabling user_allow_other in /etc/fuse.conf (lets Samba / other users read the mount)..."
if [ -f /etc/fuse.conf ]; then
    sudo sed -i 's/^#\s*user_allow_other/user_allow_other/' /etc/fuse.conf
fi
grep -q "^user_allow_other" /etc/fuse.conf 2>/dev/null || echo "user_allow_other" | sudo tee -a /etc/fuse.conf >/dev/null

echo "[3/4] Creating mount point $MOUNT_DIR..."
sudo mkdir -p "$MOUNT_DIR"
sudo chown "$USER:$(id -gn)" "$MOUNT_DIR"

echo "[4/4] Making scripts executable..."
chmod +x "$DIR"/*.sh

echo ""
echo "============================================================"
echo "Installation complete. Next steps:"
echo ""
echo "  1. Configure your bot, channel and encryption key:"
echo "       $DIR/discorddrive.sh setup -m $MOUNT_DIR"
echo "     (Using the drive from another machine too? Use the same passphrase,"
echo "      or copy 'encryption_key' from that machine's config.)"
echo ""
echo "  2. Start / check / stop the drive:"
echo "       $DIR/start_drive.sh"
echo "       $DIR/discorddrive.sh status"
echo "       $DIR/stop_drive.sh"
echo ""
echo "  3. Optional - start automatically at boot (systemd user service):"
echo "       mkdir -p ~/.config/systemd/user"
echo "       sed \"s|%h/DiscordDrive|$DIR|g\" $DIR/discorddrive.service > ~/.config/systemd/user/discorddrive.service"
echo "       systemctl --user daemon-reload && systemctl --user enable --now discorddrive"
echo "       sudo loginctl enable-linger $USER"
echo "============================================================"
