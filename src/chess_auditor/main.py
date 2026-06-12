"""Live loop: capture position -> analyze -> publish to overlay."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import chess
import chess.engine
import yaml


def app_base_dir() -> Path:
    """Folder for user-editable config and logs.

    When packaged as an .exe (PyInstaller) this is the folder containing the
    exe; otherwise it's the project root. Keeps config.yaml/logs next to the
    app instead of inside a temp extraction dir.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]

from .analysis import analyze
from .engine import Engine, EngineConfig
from .gamelog import GameLogger
from .overlay_server import OverlayServer
from .vision import FenFileSource, ScreenVisionSource


def load_config(path: str | None) -> dict:
    p = Path(path) if path else app_base_dir() / "config.yaml"
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def terminal_state(board: chess.Board, our: bool) -> dict:
    """Overlay state for a finished game (checkmate/stalemate/draw)."""
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        msg = "Game over"
    else:
        term = outcome.termination.name.replace("_", " ").title()
        if outcome.winner is None:
            msg = f"Draw - {term}"
        else:
            who = "You win" if outcome.winner == bool(our) else "Opponent wins"
            msg = f"{who} - {term}"
    return {
        "fen": board.fen(),
        "our_color": "white" if our else "black",
        "best_uci": None, "best_san": None, "pv_san": [],
        "score_cp": None, "mate_in": None, "our_cp": None, "our_mate": None,
        "highlights": [], "warnings": [msg],
    }


def resolve_color(name: str, board: chess.Board) -> bool:
    if name == "white":
        return chess.WHITE
    if name == "black":
        return chess.BLACK
    return board.turn  # auto: side to move renders at bottom


class PostSource:
    """Reads the latest position pushed to the server's POST /fen endpoint."""

    def __init__(self, server):
        self._server = server

    def read(self):
        raw = self._server.get_raw()
        if not raw:
            return None
        color = raw.get("color")
        our = None
        if color == "white":
            our = chess.WHITE
        elif color == "black":
            our = chess.BLACK
        return raw["fen"], our

    def close(self):
        pass


def build_source(args, cfg, server):
    if args.source == "post":
        return PostSource(server)
    if args.source == "vision":
        color = None if args.color == "auto" else (
            chess.WHITE if args.color == "white" else chess.BLACK)
        return ScreenVisionSource(our_color=color)
    return FenFileSource(
        path=args.fen_file,
        our_color=None if args.color == "auto" else (
            chess.WHITE if args.color == "white" else chess.BLACK),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="chess-auditor live overlay")
    ap.add_argument("--config", default=None)
    ap.add_argument("--source", choices=["fen", "vision", "post"], default="fen")
    ap.add_argument("--fen-file", default="board.fen")
    ap.add_argument("--color", choices=["white", "black", "auto"], default=None)
    ap.add_argument("--depth", type=int, default=None,
                    help="force fixed-depth search (overrides movetime)")
    ap.add_argument("--movetime", type=int, default=None,
                    help="search time per position in ms (lower = snappier)")
    ap.add_argument("--interval", type=float, default=0.05,
                    help="seconds between polls of the board source")
    args = ap.parse_args()

    cfg = load_config(args.config)
    ecfg = cfg.get("engine", {})
    scfg = cfg.get("server", {})
    acfg = cfg.get("analysis", {})
    dcfg = cfg.get("display", {})

    if args.color is None:
        args.color = dcfg.get("our_color", "white")

    server = OverlayServer(scfg.get("host", "127.0.0.1"), scfg.get("port", 8765))
    server.start()
    print(f"Overlay served at {server.url}  (add as OBS Browser source)")

    def make_engine() -> Engine:
        return Engine(EngineConfig(
            path=ecfg.get("path", "stockfish"),
            depth=ecfg.get("depth", 18),
            movetime_ms=ecfg.get("movetime_ms", 0),
            threads=ecfg.get("threads", 2),
            hash_mb=ecfg.get("hash_mb", 256),
            multipv=ecfg.get("multipv", 1),
        ))

    engine = make_engine()
    source = build_source(args, cfg, server)

    logs_dir = app_base_dir() / "logs"
    glog = GameLogger(logs_dir, keep=cfg.get("logging", {}).get("max_games", 10))
    print(f"Game log: {glog.path}")

    # Per-call search budget: --depth forces fixed depth, --movetime forces a
    # time budget, otherwise fall back to whatever config.yaml specifies.
    call_depth = args.depth
    call_movetime = args.movetime
    budget = (f"depth {call_depth}" if call_depth else
              f"{call_movetime or ecfg.get('movetime_ms', 0)} ms")
    print(f"Search budget: {budget}, threads={ecfg.get('threads', 2)}")

    # Warm up: force Stockfish to load its NNUE network now so the first real
    # move of the game isn't delayed by ~2-3s of cold start.
    print("Warming up engine…", end="", flush=True)
    engine.analyse(chess.Board(), movetime_ms=200)
    print(" ready.")

    # PostSource is push-driven: block on the server's "new position" event so
    # analysis starts the instant a FEN arrives instead of up to --interval
    # later. File/vision sources have nothing to signal, so they keep polling.
    if isinstance(source, PostSource):
        def idle() -> None:
            server.wait_for_raw(timeout=0.25)
    else:
        def idle() -> None:
            time.sleep(args.interval)

    last_key = None
    print("Running. Ctrl+C to stop.")
    try:
        while True:
            got = source.read()
            if got is None:
                idle()
                continue
            fen, our_color = got
            board = chess.Board(fen)
            our = our_color if our_color is not None else resolve_color(args.color, board)
            key = (fen, our)
            if key == last_key:
                idle()
                continue
            last_key = key

            # Don't hand terminal or illegal positions to the engine — game-over
            # positions can crash some Stockfish builds, and the userscript can
            # briefly report a malformed board mid-animation.
            if board.is_game_over():
                server.publish(terminal_state(board, our))
                print(f"  game over: {board.result()}")
                idle()
                continue
            if not board.is_valid():
                idle()
                continue

            _t = time.perf_counter()
            try:
                result = analyze(
                    board, engine, our,
                    depth=call_depth,
                    movetime_ms=call_movetime,
                    watch_roles=acfg.get("watch_roles",
                                         ["queen", "rook", "knight", "bishop"]),
                    warn_alignment=acfg.get("warn_queen_king_alignment", True),
                )
            except chess.engine.EngineError as exc:
                # Engine died (crash, terminated pipe, etc.). Restart and skip
                # this position so the overlay stays online.
                print(f"  engine error: {exc} — restarting engine…")
                last_key = None
                try:
                    engine.close()
                except Exception:
                    pass
                try:
                    engine = make_engine()
                    engine.analyse(chess.Board(), movetime_ms=200)  # warm up
                    print("  engine restarted.")
                except Exception as e2:
                    print(f"  engine restart failed: {e2}; retrying shortly.")
                    time.sleep(1.0)
                continue
            elapsed = (time.perf_counter() - _t) * 1000
            server.publish(result.to_dict())
            glog.log(result)
            tag = result.best_san or "--"
            print(f"  {fen.split()[0][:20]}…  best={tag}  "
                  f"warnings={len(result.warnings)}  analyze={elapsed:.0f}ms")
            idle()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        glog.close()
        engine.close()
        server.stop()


if __name__ == "__main__":
    main()
