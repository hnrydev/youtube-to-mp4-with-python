"""Vercel: HTTP handler that delegates to shared `resolve_core`."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import resolve_core


def _read_json(h: BaseHTTPRequestHandler) -> object:
    cl = h.headers.get("Content-Length", "0")
    try:
        n = int(cl)
    except ValueError:
        n = 0
    raw = h.rfile.read(n) if n else b""
    return json.loads(raw.decode("utf-8") or "{}")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._write_json(200, resolve_core.get_resolve_info())

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = _read_json(self)
        except json.JSONDecodeError:
            out = {
                "ok": False,
                "error": "Invalid JSON",
                "hint": 'Use body: { "url": "https://www.youtube.com/watch?v=…" }',
            }
            self._write_json(200, out)
            return
        out = resolve_core.post_resolve_from_body(body)
        self._write_json(200, out)

    def _write_json(self, code: int, data: object) -> None:
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args) -> None:
        return
