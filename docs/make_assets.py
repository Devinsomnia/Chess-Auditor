"""Generate the README assets in docs/img: per-move overlay screenshots of a
full game (Morphy's Opera Game), three feature stills, a desktop-app window
grab, and the animated gameplay GIF.

Usage (from the project root, with the app running on :8765):
    pip install pillow          # one-time, not a project dependency
    python app.py               # in another terminal (or the exe)
    python docs/make_assets.py
"""
import ctypes
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, "src")
import chess
from PIL import Image, ImageGrab

BASE = "http://127.0.0.1:8765"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
IMG = Path("docs/img")
FRAMES = IMG / "_frames"
FRAMES.mkdir(parents=True, exist_ok=True)

# Morphy vs Duke Karl / Count Isouard, Paris 1858 ("the Opera Game").
OPERA = ("e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 Qb3 Qe7 Nc3 c6 "
         "Bg5 b5 Nxb5 cxb5 Bxb5+ Nbd7 O-O-O Rd8 Rxd7 Rxd7 Rd1 Qe6 Bxd7+ Nxd7 "
         "Qb8+ Nxb8 Rd8#").split()


def get_state(since=None, timeout=30):
    url = f"{BASE}/state.json" + (f"?v={since}" if since is not None else "")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def post_fen(fen, color="white"):
    req = urllib.request.Request(
        BASE + "/fen",
        data=json.dumps({"fen": fen, "color": color}).encode(),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5)


CROP = (0, 0, 915, 605)  # trim the empty page area right/below the content


def shoot(path: Path, width=1280, height=720):
    """Headless-browser screenshot of the overlay's current state."""
    subprocess.run([
        EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--default-background-color=16161AFF",   # match the app's dark theme
        f"--window-size={width},{height}", "--virtual-time-budget=2500",
        f"--screenshot={path.resolve()}", BASE + "/?once=1",
    ], capture_output=True, timeout=60)
    if not path.exists():
        raise RuntimeError(f"screenshot failed: {path}")
    Image.open(path).crop(CROP).save(path)


def grab_app_window(path: Path):
    """Screenshot the desktop app widget itself."""
    u32 = ctypes.windll.user32
    u32.SetProcessDPIAware()
    hwnd = u32.FindWindowW(None, "Chess Auditor")
    if not hwnd:
        print("  ! app window not found, skipping app screenshot")
        return False
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    rect = ctypes.wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))  # 9 = extended frame bounds
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
    img.save(path)
    return True


def main():
    import ctypes.wintypes  # noqa: F401  (used in grab_app_window)
    board = chess.Board()
    v = get_state()["v"]
    stills = {}  # move index -> filename for the feature stills

    print(f"Playing the Opera Game ({len(OPERA)} half-moves)...")
    frames = []
    for i, san in enumerate(OPERA):
        board.push_san(san)
        post_fen(board.fen(), "white")
        st = get_state(since=v, timeout=30)
        v = st["v"]
        frame = FRAMES / f"frame_{i:02d}.png"
        shoot(frame)
        frames.append(frame)
        note = ""
        if st.get("our_mate"):
            note = f"MATE IN {st['our_mate']}"
        elif st.get("warnings"):
            note = "; ".join(st["warnings"])[:60]
        print(f"  {i+1:2}. {san:7} best={st.get('best_san') or '--':8} {note}")

        # Feature stills at the good moments:
        if san == "Bxf3":          # white queen attacked -> yellow danger
            stills[i] = "overlay-danger.png"
        elif san == "Nxb5":        # mid-game: clean best-move arrow + eval bar
            stills[i] = "overlay-best-move.png"
        elif san == "Nxb8":        # white to move, mate in 1 -> green banner
            stills[i] = "overlay-mate.png"
        if i in stills:
            (IMG / stills[i]).write_bytes(frame.read_bytes())
            print(f"      -> still: {stills[i]}")

    # Hold the final checkmate frame a bit longer in the GIF.
    print("Assembling gameplay GIF...")
    imgs = [Image.open(f) for f in frames]
    w, h = imgs[0].size
    small = [im.resize((732, int(h * 732 / w)))
               .convert("P", palette=Image.ADAPTIVE, colors=128)
             for im in imgs]
    durations = [850] * len(small)
    durations[-1] = 4000
    small[0].save(IMG / "gameplay.gif", save_all=True, append_images=small[1:],
                  duration=durations, loop=0, optimize=True)
    size_mb = (IMG / "gameplay.gif").stat().st_size / 1e6
    print(f"  gameplay.gif: {len(small)} frames, {size_mb:.1f} MB")

    print("Grabbing the desktop app window...")
    grab_app_window(IMG / "app-desktop.png")

    print("DONE")


if __name__ == "__main__":
    main()
