# chess-auditor — Project Overview

A real-time **chess broadcast analysis overlay** for streaming. It reads the
live board, runs Stockfish, and renders an analysis board for your viewers with
the best move, danger highlights, forced-mate alerts, and an eval bar — plus a
post-game review tool. Built to run under a conda environment on Windows with
OBS.

> **Intended use — important.** This is a *commentary / viewer* overlay: the
> analysis is for your audience and casters, displayed transparently. It is not
> designed as a private, in-ear feed to the player during their own competitive
> game (that would violate chess.com / Lichess fair-play rules). The overlay
> output and the player's screen are kept separate by design.

---

## What it does (features)

- **Best move (green):** the engine's top move shown as a green arrow plus
  highlighted from/to squares, at a configurable search budget.
- **Danger (yellow):** highlights your endangered pieces **and** the enemy piece
  attacking them, covering:
  - hanging / under-attacked queen, rook, knight, bishop, king,
  - a piece **pinned to your king**,
  - your **queen and king sharing a line** that an enemy slider can exploit
    (skewer/pin motif),
  - each danger also appears as a text warning so it survives even when the
    green best-move arrow lands on the same square.
- **Forced-mate alerts:** a big pulsing banner — **green "MATE IN N — YOU"** when
  you have the mate, **red "MATE THREAT IN N — OPPONENT"** when the opponent does.
- **Eval bar + score** from **your player's** point of view (positive = you're
  better), so it's not tied to white/black.
- **Always-bottom orientation:** your player renders at the bottom of the board
  regardless of their color.
- **Near real-time:** ~180 ms end-to-end per move (150 ms engine + ~30 ms
  plumbing), using a time-budgeted search instead of fixed depth. The pipeline
  is push-driven end to end: the analysis loop wakes on the incoming position
  and the overlay long-polls `/state.json`, so there is no polling lag.
- **Post-game review:** scans the game log and flags missed mates, allowed
  mates, and blunders, with the played move vs. the best move and the eval swing.
- **Game logging with rotation:** each game saved as JSONL; only the last 10
  kept.

---

## How it fits together (data flow)

```
 chess.com board (Brave)
        │   Tampermonkey userscript reads the position (chess.com game API,
        │   DOM scrape fallback) and POSTs FEN + your color
        ▼
 POST /fen  ──►  OverlayServer (local HTTP, 127.0.0.1:8765)
        │                     stores the latest raw position
        ▼
 main.py loop  ── reads raw position ──►  Engine (Stockfish)  ──►  analysis
        │                                                            │
        │   publishes analyzed state (best move, highlights,         │
        │   our-POV eval, mate, warnings)  ◄─────────────────────────┘
        ▼
 GET /state.json  ◄── long-polled (instant updates) ──  overlay/index.html  (OBS Browser source)
        │
        └── also appended to logs/game-*.jsonl  ──►  review.py (post-game)
```

---

## Components

| File | Role |
|------|------|
| [src/chess_auditor/main.py](src/chess_auditor/main.py) | Live loop: pull position → analyze → publish → log. CLI flags for source/color/movetime. Warms up the engine on start. |
| [src/chess_auditor/engine.py](src/chess_auditor/engine.py) | Stockfish wrapper (python-chess). Supports a **time budget** (`movetime_ms`) or fixed depth; returns best move, PV, score, mate distance. |
| [src/chess_auditor/analysis.py](src/chess_auditor/analysis.py) | The brains: best move (green) + danger detection (yellow) + queen/king alignment + pins. Normalizes eval/mate to **your player's POV**. |
| [src/chess_auditor/overlay_server.py](src/chess_auditor/overlay_server.py) | Tiny stdlib HTTP server. Serves the overlay, exposes `GET /state.json`, accepts `POST /fen` (with CORS) from the userscript. |
| [src/chess_auditor/overlay/index.html](src/chess_auditor/overlay/index.html) | The rendered analysis board (self-drawn from FEN), highlights, arrow, eval bar, mate banner. Polls `/state.json`. |
| [src/chess_auditor/vision.py](src/chess_auditor/vision.py) | Board sources: `PostSource` is in main; this provides the **FEN-file** source and an optional **screen-vision** (OpenCV template-match) source with calibration. |
| [src/chess_auditor/gamelog.py](src/chess_auditor/gamelog.py) | Per-move JSONL game logging, white-POV normalization helpers, and 10-game rotation. |
| [browser/chesscom-overlay.user.js](browser/chesscom-overlay.user.js) | Tampermonkey userscript that reads the chess.com board and pushes positions to the server. |
| [review.py](review.py) | Post-game review CLI: reads a game log, flags mate swings and blunders, optional HTML report. |
| [demo.py](demo.py) | Standalone demo that cycles sample positions (no browser/game needed). |
| [app.py](app.py) | Desktop launcher: starts the backend and shows the overlay in a frameless, auto-sized webview window (optionally always-on-top via `app.always_on_top`). Packaged into `ChessAuditor.exe`. |
| `build-exe.ps1` | Builds `dist\ChessAuditor.exe` with PyInstaller (one-click app). |
| [config.yaml](config.yaml) | Engine path, search budget, threads, server port, log retention, default color. |
| [environment.yml](environment.yml) | Conda environment definition (`chessauditor`). |
| `run-live.ps1` / `run-demo.ps1` / `stop.ps1` | Launch/stop helpers that use the conda env. |

---

## Key design decisions

- **Self-rendered analysis board, not pixel overlay.** Rather than trying to
  draw boxes onto the live video (which requires exact screen-coordinate
  alignment), the overlay draws its *own* board from the FEN and highlights
  squares there. It's always aligned and looks like a broadcast analysis panel.
- **Read the position, don't screen-scrape pixels (when possible).** The
  userscript reads chess.com's own `game.getFEN()` API for an exact FEN
  (including side-to-move and castling), falling back to DOM/piece-class scraping,
  and only then to OpenCV screen vision. More reliable, less fragile.
- **Time-budget search over fixed depth.** Gives predictable, low latency
  (~150 ms/move) regardless of position complexity — important for live use.
- **Everything from "your player" POV.** Eval, mate sign, and board orientation
  are all expressed relative to the player you're covering, so on-stream readouts
  are unambiguous.
- **No heavy web framework.** The server is Python stdlib `http.server`; the
  overlay is a single static HTML file. Zero extra runtime dependencies for the
  serving layer; trivial to point OBS at.

---

## What was built / changed (history)

1. Initial project: engine wrapper, analysis (best move + danger), overlay
   server + HTML, FEN/vision sources, demo, config.
2. Installed and wired up the toolchain (Python, Stockfish), verified the
   analysis pipeline (best move, mate, hanging pieces, pins, skewer alignment).
3. Added the **live capture path**: `POST /fen` endpoint + `PostSource` + the
   Tampermonkey userscript (game-API read with DOM fallback).
4. **Latency work**: switched to a time-budget search, more engine threads,
   tighter poll intervals, engine warm-up → ~300 ms/move. Diagnosed a
   `localhost`-IPv6 red herring in benchmarking.
5. **Game logging + review tool**: structured JSONL logs and `review.py` to flag
   missed/allowed mates and blunders, with HTML report output.
6. **Log rotation** (keep last 10) and **your-player-POV eval/mate** with a
   prominent mate banner.
7. **Conda**: created the `chessauditor` environment, `environment.yml`, and
   conda-aware launch scripts; documented setup in [HOWTO.md](HOWTO.md).
8. **Resilience**: skip terminal/illegal positions and auto-restart the engine
   so a crash (e.g. a checkmate position) can't take the overlay offline.
9. **Desktop app**: `app.py` + PyInstaller build (`ChessAuditor.exe`) — a
   frameless, always-on-top, content-sized webview window. Bundled conda's
   OpenSSL DLLs so the frozen exe imports `ssl`/`pywebview` correctly.

---

## Known limitations / next steps

- The userscript depends on chess.com's page structure; a site update may
  require selector tweaks (the game-API path is the most stable).
- Screen-vision source needs a one-time calibration and piece templates per
  board theme.
- The review report lists evals from White's POV (with each move labeled by the
  side that played it); a your-player-POV review mode could be added.
- Castling/en-passant in the FEN are approximated when read from pixels (not
  from the game API), which can slightly affect analysis in rare positions.
