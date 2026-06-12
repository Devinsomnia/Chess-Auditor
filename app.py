"""Desktop launcher for chess-auditor.

Starts the analysis backend (overlay server + engine loop) and shows the overlay
in a frameless webview window, auto-sized to the content so there is no empty
white margin. Set app.always_on_top in config.yaml to keep it above other windows.

Run as a script:   python app.py
Or as the built:   ChessAuditor.exe
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

_CREATE_NO_WINDOW = 0x08000000  # don't flash a console for helper processes

# When run as a plain script, make ./src importable. (When frozen, chess_auditor
# is bundled into the exe and already importable.)
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _base_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else ROOT


def _setup_logging() -> None:
    # In a windowed (--noconsole) exe, sys.stdout/stderr are None, so the
    # backend's print() calls would crash. Redirect both to a log file next to
    # the app; this also captures any startup traceback for debugging.
    try:
        f = open(_base_dir() / "app.log", "w", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass

import webview  # noqa: E402
from chess_auditor import main as backend  # noqa: E402

HOST = "127.0.0.1"


def start_backend() -> None:
    # Drive the same live loop run-live.ps1 uses.
    sys.argv = ["chess-auditor", "--source", "post", "--color", "auto"]
    try:
        backend.main()
    except SystemExit:
        pass
    except Exception:  # keep the window up even if the loop hiccups
        traceback.print_exc()


class Api:
    """Bridge exposed to the overlay's JS for the in-window controls."""

    def __init__(self, engine_path: str | None):
        self._engine_path = engine_path
        # Underscore-prefixed on purpose: pywebview serializes every *public*
        # attribute of the js_api object for the JS bridge, and walking the
        # native window object recurses forever (AccessibilityObject.Bounds.
        # Empty.Empty…) — that recursion froze the packaged exe.
        self._window = None  # set after the window is created

    def quit(self) -> None:
        """Terminate the app (and its Stockfish engine)."""
        self._kill_engine()
        try:
            if self._window is not None:
                self._window.destroy()
        except Exception:
            pass
        os._exit(0)

    def set_mode(self, mode: str) -> None:
        """Persist the new window style and relaunch the app in it."""
        if mode not in ("desktop", "obs"):
            return
        _save_mode(mode)
        self._relaunch(mode)   # starts a fresh instance after a short delay
        self.quit()            # then this instance exits and frees the port

    def _kill_engine(self) -> None:
        name = Path(self._engine_path).name if self._engine_path else None
        if not name:
            return
        try:
            subprocess.run(["taskkill", "/IM", name, "/F"],
                           creationflags=_CREATE_NO_WINDOW,
                           capture_output=True)
        except Exception:
            pass

    def _relaunch(self, mode: str) -> None:
        if getattr(sys, "frozen", False):
            target = f'"{sys.executable}" --mode {mode}'
        else:
            target = f'"{sys.executable}" "{Path(__file__).resolve()}" --mode {mode}'
        # Wait 2s so this instance fully exits (and releases port 8765) before
        # the new one starts; survives this process dying via a detached cmd.
        try:
            subprocess.Popen(
                f'cmd /c timeout /t 2 /nobreak >nul & start "" {target}',
                shell=True, creationflags=_CREATE_NO_WINDOW,
            )
        except Exception:
            pass


def _save_mode(mode: str) -> None:
    """Rewrite only the `mode:` value in config.yaml (keeps comments intact)."""
    p = backend.app_base_dir() / "config.yaml"
    try:
        txt = p.read_text(encoding="utf-8")
        new = re.sub(r"(?m)^(\s*mode:\s*).*$", r"\g<1>" + mode, txt, count=1)
        p.write_text(new, encoding="utf-8")
    except Exception:
        pass


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> None:
    _setup_logging()

    ap = argparse.ArgumentParser(description="Chess Auditor desktop app")
    ap.add_argument("--mode", choices=["desktop", "obs"], default=None,
                    help="window style (default: app.mode in config.yaml)")
    args, _ = ap.parse_known_args()

    cfg = backend.load_config(None)
    port = cfg.get("server", {}).get("port", 8765)
    mode = args.mode or cfg.get("app", {}).get("mode", "desktop")
    always_on_top = bool(cfg.get("app", {}).get("always_on_top", False))
    engine_path = cfg.get("engine", {}).get("path")
    # ?app=<mode> tells the overlay which mode it's in (labels the switch button)
    url = f"http://{HOST}:{port}/?app={mode}"

    threading.Thread(target=start_backend, daemon=True).start()
    if not wait_for_server(url, 30):
        print("WARNING: backend server did not come up on "
              f"http://{HOST}:{port}/ within 30s — the window may stay blank. "
              "Check the engine path in config.yaml and this log for a traceback.")

    api = Api(engine_path)

    if mode == "obs":
        # Normal, movable, minimizable window. OBS captures the same URL; this
        # window is just so you can see/confirm the overlay while you set up OBS.
        window = webview.create_window(
            f"Chess Auditor (OBS source: http://{HOST}:{port}/)",
            url,
            width=980, height=700, resizable=True,
            frameless=False, on_top=False,
            background_color="#16161a",
            js_api=api,
        )
        api._window = window
        webview.start()
        return

    # desktop: frameless, auto-sized widget. Behaves like a normal window by
    # default; set app.always_on_top: true in config.yaml to keep it floating
    # over the game/browser.
    window = webview.create_window(
        "Chess Auditor",
        url,
        width=960, height=680, min_size=(420, 320),
        frameless=True,        # no title bar / white chrome
        easy_drag=False,       # only the in-app "Move" handle drags the window
        on_top=always_on_top,
        background_color="#16161a",
        resizable=True,
        js_api=api,
    )
    api._window = window

    def fit() -> None:
        # Resize the window to wrap the content exactly (kills empty margins).
        time.sleep(0.6)
        try:
            w = window.evaluate_js("document.getElementById('app').scrollWidth")
            h = window.evaluate_js("document.getElementById('app').scrollHeight")
            if w and h:
                window.resize(int(w) + 2, int(h) + 2)
        except Exception:
            pass

    window.events.loaded += lambda: threading.Thread(target=fit, daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
