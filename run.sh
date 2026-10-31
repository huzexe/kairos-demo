#!/usr/bin/env sh
# Start Kairos on macOS or Linux. Double-click (macOS: rename to run.command) or run ./run.sh
cd "$(dirname "$0")" && exec python3 start.py "$@"
