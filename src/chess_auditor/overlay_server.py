"""Tiny HTTP server that serves the overlay and the current analysis state.

The overlay (index.html) polls /state.json. This keeps OBS integration to a
single Browser source with zero extra dependencies.
"""

from __future__ import annotations

import json
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

_OVERLAY_DIR = Path(__file__).parent / "overlay"


class _State:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._version = 0
        self._data: dict = {"fen": None, "highlights": [], "warnings": []}
        # Raw position pushed in by a capture client (e.g. the browser
        # userscript), awaiting analysis: {"fen": str, "color": "white"|"black"}.
        self._raw: dict | None = None
        self._raw_event = threading.Event()

    def set(self, data: dict) -> None:
        with self._cond:
            self._version += 1
            self._data = data
            self._cond.notify_all()

    def get(self) -> dict:
        with self._cond:
            return {**self._data, "v": self._version}

    def wait_changed(self, since: int, timeout: float) -> dict:
        """Block until the state version passes `since` (or timeout), then
        return the current state. Lets clients long-poll instead of polling."""
        with self._cond:
            self._cond.wait_for(lambda: self._version != since, timeout=timeout)
            return {**self._data, "v": self._version}

    def set_raw(self, raw: dict) -> None:
        with self._cond:
            self._raw = raw
        self._raw_event.set()

    def get_raw(self) -> dict | None:
        with self._cond:
            return dict(self._raw) if self._raw else None

    def wait_raw(self, timeout: float) -> bool:
        """Block until a new raw position is pushed (or timeout)."""
        if self._raw_event.wait(timeout):
            self._raw_event.clear()
            return True
        return False


class _Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, state: _State, **kwargs):
        self._state = state
        super().__init__(*args, **kwargs)

    def log_message(self, *args) -> None:  # silence default logging
        pass

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self) -> None:
        if not self.path.startswith("/fen"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            fen = payload.get("fen")
            if not fen:
                raise ValueError("missing fen")
            self._state.set_raw({"fen": fen, "color": payload.get("color")})
            body = b'{"ok":true}'
        except (ValueError, json.JSONDecodeError) as e:
            body = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
        self._send_bytes(body, "application/json")

    def do_GET(self) -> None:
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            self._send_file(_OVERLAY_DIR / "index.html", "text/html")
        elif path == "/state.json":
            # Long-poll: /state.json?v=<n> parks the request until the state
            # version moves past n (each request has its own thread, so this
            # never blocks POST /fen). Bare /state.json answers immediately,
            # keeping OBS browser sources and old clients working unchanged.
            since = parse_qs(query).get("v", [None])[0]
            if since is not None and since.lstrip("-").isdigit():
                state = self._state.wait_changed(int(since), timeout=25.0)
            else:
                state = self._state.get()
            self._send_bytes(json.dumps(state).encode("utf-8"), "application/json")
        else:
            self.send_error(404)

    def _send_file(self, path: Path, ctype: str) -> None:
        try:
            self._send_bytes(path.read_bytes(), ctype)
        except OSError:
            self.send_error(404)

    def _send_bytes(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)


class OverlayServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.state = _State()
        handler = partial(_Handler, state=self.state)
        # Retry the bind briefly: when the app relaunches to switch modes, the
        # previous instance may still be releasing the port for a moment.
        import time as _time
        last_err = None
        for _ in range(20):
            try:
                self._httpd = ThreadingHTTPServer((host, port), handler)
                break
            except OSError as e:
                last_err = e
                _time.sleep(0.25)
        else:
            raise last_err
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self.url = f"http://{host}:{port}/"

    def start(self) -> None:
        self._thread.start()

    def publish(self, data: dict) -> None:
        self.state.set(data)

    def get_raw(self) -> dict | None:
        """Latest raw position pushed by a capture client, if any."""
        return self.state.get_raw()

    def wait_for_raw(self, timeout: float) -> bool:
        """Block until a capture client pushes a new position (or timeout).
        Lets the analysis loop react instantly instead of sleep-polling."""
        return self.state.wait_raw(timeout)

    def stop(self) -> None:
        self._httpd.shutdown()
