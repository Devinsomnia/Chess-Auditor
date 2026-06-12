"""Post-game review: scan a game log and highlight the decisive moments.

Reads a JSONL game log written by the live overlay (logs/game-*.jsonl) and
flags, for each move:

  * mate appearing / disappearing  (your main ask),
  * a forced mate that was missed,
  * walking into a forced mate,
  * blunders / mistakes (large eval swings).

Usage:
    python review.py                 # newest game log in ./logs
    python review.py logs/game-*.jsonl
    python review.py --html          # also write an HTML report you can screenshot
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import chess  # noqa: E402
from chess_auditor.gamelog import MATE_BASE, is_mate_cp  # noqa: E402

ROOT = Path(__file__).parent
LOGS = ROOT / "logs"

# eval-swing thresholds (centipawns, from the mover's point of view)
BLUNDER = 300
MISTAKE = 150


def latest_log() -> Path | None:
    files = sorted(LOGS.glob("game-*.jsonl"))
    return files[-1] if files else None


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def move_number(fen: str) -> str:
    parts = fen.split()
    full = parts[5] if len(parts) > 5 else "?"
    return f"{full}." if parts[1] == "w" else f"{full}..."


def played_move(prev_fen: str, next_fen: str) -> str | None:
    """Reconstruct the move played between two positions via placement match."""
    try:
        board = chess.Board(prev_fen)
    except ValueError:
        return None
    target = next_fen.split()[0]
    for mv in board.legal_moves:
        board.push(mv)
        same = board.fen().split()[0] == target
        board.pop()
        if same:
            return board.san(mv)
    return None


def fmt_eval(white_cp: int | None, mate_in: int | None, turn_white: bool) -> str:
    if mate_in is not None:
        # mate_in is from side-to-move POV; show from White POV for consistency
        signed = mate_in if turn_white else -mate_in
        return f"#{signed}" if signed else "#"
    if white_cp is None:
        return "—"
    return f"{white_cp/100:+.2f}"


def mover_cp(white_cp: int | None, mover_white: bool) -> int | None:
    if white_cp is None:
        return None
    return white_cp if mover_white else -white_cp


def review(rows: list[dict]) -> list[dict]:
    events = []
    for i in range(len(rows) - 1):
        cur, nxt = rows[i], rows[i + 1]
        mover_white = cur["turn"] == "w"
        before = mover_cp(cur.get("white_cp"), mover_white)
        after = mover_cp(nxt.get("white_cp"), mover_white)
        if before is None or after is None:
            continue

        delta = after - before  # negative = the mover's position got worse
        before_mate = is_mate_cp(cur.get("white_cp"))
        after_mate = is_mate_cp(nxt.get("white_cp"))

        label = None
        kind = None
        # --- mate transitions (highest priority) ---
        if before_mate and before > 0 and not (after_mate and after > 0):
            label = f"MISSED MATE - had {fmt_eval(cur['white_cp'], cur['mate_in'], mover_white)}"
            kind = "missed_mate"
        elif after_mate and after < 0 and not (before_mate and before < 0):
            label = "ALLOWED FORCED MATE"
            kind = "allowed_mate"
        elif after_mate and after > 0 and not (before_mate and before > 0):
            label = "Mate found"
            kind = "mate_found"
        # --- otherwise large eval swings ---
        elif delta <= -BLUNDER:
            label = f"BLUNDER ({delta/100:+.1f})"
            kind = "blunder"
        elif delta <= -MISTAKE:
            label = f"Mistake ({delta/100:+.1f})"
            kind = "mistake"

        if label:
            events.append({
                "move_no": move_number(cur["fen"]),
                "mover": "White" if mover_white else "Black",
                "played": played_move(cur["fen"], nxt["fen"]) or "?",
                "best": cur.get("best_san") or "?",
                "eval_before": fmt_eval(cur.get("white_cp"), cur.get("mate_in"), mover_white),
                "eval_after": fmt_eval(nxt.get("white_cp"), nxt.get("mate_in"), not mover_white),
                "label": label,
                "kind": kind,
            })
    return events


def print_report(path: Path, rows: list[dict], events: list[dict]) -> None:
    print(f"\nGame log: {path.name}   ({len(rows)} positions)\n")
    if not events:
        print("No mate swings or blunders detected.\n")
        return
    print(f"{'Move':>7}  {'Side':<5}  {'Played':<8}  {'Best':<8}  {'Eval':>14}  Note")
    print("-" * 78)
    for e in events:
        arrow = f"{e['eval_before']} -> {e['eval_after']}"
        flag = "**" if e["kind"] in ("missed_mate", "allowed_mate", "blunder") else "  "
        print(f"{e['move_no']:>7}  {e['mover']:<5}  {e['played']:<8}  "
              f"{e['best']:<8}  {arrow:>14}  {flag}{e['label']}")
    print()
    mates = [e for e in events if e["kind"] in ("missed_mate", "allowed_mate", "mate_found")]
    print(f"Summary: {len(events)} key moments, {len(mates)} mate-related.\n")


def write_html(path: Path, rows: list[dict], events: list[dict]) -> Path:
    color = {"missed_mate": "#e05a5a", "allowed_mate": "#e05a5a", "blunder": "#e07b39",
             "mistake": "#e0c139", "mate_found": "#48e060"}
    out = path.with_suffix(".html")
    cells = "".join(
        f"<tr style='border-left:5px solid {color.get(e['kind'], '#888')}'>"
        f"<td>{e['move_no']}</td><td>{e['mover']}</td><td>{e['played']}</td>"
        f"<td>{e['best']}</td><td>{e['eval_before']} → {e['eval_after']}</td>"
        f"<td>{e['label']}</td></tr>"
        for e in events
    )
    html = f"""<!doctype html><meta charset=utf-8>
<style>body{{font:15px system-ui;background:#16161a;color:#eee;padding:24px}}
h1{{font-size:20px}} table{{border-collapse:collapse;width:100%}}
td,th{{padding:6px 12px;text-align:left}} th{{color:#9aa0a6;border-bottom:1px solid #333}}
tr{{background:#1e1e22}}</style>
<h1>chess-auditor — game review</h1>
<p>{path.name} · {len(rows)} positions · {len(events)} key moments</p>
<table><tr><th>Move</th><th>Side</th><th>Played</th><th>Best</th><th>Eval</th><th>Note</th></tr>
{cells}</table>"""
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="chess-auditor post-game review")
    ap.add_argument("logfile", nargs="?", help="path to a game-*.jsonl (default: newest)")
    ap.add_argument("--html", action="store_true", help="also write an HTML report")
    args = ap.parse_args()

    path = Path(args.logfile) if args.logfile else latest_log()
    if not path or not path.exists():
        print("No game log found. Play a game with run-live.ps1 first "
              "(logs are written to ./logs).")
        return

    rows = load(path)
    events = review(rows)
    print_report(path, rows, events)
    if args.html:
        out = write_html(path, rows, events)
        print(f"HTML report: {out}")


if __name__ == "__main__":
    main()
