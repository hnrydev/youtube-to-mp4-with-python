"""Resolve a public YouTube URL to a progressive (muxed) MP4 stream when available."""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Any

import yt_dlp

_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)


def _is_allowed_youtube_url(url: str) -> bool:
    try:
        p = urllib.parse.urlparse(url)
        h = p.netloc.lower()
        if p.scheme not in ("http", "https") or not h:
            return False
        if h.startswith("www."):
            h = h[4:]
        return h in _ALLOWED_HOSTS
    except (ValueError, AttributeError):
        return False


def _non_none(codec: str | None) -> bool:
    c = (codec or "none") or "none"
    return c not in ("none", "")


def _best_progressive_mp4(info: dict[str, Any]) -> dict[str, str] | None:
    out: list[tuple[int, int, dict]] = []
    for f in info.get("formats") or []:
        if f.get("ext") != "mp4" or not f.get("url"):
            continue
        v = f.get("vcodec")
        a = f.get("acodec")
        if not _non_none(v) or not _non_none(a):
            continue
        if str(v or "").endswith("none") or str(a or "").endswith("none"):
            continue
        height = int(f.get("height") or 0)
        tbr = int(f.get("tbr") or f.get("abr") or 0)
        w = int(f.get("width") or 0)
        out.append((height, tbr, w, f))
    if not out:
        return None
    out.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    f = out[0][-1]
    h = f.get("height")
    tbr = f.get("tbr")
    if tbr is None and f.get("abr") is not None:
        tbr = f.get("abr")
    label = "MP4"
    if h is not None:
        label = f"MP4 · {int(h)}p"
    if tbr is not None:
        try:
            t = int(tbr)
            if t:
                label += f" ~{t}kbps"
        except (TypeError, ValueError):
            pass
    return {"url": f["url"], "qualityLabel": label}


def _extract_info(url: str) -> dict[str, Any] | None:
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def _read_json(h: BaseHTTPRequestHandler) -> dict[str, Any]:
    cl = h.headers.get("Content-Length", "0")
    try:
        n = int(cl)
    except ValueError:
        n = 0
    raw = h.rfile.read(n) if n else b""
    return json.loads(raw.decode("utf-8") or "{}")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:  # noqa: N802 (Vercel contract)
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        b = json.dumps(
            {
                "ok": True,
                "service": "ytdl-resolve",
                "usage": "POST with JSON: {\"url\":\"https://www.youtube.com/watch?v=...\"}",
            }
        )
        self.wfile.write(b.encode("utf-8"))

    def do_POST(self) -> None:  # noqa: N802
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        try:
            body = _read_json(self)
        except json.JSONDecodeError:
            out = {
                "ok": False,
                "error": "Invalid JSON",
                "hint": 'Use body: { "url": "https://www.youtube.com/watch?v=…" }',
            }
            self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
            return

        url = (str(body.get("url") or "")).strip()
        if not url or not _is_allowed_youtube_url(url):
            out = {
                "ok": False,
                "error": "Not a YouTube link",
                "hint": "Use a youtube.com, youtu.be, or Shorts URL from this site.",
            }
            self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
            return

        try:
            info = _extract_info(url)
        except Exception as e:  # noqa: BLE001 — surface yt-dlp errors
            message = str(e) if e else "Unknown"
            if len(message) > 300:
                message = message[:300] + "…"
            out = {
                "ok": False,
                "error": "yt-dlp could not read that URL",
                "hint": message,
            }
            self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
            return

        if not info:
            out = {
                "ok": False,
                "error": "No metadata",
                "hint": "The resolver returned no video data.",
            }
            self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
            return

        title = (info.get("title") or "Video").replace("\n", " ").replace("\r", " ")

        u = info.get("url")
        vcodec = (info.get("vcodec") or "none") or "none"
        if u and vcodec not in ("none", "") and info.get("ext") == "mp4":
            height = info.get("height", "?")
            out = {
                "ok": True,
                "title": title,
                "downloadUrl": u,
                "qualityLabel": f"MP4 (direct) · {height}p",
            }
            self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
            return

        pick = _best_progressive_mp4(info)
        if not pick:
            out = {
                "ok": False,
                "error": "No progressive MP4 is exposed for this video",
                "hint": "YouTube often serves HD as DASH (separate A/V) — merging needs ffmpeg, which is not in this serverless runtime. Try a clip that still offers 360p/480p progressive, or use yt-dlp on your own machine with ffmpeg installed.",
            }
            self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
            return

        out = {
            "ok": True,
            "title": title,
            "downloadUrl": pick["url"],
            "qualityLabel": pick["qualityLabel"],
        }
        self.wfile.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args) -> None:
        return
