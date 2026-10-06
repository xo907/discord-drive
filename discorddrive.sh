#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
export PYTHONPATH="$DIR:$PYTHONPATH"

if [ -z "$1" ]; then
    python3 -m discorddrive mount
else
    python3 -m discorddrive "$@"
fi
