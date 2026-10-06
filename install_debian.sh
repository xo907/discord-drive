#!/usr/bin/env bash
# DiscordDrive installer for Debian / Ubuntu / Raspberry Pi OS.
# Usage: ./install_debian.sh [mount-dir]      (default mount dir: /mnt/discord)
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
MOUNT_DIR="${1:-/mnt/discord}"

# Privileged steps run directly when already root (e.g. on a VPS), otherwise through sudo.
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
elif command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
else
    echo "[ERROR] This installer needs root rights. Run it as root, or install sudo first." >&2
    exit 1
fi
ME="$(id -un)"
MYGROUP="$(id -gn)"

echo "============================================================"
echo "          DiscordDrive - Debian / Linux Installer"
echo "============================================================"

echo "[1/4] Installing dependencies (libfuse2, fuse, python3-cryptography, curl)..."
$SUDO apt-get update -qq
# Debian 11/12 and Ubuntu use libfuse2; Debian 13+ (Trixie) / Ubuntu 24.04+ use libfuse2t64
if ! $SUDO apt-get install -y libfuse2 fuse python3 python3-cryptography curl; then
    echo "  -> Retrying with libfuse2t64..."
    $SUDO apt-get install -y libfuse2t64 fuse3 python3 python3-cryptography curl
fi

echo "[2/4] Enabling user_allow_other in /etc/fuse.conf (lets Samba / other users read the mount)..."
if [ -f /etc/fuse.conf ]; then
    $SUDO sed -i 's/^#\s*user_allow_other/user_allow_other/' /etc/fuse.conf
fi
grep -q "^user_allow_other" /etc/fuse.conf 2>/dev/null || echo "user_allow_other" | $SUDO tee -a /etc/fuse.conf >/dev/null

if [ ! -e /dev/fuse ]; then
    echo "  [WARNING] /dev/fuse does not exist. This machine may not support FUSE (common on"
    echo "            OpenVZ/LXC container VPSes); ask your provider to enable FUSE, or use a KVM VPS."
fi

echo "[3/4] Creating mount point $MOUNT_DIR..."
$SUDO mkdir -p "$MOUNT_DIR"
$SUDO chown "$ME:$MYGROUP" "$MOUNT_DIR"

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
echo "       ${SUDO:+sudo }loginctl enable-linger $ME"
echo "============================================================"
