"""Shared YouTube → progressive MP4 resolution (Vercel handler, FastAPI, or tests)."""

from __future__ import annotations

import base64
import logging
import os
import tempfile
import urllib.parse
from contextlib import contextmanager
from typing import Any, Iterator

import yt_dlp

# Keep container logs clean: yt-dlp still prints to stderr on each failed client attempt
for _name in ("yt_dlp", "yt_dlp.cookies", "yt_dlp.networking"):
    logging.getLogger(_name).setLevel(logging.CRITICAL + 1)
del _name


class _YdlLogger:
    """Swallow yt-dlp console noise (retries would spam four ERROR: lines)."""

    def debug(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002
        return

    def info(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002
        return

    def warning(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002
        return

    def error(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002
        return

    def trace(self, *args, **kwargs) -> None:  # noqa: ANN001, ANN002
        return

_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)

NO_PROGRESSIVE_HINT = (
    "This server only returns a single muxed MP4 stream. Many HD items are DASH (split A/V). "
    "On a server without ffmpeg, try another quality or use yt-dlp+ffmpeg locally."
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Tried in order. Later entries fall back to yt-dlp default clients.
_YT_CLIENT_LAYERS: list[dict[str, Any]] = [
    {
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb", "web", "ios", "android"],
            }
        }
    },
    {
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "mweb", "web"],
            }
        }
    },
    {
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        }
    },
    {},
]

_BOT_HINT = (
    "On your server, provide Netscape cookies: YOUTUBE_COOKIES (raw), YOUTUBE_COOKIES_B64, "
    "or YOUTUBE_COOKIES_FILE (path to a cookie file, e.g. a mounted volume in Docker). "
    "See https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
)


def _resolve_cookiefile_path() -> str | None:
    """Path to a readable cookie file from env, or None."""
    raw = (os.environ.get("YOUTUBE_COOKIES_FILE") or os.environ.get("YTDLP_COOKIES_FILE") or "").strip()
    if not raw:
        return None
    p = os.path.expanduser(os.path.expandvars(raw))
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    p = os.path.normpath(p)
    if os.path.isfile(p) and os.access(p, os.R_OK):
        return p
    return None


def _cookies_configured() -> bool:
    if (os.environ.get("YOUTUBE_COOKIES") or os.environ.get("YOUTUBE_COOKIES_B64") or "").strip():
        return True
    return _resolve_cookiefile_path() is not None


def _cookiefile_env_misconfigured() -> str | None:
    """If YOUTUBE_COOKIES_FILE is set but unusable, explain for operators."""
    raw = (os.environ.get("YOUTUBE_COOKIES_FILE") or os.environ.get("YTDLP_COOKIES_FILE") or "").strip()
    if not raw:
        return None
    if _resolve_cookiefile_path() is not None:
        return None
    p = os.path.expanduser(os.path.expandvars(raw))
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    p = os.path.normpath(p)
    return (
        f"YOUTUBE_COOKIES_FILE is {raw!r} (looked for {p!r}) but that file is missing or not "
        f"readable in the container. Mount a volume or copy the file into the image."
    )


@contextmanager
def _cookiefile_for_ydl() -> Iterator[str | None]:
    """Cookie file: mounted path (YOUTUBE_COOKIES_FILE) first, else temp from env text."""
    fixed = _resolve_cookiefile_path()
    if fixed is not None:
        yield fixed
        return
    with _env_cookie_path() as t:
        yield t


@contextmanager
def _env_cookie_path() -> Iterator[str | None]:
    text = (os.environ.get("YOUTUBE_COOKIES") or os.environ.get("YTDLP_COOKIES") or "").strip()
    b64 = (os.environ.get("YOUTUBE_COOKIES_B64") or "").strip()
    if b64:
        try:
            text = base64.b64decode(b64).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            text = ""
    if not text or not str(text).strip():
        yield None
        return
    text = str(text).strip() + "\n"
    path: str | None = None
    try:
        fd, path = tempfile.mkstemp(suffix="_yt_cookies.txt", text=True)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        yield path
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _strip_playlist_extras(url: str) -> str:
    try:
        p = urllib.parse.urlparse(url)
        host = (p.netloc or "").lower()
        if "youtube" not in host and "youtu.be" not in host:
            return url
        if "/watch" in (p.path or "") and "v=" in (p.query or ""):
            q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
            v = (q.get("v") or [""])[0]
            if v:
                q2 = urllib.parse.urlencode({"v": v})
                return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", q2, ""))
        return url
    except (ValueError, TypeError, AttributeError):
        return url


def _is_bot_block_message(msg: str) -> bool:
    s = (msg or "").lower()
    if "not a bot" in s and "sign in" in s:
        return True
    if "sign in to confirm" in s:
        return True
    if "use --cookies" in s or "--cookies-from-browser" in s:
        return True
    return False


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
    """YouTube may block datacenter / bot clients; retry alternate player clients and cookies."""
    u = _strip_playlist_extras(url)
    last_err: Exception | None = None
    with _cookiefile_for_ydl() as cookiefile:
        for layer in _YT_CLIENT_LAYERS:
            opts: dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "noprogress": True,
                "noplaylist": True,
                "skip_download": True,
                "logger": _YdlLogger(),
                "http_headers": {
                    "User-Agent": UA,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            opts.update(layer)
            if cookiefile:
                opts["cookiefile"] = cookiefile
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(u, download=False)
            except Exception as e:  # noqa: BLE001
                last_err = e
    if last_err is not None:
        raise last_err
    return None


def get_resolve_info() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "ytdl-resolve",
        "usage": 'POST with JSON: {"url":"https://www.youtube.com/watch?v=..."}',
        "cookiesConfigured": _cookies_configured(),
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
        if len(message) > 400:
            message = message[:400] + "…"
        hint = message
        if _is_bot_block_message(message):
            mfile = _cookiefile_env_misconfigured()
            if mfile:
                extra = f"{mfile} {_BOT_HINT}"
            elif not _cookies_configured():
                extra = (
                    "No working cookie config (set YOUTUBE_COOKIES, YOUTUBE_COOKIES_B64, or "
                    "YOUTUBE_COOKIES_FILE to a file that exists in the container). " + _BOT_HINT
                )
            else:
                extra = (
                    "Cookies are configured but YouTube still rejected the request; refresh the "
                    f"export or try another network. {_BOT_HINT}"
                )
            hint = f"{message} — {extra}"
        return {
            "ok": False,
            "error": "yt-dlp could not read that URL",
            "hint": hint,
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
