"""Board sources: where the current position comes from.

Two sources are provided:

* ``FenFileSource`` — reads a FEN from a text file. Fully working, no extra deps.
  Point anything that knows the position at this file (a PGN relay script, a
  second-screen analysis board export, manual entry, etc.).

* ``ScreenVisionSource`` — captures a screen region with ``mss`` and recognizes
  pieces by OpenCV template matching. This needs a one-time calibration to
  record the board's pixel rectangle and a set of piece templates for the board
  theme you stream (chess.com pieces are consistent sprites, so template
  matching is reliable once calibrated). See ``calibrate()``.

Both return a tuple ``(fen, our_color)`` or ``None`` when no position is ready.
``our_color`` is ``chess.WHITE``/``chess.BLACK`` for the side to render at the
bottom, or ``None`` to let the caller decide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chess


class BoardSource:
    def read(self) -> tuple[str, bool | None] | None:
        raise NotImplementedError

    def close(self) -> None:
        pass


@dataclass
class FenFileSource(BoardSource):
    path: str
    our_color: bool | None = None

    def read(self) -> tuple[str, bool | None] | None:
        p = Path(self.path)
        if not p.exists():
            return None
        text = p.read_text(encoding="utf-8").strip()
        if not text:
            return None
        try:
            chess.Board(text)  # validate
        except ValueError:
            return None
        return text, self.our_color


# --------------------------------------------------------------------------
# Screen capture source (optional; needs mss + opencv-python + numpy).
# --------------------------------------------------------------------------

_CALIB_PATH = Path(__file__).parent / "vision_calibration.json"


@dataclass
class ScreenVisionSource(BoardSource):
    """Reads the board out of a screen region via template matching.

    Calibration data (board rectangle + piece template directory) is stored in
    ``vision_calibration.json`` next to this module. Run ``calibrate()`` once per
    board theme / layout.
    """

    our_color: bool | None = None
    _calib: dict | None = None
    _templates: dict | None = None
    _sct = None
    _last_fen: str | None = None

    def __post_init__(self) -> None:
        if not _CALIB_PATH.exists():
            raise RuntimeError(
                "No vision calibration found. Run "
                "`python -m chess_auditor.vision --calibrate` first."
            )
        self._calib = json.loads(_CALIB_PATH.read_text(encoding="utf-8"))
        self._load_deps()
        self._templates = self._load_templates()

    def _load_deps(self):
        global mss, cv2, np
        import cv2  # type: ignore
        import mss  # type: ignore
        import numpy as np  # type: ignore
        self._sct = mss.mss()

    def _load_templates(self) -> dict:
        import cv2  # type: ignore
        tdir = Path(self._calib["templates_dir"])
        templates = {}
        # filenames: wP, wN, wB, wR, wQ, wK, bP, ... .png
        for f in tdir.glob("*.png"):
            img = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                templates[f.stem] = img
        if not templates:
            raise RuntimeError(f"No piece templates found in {tdir}")
        return templates

    def _grab(self):
        import numpy as np  # type: ignore
        import cv2  # type: ignore
        r = self._calib["rect"]  # {left, top, width, height}
        shot = self._sct.grab(r)
        img = np.asarray(shot)[:, :, :3]  # BGRA -> BGR
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def read(self) -> tuple[str, bool | None] | None:
        import cv2  # type: ignore
        board_img = self._grab()
        h, w = board_img.shape
        cell_h, cell_w = h / 8, w / 8

        # bottom-side color decides FEN orientation; from calibration.
        bottom_white = self._calib.get("bottom_is_white", True)
        board = chess.Board(None)  # empty

        for screen_row in range(8):
            for screen_col in range(8):
                y0, x0 = int(screen_row * cell_h), int(screen_col * cell_w)
                cell = board_img[y0:y0 + int(cell_h), x0:x0 + int(cell_w)]
                label = self._classify(cell)
                if label is None:
                    continue
                file, rank = self._screen_to_square(screen_col, screen_row, bottom_white)
                piece = chess.Piece(
                    {"P": chess.PAWN, "N": chess.KNIGHT, "B": chess.BISHOP,
                     "R": chess.ROOK, "Q": chess.QUEEN, "K": chess.KING}[label[1]],
                    chess.WHITE if label[0] == "w" else chess.BLACK,
                )
                board.set_piece_at(chess.square(file, rank), piece)

        # We cannot recover castling/ep/side-to-move from pixels alone; assume the
        # side at the bottom is to move (typical when it's our turn). Adjust if you
        # feed turn info from another channel.
        board.turn = chess.WHITE if bottom_white else chess.BLACK
        fen = board.fen()
        if board.king(chess.WHITE) is None or board.king(chess.BLACK) is None:
            return None  # bad read, skip frame
        self._last_fen = fen
        our = self.our_color
        if our is None:
            our = chess.WHITE if bottom_white else chess.BLACK
        return fen, our

    def _classify(self, cell) -> str | None:
        import cv2  # type: ignore
        best_label, best_score = None, 0.0
        for label, tmpl in self._templates.items():
            th, tw = tmpl.shape
            resized = cv2.resize(cell, (tw, th))
            res = cv2.matchTemplate(resized, tmpl, cv2.TM_CCOEFF_NORMED)
            score = float(res.max())
            if score > best_score:
                best_score, best_label = score, label
        threshold = self._calib.get("match_threshold", 0.55)
        return best_label if best_score >= threshold else None

    @staticmethod
    def _screen_to_square(col: int, row: int, bottom_white: bool) -> tuple[int, int]:
        if bottom_white:
            return col, 7 - row
        return 7 - col, row


def calibrate() -> None:
    """Interactive helper: capture the board rectangle and save calibration.

    Capturing piece templates is a manual step: screenshot each piece on an
    empty square in your theme, crop tightly, and save as wP.png, bK.png, etc.
    into a folder, then set that folder as templates_dir below.
    """
    print("Vision calibration")
    print("------------------")
    print("1) Take a screenshot and read off the board's pixel rectangle.")
    left = int(input("  board left  (px): "))
    top = int(input("  board top   (px): "))
    width = int(input("  board width (px): "))
    height = int(input("  board height(px): "))
    tdir = input("  templates dir (folder of wP.png ... bK.png): ").strip()
    bottom = input("  is WHITE at the bottom? [Y/n]: ").strip().lower() != "n"
    calib = {
        "rect": {"left": left, "top": top, "width": width, "height": height},
        "templates_dir": tdir,
        "bottom_is_white": bottom,
        "match_threshold": 0.55,
    }
    _CALIB_PATH.write_text(json.dumps(calib, indent=2), encoding="utf-8")
    print(f"Saved calibration to {_CALIB_PATH}")


if __name__ == "__main__":
    import sys
    if "--calibrate" in sys.argv:
        calibrate()
    else:
        print("Usage: python -m chess_auditor.vision --calibrate")
