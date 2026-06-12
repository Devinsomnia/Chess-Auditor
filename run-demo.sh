#!/usr/bin/env bash
# Run the chess-auditor demo (Linux): cycles sample positions through the full
# analysis + overlay so you can confirm everything works, no game needed.
# Open http://localhost:8765/ while it runs. Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "No .venv found - run ./setup-linux.sh first." >&2; exit 1; }
export PYTHONPATH="$PWD/src"
echo "chess-auditor demo -> open http://localhost:8765/   (Ctrl+C to stop)"
exec .venv/bin/python -u demo.py "$@"
