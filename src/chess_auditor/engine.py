"""Stockfish wrapper built on python-chess."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import chess
import chess.engine

# On Windows, prevent the console app (Stockfish) from popping up its own
# terminal window when launched from a windowed (no-console) app.
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


@dataclass
class EngineConfig:
    path: str = "stockfish"
    depth: int = 18
    # If set (>0), search for this many milliseconds instead of to a fixed
    # depth. Time-based search gives predictable, low latency — best for live
    # overlay use. Takes precedence over `depth`.
    movetime_ms: int = 0
    threads: int = 2
    hash_mb: int = 256
    multipv: int = 1


@dataclass
class EvalResult:
    best_move: chess.Move | None          # principal best move
    pv: list[chess.Move]                   # full principal variation
    score_cp: int | None                   # eval in centipawns, +ve = side-to-move better
    mate_in: int | None                    # mate distance (signed), if any


class Engine:
    """Thin, reusable Stockfish session."""

    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg
        self._engine = chess.engine.SimpleEngine.popen_uci(cfg.path, **_NO_WINDOW)
        self._engine.configure(
            {"Threads": cfg.threads, "Hash": cfg.hash_mb}
        )

    def analyse(self, board: chess.Board, depth: int | None = None,
                movetime_ms: int | None = None) -> EvalResult:
        # Priority: explicit movetime > explicit depth > configured movetime >
        # configured depth.
        mt = movetime_ms if movetime_ms is not None else self.cfg.movetime_ms
        if depth is not None:
            limit = chess.engine.Limit(depth=depth)
        elif mt and mt > 0:
            limit = chess.engine.Limit(time=mt / 1000.0)
        else:
            limit = chess.engine.Limit(depth=self.cfg.depth)
        info = self._engine.analyse(board, limit, multipv=self.cfg.multipv)
        # multipv returns a list; depth-only returns a dict. Normalize.
        primary = info[0] if isinstance(info, list) else info

        pv = primary.get("pv", [])
        score = primary.get("score")
        score_cp = mate_in = None
        if score is not None:
            pov = score.pov(board.turn)
            if pov.is_mate():
                mate_in = pov.mate()
            else:
                score_cp = pov.score()

        return EvalResult(
            best_move=pv[0] if pv else None,
            pv=list(pv),
            score_cp=score_cp,
            mate_in=mate_in,
        )

    def close(self) -> None:
        try:
            self._engine.quit()
        except chess.engine.EngineError:
            pass

    def __enter__(self) -> "Engine":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
