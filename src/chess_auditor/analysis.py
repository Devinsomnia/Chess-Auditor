"""Position analysis: best move (green) and danger detection (yellow).

The output is a plain dict ready to be serialized to the overlay.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import chess

from .engine import Engine, EvalResult

PIECE_VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}

ROLE_NAMES = {
    "queen": chess.QUEEN,
    "rook": chess.ROOK,
    "knight": chess.KNIGHT,
    "bishop": chess.BISHOP,
    "king": chess.KING,
    "pawn": chess.PAWN,
}


@dataclass
class Highlight:
    square: int          # 0..63 (a1 = 0)
    color: str           # "green" | "yellow"
    role: str            # "best-from" | "best-to" | "ours" | "enemy"
    reason: str = ""


@dataclass
class AnalysisResult:
    fen: str
    our_color: bool                       # chess.WHITE / chess.BLACK = bottom side
    best_uci: str | None
    best_san: str | None
    pv_san: list[str]
    score_cp: int | None
    mate_in: int | None
    highlights: list[Highlight] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        # Re-express the eval from OUR player's point of view (the side at the
        # bottom of the board), so a positive score / "#N" always means *our*
        # player is winning / has the mate, and a negative one means the
        # opponent does. The engine reports from the side-to-move POV, so we
        # flip when it's the opponent's turn.
        turn_white = self.fen.split()[1] == "w"
        side_is_ours = turn_white == self.our_color
        our_cp = self.score_cp if side_is_ours else _neg(self.score_cp)
        our_mate = self.mate_in if side_is_ours else _neg(self.mate_in)
        return {
            "fen": self.fen,
            "our_color": "white" if self.our_color else "black",
            "best_uci": self.best_uci,
            "best_san": self.best_san,
            "pv_san": self.pv_san,
            "score_cp": self.score_cp,
            "mate_in": self.mate_in,
            "our_cp": our_cp,
            "our_mate": our_mate,
            "highlights": [
                {"square": h.square, "color": h.color, "role": h.role, "reason": h.reason}
                for h in self.highlights
            ],
            "warnings": self.warnings,
        }


def _ray_attacker(board: chess.Board, target: int, by_color: bool,
                  slider_types: set[int]) -> int | None:
    """Find an enemy slider of the given types attacking `target`."""
    for attacker_sq in board.attackers(by_color, target):
        piece = board.piece_at(attacker_sq)
        if piece and piece.piece_type in slider_types:
            return attacker_sq
    return None


def _danger_highlights(board: chess.Board, our_color: bool,
                       watch_roles: list[str],
                       warn_alignment: bool) -> tuple[list[Highlight], list[str]]:
    highlights: list[Highlight] = []
    warnings: list[str] = []
    opp = not our_color

    watch = {ROLE_NAMES[r] for r in watch_roles} | {chess.KING}

    # 1) Attacked / hanging valuable pieces of ours.
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != our_color or piece.piece_type not in watch:
            continue

        attackers = board.attackers(opp, sq)
        if not attackers:
            continue
        defenders = board.attackers(our_color, sq)

        in_danger = False
        reason = ""
        if piece.piece_type == chess.KING:
            in_danger = True
            reason = "king under attack" if board.is_check() else "king square attacked"
        else:
            min_attacker_val = min(
                PIECE_VALUE[board.piece_at(a).piece_type] for a in attackers
            )
            if not defenders:
                in_danger = True
                reason = f"{chess.piece_name(piece.piece_type)} hanging (undefended)"
            elif min_attacker_val < PIECE_VALUE[piece.piece_type]:
                in_danger = True
                reason = (
                    f"{chess.piece_name(piece.piece_type)} attacked by a "
                    f"cheaper piece"
                )

        if in_danger:
            highlights.append(Highlight(sq, "yellow", "ours", reason))
            for a in attackers:
                highlights.append(
                    Highlight(a, "yellow", "enemy",
                              f"attacks our {chess.piece_name(piece.piece_type)}")
                )
            # Always surface in text too, so the cue survives even when the best
            # move (green) happens to occupy the same square.
            warnings.append(f"{chess.square_name(sq)}: {reason}")

    # 2) Absolute pins of our valuable pieces to our king.
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if not piece or piece.color != our_color or piece.piece_type == chess.KING:
            continue
        if piece.piece_type not in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            continue
        if board.is_pinned(our_color, sq):
            highlights.append(
                Highlight(sq, "yellow", "ours",
                          f"{chess.piece_name(piece.piece_type)} pinned to king")
            )
            warnings.append(f"{chess.piece_name(piece.piece_type)} is pinned")

    # 3) Queen <-> king alignment (skewer/pin risk along a line).
    if warn_alignment:
        king_sq = board.king(our_color)
        queens = list(board.pieces(chess.QUEEN, our_color))
        if king_sq is not None:
            for q in queens:
                line = _aligned_line(q, king_sq)
                if line is None:
                    continue
                # Is there an enemy slider that could exploit this line?
                if line == "ortho":
                    sliders = {chess.ROOK, chess.QUEEN}
                else:
                    sliders = {chess.BISHOP, chess.QUEEN}
                # Look both directions along the line for an enemy slider with a
                # clear (or only-queen/king-blocked) path.
                if _line_exploitable(board, q, king_sq, opp, sliders):
                    highlights.append(
                        Highlight(q, "yellow", "ours",
                                  "queen aligned with king (skewer/pin risk)")
                    )
                    highlights.append(
                        Highlight(king_sq, "yellow", "ours",
                                  "king aligned with queen")
                    )
                    warnings.append("Queen and king share an exploitable line")

    return _dedupe(highlights), warnings


def _aligned_line(a: int, b: int) -> str | None:
    """'ortho' if a,b share rank/file; 'diag' if same diagonal; else None."""
    fa, ra = chess.square_file(a), chess.square_rank(a)
    fb, rb = chess.square_file(b), chess.square_rank(b)
    if fa == fb or ra == rb:
        return "ortho"
    if abs(fa - fb) == abs(ra - rb):
        return "diag"
    return None


def _line_exploitable(board: chess.Board, q: int, k: int,
                      opp: bool, sliders: set[int]) -> bool:
    """True if an enemy slider sits on the q-k line (either side) with at most
    our own queen/king between it and the king — i.e. a real pin/skewer motif."""
    fq, rq = chess.square_file(q), chess.square_rank(q)
    fk, rk = chess.square_file(k), chess.square_rank(k)
    df = _sign(fk - fq)
    dr = _sign(rk - rq)
    # Scan outward from the king, away from the queen, looking for an enemy slider.
    for direction in ((df, dr), (-df, -dr)):
        f, r = fk + direction[0], rk + direction[1]
        while 0 <= f < 8 and 0 <= r < 8:
            sq = chess.square(f, r)
            piece = board.piece_at(sq)
            if piece is not None:
                if piece.color == opp and piece.piece_type in sliders:
                    return True
                break  # any other piece blocks the line
            f += direction[0]
            r += direction[1]
    return False


def _sign(n: int) -> int:
    return (n > 0) - (n < 0)


def _neg(v: int | None) -> int | None:
    return None if v is None else -v


def _dedupe(highlights: list[Highlight]) -> list[Highlight]:
    """Keep one highlight per square; green wins over yellow, ours over enemy."""
    priority = {"best-from": 4, "best-to": 4, "ours": 2, "enemy": 1}
    best: dict[int, Highlight] = {}
    for h in highlights:
        cur = best.get(h.square)
        if cur is None or priority[h.role] > priority[cur.role]:
            best[h.square] = h
    return list(best.values())


def analyze(board: chess.Board, engine: Engine, our_color: bool,
            depth: int | None = None,
            movetime_ms: int | None = None,
            watch_roles: list[str] | None = None,
            warn_alignment: bool = True) -> AnalysisResult:
    watch_roles = watch_roles or ["queen", "rook", "knight", "bishop"]
    ev: EvalResult = engine.analyse(board, depth=depth, movetime_ms=movetime_ms)

    best_uci = best_san = None
    pv_san: list[str] = []
    if ev.best_move is not None:
        best_uci = ev.best_move.uci()
        best_san = board.san(ev.best_move)
        pv_san = _pv_to_san(board, ev.pv)

    highlights, warnings = _danger_highlights(
        board, our_color, watch_roles, warn_alignment
    )

    # Best move squares (green) added last so dedupe lets them win.
    if ev.best_move is not None:
        highlights.append(Highlight(ev.best_move.from_square, "green", "best-from",
                                    "best move"))
        highlights.append(Highlight(ev.best_move.to_square, "green", "best-to",
                                    "best move"))
        highlights = _dedupe(highlights)

    return AnalysisResult(
        fen=board.fen(),
        our_color=our_color,
        best_uci=best_uci,
        best_san=best_san,
        pv_san=pv_san,
        score_cp=ev.score_cp,
        mate_in=ev.mate_in,
        highlights=highlights,
        warnings=warnings,
    )


def _pv_to_san(board: chess.Board, pv: list[chess.Move], limit: int = 6) -> list[str]:
    out: list[str] = []
    tmp = board.copy()
    for mv in pv[:limit]:
        try:
            out.append(tmp.san(mv))
            tmp.push(mv)
        except (AssertionError, ValueError):
            break
    return out
