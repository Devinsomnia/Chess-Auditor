"""Standalone demo: run a sequence of positions through the full pipeline.

Shows the overlay working end-to-end (best move in green, danger in yellow,
player oriented at the bottom) without any camera or vision calibration.

Requires Stockfish installed (see README). Run:

    python demo.py

then open http://localhost:8765/  (or add it as an OBS Browser source).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent / "src"))

import chess  # noqa: E402
import yaml  # noqa: E402

from chess_auditor.analysis import analyze  # noqa: E402
from chess_auditor.engine import Engine, EngineConfig  # noqa: E402
from chess_auditor.overlay_server import OverlayServer  # noqa: E402


def _engine_cfg() -> EngineConfig:
    """Read engine settings from config.yaml so the demo matches live setup."""
    cfg_path = Path(__file__).parent / "config.yaml"
    e = {}
    if cfg_path.exists():
        e = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get("engine", {})
    return EngineConfig(
        path=e.get("path", "stockfish"),
        depth=e.get("depth", 16),
        threads=e.get("threads", 2),
        hash_mb=e.get("hash_mb", 256),
    )

# (FEN, color-at-bottom) — a mix that triggers green best move and yellow danger.
POSITIONS = [
    # Italian game, quiet — clean best move.
    ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", "black"),
    # White queen on d5 attacked / loose — danger highlight for the side to move.
    ("rnb1kbnr/ppp2ppp/8/3qp3/8/2N5/PPPP1PPP/R1BQKBNR w KQkq - 0 4", "white"),
    # Queen and king on the same file with an enemy rook lurking — alignment warn.
    ("4r1k1/5ppp/8/8/8/8/4Q1PP/6K1 w - - 0 1", "white"),
    # Tactic: white to move, mating/winning shot — strong green best move.
    ("6k1/5ppp/8/8/8/8/5PPP/R3R1K1 w - - 0 1", "white"),
]


def main() -> None:
    server = OverlayServer()
    server.start()
    print(f"Overlay at {server.url}  — open it in a browser or OBS Browser source.")

    try:
        engine = Engine(_engine_cfg())
    except FileNotFoundError:
        print("ERROR: Stockfish not found. Install it and put stockfish.exe on PATH")
        print("       or set engine.path in config.yaml. See README.")
        server.stop()
        return

    try:
        i = 0
        while True:
            fen, color = POSITIONS[i % len(POSITIONS)]
            board = chess.Board(fen)
            our = chess.WHITE if color == "white" else chess.BLACK
            result = analyze(board, engine, our, depth=16)
            server.publish(result.to_dict())
            print(f"[{i+1}] best={result.best_san}  "
                  f"eval_cp={result.score_cp}  warnings={result.warnings}")
            i += 1
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        engine.close()
        server.stop()


if __name__ == "__main__":
    main()
