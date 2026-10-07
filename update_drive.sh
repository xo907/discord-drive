#!/usr/bin/env bash
# Updates DiscordDrive: stop the drive, download the latest version, start it again.
# Everything is inside { } so bash reads the whole script before git pull can replace it.
{
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR" || exit 1

echo "============================================================"
echo "                  Updating DiscordDrive"
echo "============================================================"

if ! command -v git >/dev/null 2>&1; then
    echo "[ERROR] git is not installed: apt install -y git" >&2
    exit 1
fi

./stop_drive.sh
echo
echo "Downloading the latest version..."
if ! git pull --ff-only; then
    echo
    echo "[WARNING] Could not update (see the message above). Starting the current version again."
fi
chmod +x ./*.sh 2>/dev/null
echo
# Start from the home folder, so a terminal sitting inside the mount point can't hide it.
(cd ~ && "$DIR/start_drive.sh")
exit
}
