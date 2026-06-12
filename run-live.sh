#!/usr/bin/env bash
# Launch chess-auditor in LIVE mode (Linux). Run ./setup-linux.sh first.
# Receives positions from the browser userscript and serves the overlay at
# http://localhost:8765/ (open in a browser or add as an OBS Browser source).
# Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "No .venv found - run ./setup-linux.sh first." >&2; exit 1; }
export PYTHONPATH="$PWD/src"
echo "chess-auditor live overlay -> http://localhost:8765/"
echo "Add that URL as an OBS Browser source. Ctrl+C to stop."
exec .venv/bin/python -u -m chess_auditor.main --source post --color auto "$@"
