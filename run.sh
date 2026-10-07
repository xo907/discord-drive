#!/usr/bin/env bash
# DiscordDrive - Made by XO.ST - https://github.com/xo907/discord-drive
#   ./run.sh              opens the menu
#   ./run.sh <command>    runs a command directly, e.g.  ./run.sh status
# Everything is inside { } so bash reads the whole file before an update can replace it.
{
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$ROOT" || exit 1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required:  sudo apt install -y python3   (then run ./run.sh again)" >&2
    exit 1
fi
if [ $# -gt 0 ]; then
    exec python3 -m discorddrive "$@"
fi
while true; do
    python3 -m discorddrive menu
    code=$?
    [ "$code" -eq 75 ] || exit "$code"
done
}
