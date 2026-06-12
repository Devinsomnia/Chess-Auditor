#!/usr/bin/env bash
# ============================================================================
# chess-auditor one-click setup for Linux
#
# Installs everything the app needs:
#   1. Python 3 + venv + pip       - via your distro's package manager
#   2. Stockfish (the chess engine) - via your distro's package manager
#   3. A local Python environment (.venv) with all dependencies
#   4. Points config.yaml at the installed Stockfish
#
# Run it from the project folder:
#   chmod +x setup-linux.sh && ./setup-linux.sh
#
# Safe to re-run: every step is skipped if it's already done.
#
# Note: on Linux you use the overlay in a browser / OBS Browser source
# (http://localhost:8765/). The packaged ChessAuditor.exe desktop window is
# Windows-only, but the analysis overlay itself is identical.
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()   { printf '\033[32m    %s\033[0m\n' "$1"; }
fail() { printf '\033[31m    ERROR: %s\033[0m\n' "$1"; exit 1; }

# --- 1. system packages (python3, venv, pip, stockfish) ---------------------
step "Installing system packages (python3, venv, pip, stockfish)..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip stockfish
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip stockfish
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm python python-pip stockfish
elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y python3 python3-pip stockfish
else
    echo "    Unknown package manager. Please install python3 (3.10+), pip and" >&2
    echo "    stockfish yourself, then re-run this script." >&2
    exit 1
fi
ok "system packages installed"

# --- 2. Stockfish path -------------------------------------------------------
step "Locating Stockfish..."
STOCKFISH="$(command -v stockfish || true)"
[ -n "$STOCKFISH" ] || fail "stockfish not found on PATH after install."
ok "stockfish: $STOCKFISH"

# --- 3. Python environment ---------------------------------------------------
step "Creating the Python environment (.venv) and installing dependencies..."
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements.txt
ok "environment ready"

# --- 4. Point config.yaml at Stockfish ---------------------------------------
step "Writing the Stockfish path into config.yaml..."
sed -i "s|^\(\s*path:\s*\).*$|\1$STOCKFISH|" config.yaml
ok "config.yaml -> engine.path = $STOCKFISH"

# --- 5. Make the run scripts executable --------------------------------------
chmod +x run-live.sh run-demo.sh 2>/dev/null || true

printf '\n\033[32m=================== SETUP COMPLETE ===================\033[0m\n'
printf '\033[32m Try the demo:   ./run-demo.sh   then open http://localhost:8765/\033[0m\n'
printf '\033[32m Go live:        ./run-live.sh   (see README, step 2, for the userscript)\033[0m\n'
printf '\033[32m=======================================================\033[0m\n'
