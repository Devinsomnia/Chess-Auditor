# chess-auditor — How to Run (conda + OBS + browser setup)

This guide gets you from a fresh machine to a live analysis overlay on your
stream. It assumes Windows + PowerShell.

> **What this is:** a *broadcast / commentary* analysis overlay. It shows the
> best move, danger, and forced mates to **your viewers and casters** — it is
> not a private feed to the player mid-game. See [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).

---

## ⭐ Easiest way: the desktop app (`ChessAuditor.exe`)

If you just want to **double-click and go**, open the **`dist`** folder. There
are two clickable shortcuts — pick the window style you want:

| Double-click | Window style | Use when |
|---|---|---|
| **Chess Auditor (Desktop).lnk** | frameless, auto-sized, draggable widget | you want the analysis on your screen, no OBS (set `app.always_on_top: true` in `config.yaml` to keep it in front of other windows) |
| **Chess Auditor (OBS).lnk** | normal titled, resizable, **not** always-on-top (minimizable) | you'll show it via OBS and don't want it covering your desktop |

Both run the **same analysis engine and overlay** (server on `localhost:8765`),
so OBS can read it in either mode — the only difference is the window.

You can also just double-click **`ChessAuditor.exe`** directly; it uses the
default style set by `app.mode` in `config.yaml` (`desktop` or `obs`), or pass
`--mode obs` / `--mode desktop` to override.

### In-app controls

In the side panel, under the **Danger** section, there's a **Controls** panel:

- **⠿ Hold here to move window** — press and hold this handle, then drag to
  reposition the window. (Whole-window dragging is off so it no longer fights
  with clicking the board/buttons.)
- **⇄ Switch to OBS / Desktop mode** (green) — switches the window style live. It
  saves your choice to `config.yaml` and relaunches the app in the new style
  (takes ~2–3s).
- **✕ Quit app** (red) — terminates the app and its engine cleanly.

These buttons only appear inside the desktop app — they are **not** shown in the
OBS browser source or a plain browser, so they never end up on your stream.

Keep `config.yaml` in the same folder as the exe (it's already there) — edit it
to change engine path, depth, speed, or the default window mode. Logs go to
`dist\logs\`.

You still need the **Tampermonkey userscript** (section 3 below) so the app
receives the live position from your game, and you still set up OBS (section 5)
if you want it on stream — the desktop window and the OBS browser source both
read the same overlay, so you can use either or both.

To rebuild the exe after code changes: **`.\build-exe.ps1`**.

> Prefer running from source / OBS only? Skip this and use `run-live.ps1`
> (section 4). Both do the same analysis.

---

## 0. One-time prerequisites

These are already installed on this machine, but for a clean setup:

| Tool | Why | Install |
|------|-----|---------|
| **Miniconda** | Python environment manager | `winget install Anaconda.Miniconda3` |
| **Stockfish** | the chess engine | `winget install Stockfish.Stockfish` |
| **Tampermonkey** | runs the board-reader userscript in Brave | Chrome Web Store |
| **OBS Studio** | streaming / overlay compositor | `winget install OBSProject.OBSStudio` |

After installing Stockfish, confirm the path in [config.yaml](config.yaml) under
`engine.path` points at `stockfish-windows-x86-64-avx2.exe`.

---

## 1. Create the conda environment

From the project folder:

```powershell
conda env create -f environment.yml
conda activate chessauditor
```

That creates an environment named **`chessauditor`** with Python 3.12 and all
dependencies (python-chess, PyYAML, mss, opencv-python, numpy).

To recreate or update it later:
```powershell
conda env update -f environment.yml --prune      # apply changes
conda remove -n chessauditor --all               # delete it entirely
```

> The launch scripts (`run-live.ps1`, `run-demo.ps1`) find the `chessauditor`
> env automatically — you don't strictly need to `conda activate` first.

---

## 2. Quick test — the demo (no game needed)

```powershell
.\run-demo.ps1
```

Open **http://localhost:8765/** in Brave. You should see the analysis board
cycle through positions with the **green best-move arrow**, **yellow danger
boxes**, the eval bar, and (on mating positions) the **mate banner**. Press
`Ctrl+C` in the terminal to stop.

If you see this, the engine + overlay are working. Now wire up the live game.

---

## 3. Browser / "development mode" setup (read the live board)

The overlay gets the live position from a **Tampermonkey userscript** that reads
chess.com's board. To allow it to run, Brave (Chromium MV3) needs script
injection enabled — this is the "development mode" step:

1. **Install Tampermonkey** in Brave (Chrome Web Store).
2. Go to **`brave://extensions`**.
3. Open **Tampermonkey → Details** and turn ON **"Allow User Scripts"**.
   - If that toggle isn't there, turn ON **"Developer mode"** (top-right switch
     on the extensions page) instead.
4. **Restart Brave** so the change takes effect.
5. Open the Tampermonkey dashboard → **Create a new script**, delete the
   template, and paste the entire contents of
   [browser/chesscom-overlay.user.js](browser/chesscom-overlay.user.js). Save
   with `Ctrl+S`.

### Verify the userscript
Open a chess.com game. You should see a small **"chess-auditor"** pill at the
bottom-right of the page:
- **yellow "starting…"** → it loaded,
- **green "live (game-api)"** → it's pushing positions to the overlay.

First time, Tampermonkey may ask to allow a cross-origin request to
`127.0.0.1` — click **Always allow**. (Press `F12` → Console to see
`[chess-auditor]` log lines if anything looks off.)

---

## 4. Run it live

```powershell
.\run-live.ps1
```

This starts the analysis server (under conda) and prints the overlay URL and the
game-log path. Leave it running while you play. Stop with `Ctrl+C` or:

```powershell
.\stop.ps1
```

---

## 5. OBS setup (put the overlay on stream)

1. In OBS, add a **Source → Browser**.
2. URL: **`http://localhost:8765/`**
3. Size: **1280 × 720** (or to taste).
4. Position it where you want over your scene.

Whenever you change the overlay or restart, **right-click the Browser source →
Refresh** to reload it.

The overlay always orients **your player at the bottom**, whatever color they
are, and the eval/mate are shown from **your player's** point of view:

- `+1.5` = you're winning · `-1.5` = opponent better
- green banner **"FORCED MATE IN N — YOU"** = you have the mate
- red banner **"MATE THREAT IN N — OPPONENT"** = opponent has the mate

---

## 6. Speed vs. strength tuning

One knob: `engine.movetime_ms` in [config.yaml](config.yaml) (milliseconds per
position). End-to-end latency is roughly this value + ~30 ms (the position is
pushed to the engine and the overlay long-polls, so there's no polling lag).

| movetime_ms | Feel | Strength |
|-------------|------|----------|
| **150** (default) | snappiest | still finds the right move almost always |
| 250 | great balance | strong |
| 500–1000 | slight lag | best in sharp tactics |

Per-run overrides (no need to edit config):
```powershell
.\run-live.ps1                                    # uses config (150 ms)
# or run main directly for overrides:
conda activate chessauditor
$env:PYTHONPATH="src"; python -m chess_auditor.main --source post --color auto --movetime 150
```

---

## 7. After the game — review (mate swings & blunders)

Every game is logged to `logs/game-<timestamp>.jsonl` (only the **last 10**
games are kept). To analyze the most recent game:

```powershell
conda activate chessauditor
python review.py            # console report
python review.py --html     # also writes logs/game-*.html you can screenshot
```

It flags **missed mates**, **allowed forced mates**, and **blunders/mistakes**,
showing the move played vs. the engine's best move and the eval swing.

---

## 8. Reading the board another way (optional)

If the userscript ever breaks (chess.com markup change), there are two fallbacks:

- **Screen vision** (`--source vision`): captures the board region and reads
  pieces by image matching. Needs a one-time calibration:
  `python -m chess_auditor.vision --calibrate`.
- **FEN file** (`--source fen --fen-file board.fen`): point it at a file that
  any other tool keeps updated with the current FEN.

---

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| Pill never appears | Script injection not enabled → redo step 3, restart Brave; check script is **Enabled** in Tampermonkey |
| Pill says "server offline" | `run-live.ps1` not running, or you didn't "Always allow" the cross-origin request |
| Pill says "no board found" | chess.com markup changed → in console run `document.querySelector('wc-chess-board').game.getFEN()` and send me the result |
| Overlay blank / frozen | Refresh the OBS Browser source; check `main.err.log` in the project folder |
| "conda env not found" | `conda env create -f environment.yml` |
| Wrong best move / side | Side-to-move came in wrong — usually self-corrects next move; report if persistent |
