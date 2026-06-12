"""Structured per-move game logging for post-game review.

Each analyzed position is appended as one JSON line (JSONL) to a per-session
file under ``logs/``. This is what ``review.py`` reads to flag mate swings and
blunders after the game.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

# Centipawn magnitude used to represent a forced mate, so mates and normal
# evals live on one comparable scale. Closer mates score higher.
MATE_BASE = 100_000


def to_white_cp(score_cp: int | None, mate_in: int | None, turn_white: bool) -> int | None:
    """Normalize a side-to-move eval to a White-positive centipawn scale.

    Mates become large signed values (closer mate = larger magnitude) so a
    swing into or out of mate shows up as a huge delta.
    """
    if mate_in is not None:
        mag = MATE_BASE - min(abs(mate_in), 1000)
        signed = mag if mate_in > 0 else -mag
        return signed if turn_white else -signed
    if score_cp is None:
        return None
    return score_cp if turn_white else -score_cp


def is_mate_cp(white_cp: int | None) -> bool:
    return white_cp is not None and abs(white_cp) >= MATE_BASE - 1000


class GameLogger:
    def __init__(self, logs_dir: Path, keep: int = 10):
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = logs_dir / f"game-{stamp}.jsonl"
        self._ply = 0
        self._fh = self.path.open("a", encoding="utf-8")
        self._prune(logs_dir, keep)

    @staticmethod
    def _prune(logs_dir: Path, keep: int) -> None:
        """Keep only the `keep` most recent game logs (and their HTML reports)."""
        if keep <= 0:
            return
        logs = sorted(logs_dir.glob("game-*.jsonl"))  # oldest first, newest last
        for old in logs[:-keep]:
            for f in (old, old.with_suffix(".html")):
                try:
                    f.unlink()
                except OSError:
                    pass

    def log(self, result) -> None:
        """Append one analyzed position. `result` is an AnalysisResult."""
        self._ply += 1
        board_turn_white = result.fen.split()[1] == "w"
        white_cp = to_white_cp(result.score_cp, result.mate_in, board_turn_white)
        rec = {
            "ply": self._ply,
            "ts": round(time.time(), 3),
            "fen": result.fen,
            "turn": "w" if board_turn_white else "b",
            "our_color": "white" if result.our_color else "black",
            "best_uci": result.best_uci,
            "best_san": result.best_san,
            "score_cp": result.score_cp,
            "mate_in": result.mate_in,
            "white_cp": white_cp,
            "warnings": result.warnings,
        }
        self._fh.write(json.dumps(rec) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass
