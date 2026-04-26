"""Shared YouTube → progressive MP4 resolution (Vercel handler, FastAPI, or tests)."""

from __future__ import annotations

import json
import urllib.parse
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

NO_PROGRESSIVE_HINT = (
    "YouTube often serves HD as DASH (separate A/V) — merging needs ffmpeg, which is not in "
    "this setup. Try a clip that still offers 360p/480p progressive, or use yt-dlp with "
    "ffmpeg on your own machine."
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


def get_resolve_info() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "ytdl-resolve",
        "usage": 'POST with JSON: {"url":"https://www.youtube.com/watch?v=..."}',
    }


def post_resolve_from_body(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {
            "ok": False,
            "error": "Invalid JSON",
            "hint": 'Use body: { "url": "https://www.youtube.com/watch?v=…" }',
        }

    url = (str(body.get("url") or "")).strip()
    if not url or not _is_allowed_youtube_url(url):
        return {
            "ok": False,
            "error": "Not a YouTube link",
            "hint": "Use a youtube.com, youtu.be, or Shorts URL from this site.",
        }

    try:
        info = _extract_info(url)
    except Exception as e:  # noqa: BLE001
        message = str(e) if e else "Unknown"
        if len(message) > 300:
            message = message[:300] + "…"
        return {
            "ok": False,
            "error": "yt-dlp could not read that URL",
            "hint": message,
        }

    if not info:
        return {
            "ok": False,
            "error": "No metadata",
            "hint": "The resolver returned no video data.",
        }

    title = (info.get("title") or "Video").replace("\n", " ").replace("\r", " ")

    u = info.get("url")
    vcodec = (info.get("vcodec") or "none") or "none"
    if u and vcodec not in ("none", "") and info.get("ext") == "mp4":
        height = info.get("height", "?")
        return {
            "ok": True,
            "title": title,
            "downloadUrl": u,
            "qualityLabel": f"MP4 (direct) · {height}p",
        }

    pick = _best_progressive_mp4(info)
    if not pick:
        return {
            "ok": False,
            "error": "No progressive MP4 is exposed for this video",
            "hint": NO_PROGRESSIVE_HINT,
        }

    return {
        "ok": True,
        "title": title,
        "downloadUrl": pick["url"],
        "qualityLabel": pick["qualityLabel"],
    }
