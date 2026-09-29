"""A page on this PC only. It is not reachable from other computers."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .render import render_html
from .scan import run_scan

_LOCK = threading.Lock()

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What is slowing this PC</title>
<style>
  body { margin: 0; background: #f6f3ec; color: #1c1915; font: 18px/1.5 "Segoe UI", Helvetica, Arial, sans-serif; }
  main { max-width: 720px; margin: 0 auto; padding: 36px 18px 64px; }
  h1 { font-size: 2rem; line-height: 1.15; margin-bottom: 8px; }
  form { display: flex; flex-wrap: wrap; gap: 14px; align-items: end; background: #fffdf8; border: 1px solid #e3dccf; padding: 16px; border-radius: 14px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 0.92rem; color: #5c564c; }
  input { font: inherit; width: 6rem; padding: 8px 10px; border-radius: 8px; border: 1px solid #e3dccf; }
  button { font: inherit; background: #24352c; color: white; border: 0; border-radius: 10px; padding: 10px 16px; cursor: pointer; }
  .note { color: #5c564c; }
</style>
</head>
<body>
<main>
  <h1>What is slowing this PC</h1>
  <p>This watches the programs already running, then writes a plain-language report. It does not close anything. Leave the slow programs open while it watches.</p>
  <form method="post" action="/scan">
    <label>Seconds to watch
      <input name="seconds" type="number" min="3" max="60" value="8">
    </label>
    <label>Repeat
      <input name="repeat" type="number" min="1" max="4" value="1">
    </label>
    <button type="submit">Check this PC</button>
  </form>
  <p class="note">A repeat of 3, at 20 seconds each, is the better test when you want to know whether a program stays heavy or only spiked once. The page will sit here while it watches. That pause is the measurement.</p>
</main>
</body>
</html>
"""

_BANNER = """
<form class="check" method="post" action="/scan">
  <label>Seconds to watch
    <input name="seconds" type="number" min="3" max="60" value="{seconds}">
  </label>
  <label>Repeat
    <input name="repeat" type="number" min="1" max="4" value="{repeat}">
  </label>
  <button type="submit">Check again</button>
</form>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] not in {"/", "/index.html"}:
            self._send(404, "Not found.")
            return
        self._send(200, _PAGE)

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/scan":
            self._send(404, "Not found.")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(min(length, 4096)).decode("utf-8", errors="replace")
        form = parse_qs(raw)
        try:
            seconds = float((form.get("seconds") or ["8"])[0])
        except ValueError:
            seconds = 8.0
        try:
            repeats = int((form.get("repeat") or ["1"])[0])
        except ValueError:
            repeats = 1
        seconds = min(60.0, max(3.0, seconds))
        repeats = min(4, max(1, repeats))
        if not _LOCK.acquire(blocking=False):
            self._send(409, "A check is already running. Wait for it to finish.")
            return
        try:
            report = run_scan(seconds=seconds, repeats=repeats, include_events=True)
        except Exception as exc:  # noqa: BLE001 — show a short message, keep the page up
            self._send(500, f"The check failed: {exc}")
            return
        finally:
            _LOCK.release()
        from .render import write_reports
        from pathlib import Path

        write_reports(report, Path("reports"))
        banner = _BANNER.format(seconds=int(seconds), repeat=repeats)
        self._send(200, render_html(report, banner_html=banner))

    def _send(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("The page is only allowed on this PC (127.0.0.1).")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Open http://{host}:{port} in this PC's browser. Press Ctrl+C to stop.")
    print("Nothing is exposed to other computers.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
