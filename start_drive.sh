#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
echo "Starting DiscordDrive in the background..."
"$DIR/discorddrive.sh" mount -b
echo ""
"$DIR/discorddrive.sh" status
