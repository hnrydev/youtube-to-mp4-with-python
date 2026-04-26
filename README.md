# YouTube → progressive MP4 link (Vite + Python)

The UI calls **yt-dlp** over `POST /api/resolve` to find a **single-file (muxed) MP4** (video + audio in one stream). Merging DASH (separate A/V) on the server would require **ffmpeg**; that path is not included. Some videos have no progressive MP4; the API returns a clear error.

## When YouTube says “Sign in to confirm you’re not a bot”

YouTube often challenges datacenter IPs. This app retries alternate **player clients** (`mweb`, `ios`, `web`, `android`, …) and **strips `&list=…` from `watch` URLs** so a single `v=` is used.

If it still fails, set **Netscape-format cookies** on the **server** (Vercel env, Dokploy env, or your `systemd` unit) — export from a logged-in browser (see the [YouTube extractors](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies) doc), then use one of:

- **`YOUTUBE_COOKIES`** — the full file contents (multiline; some UIs are awkward for this), or  
- **`YOUTUBE_COOKIES_B64`** — the same file **base64**-encoded (avoids newlines in the dashboard), or  
- **`YOUTUBE_COOKIES_FILE`** — path **inside the container** to a mounted cookie file (e.g. Docker / Dokploy volume: `/data/youtube_cookies.txt`).

`GET /api/resolve` returns `cookiesConfigured: true` if any of the above is active and (for a file) the path is readable.

Do not commit cookies. Rotate them if they leak. Follow [yt-dlp cookies](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp) and YouTube’s terms.

## Deploy on a VPS (Dokploy + Nixpacks)

1. In Dokploy, use **Nixpacks** as the build type (default for many app templates; see [Dokploy build type](https://docs.dokploy.com/docs/core/applications/build-type) and [Nixpacks on Dokploy](https://nixpacks.com/docs/deploying/dokploy)).
2. Point the app at this repo. **Do not** set *Publish directory* to `dist` for this project: the container must keep the full tree so **Python + `dist/`** are both present. The process is one **uvicorn** that serves the built SPA and the API.
3. Map the container’s HTTP port to what Nixpacks uses: **`3000` by default** (override with the `PORT` environment variable). The start command runs  
   `uvicorn server:app --host 0.0.0.0 --port $PORT` (default `3000` if `PORT` is unset).
4. If the Nix build still mis-orders install steps, use **Dokploy env overrides** (see [Dokploy Nixpacks](https://docs.dokploy.com/docs/core/applications/build-type)) — do **not** use `python3 -m pip` on the Nix `python3` (it has no `pip`). Nixpacks’ `python:install` uses `/opt/venv` and `pip install -r requirements.txt` there. The `nixpacks.toml` `start` command prepends `/opt/venv/bin` to `PATH` so `uvicorn` runs from that venv.

### Run locally (same as production)

```bash
npm install
python3 -m pip install -r requirements.txt
npm run build
npm start
# or: uvicorn server:app --host 0.0.0.0 --port 3000
```

Before a release or deploy, run **`npm run check`** (Vite production build + `py_compile` + import of `resolve_core` / `server`).

Open `http://127.0.0.1:3000` — the API is at `/api/resolve` on the same origin.

## Vercel (serverless)

[Install the Vercel CLI](https://vercel.com/docs/cli), then:

```bash
npx vercel dev
# or: npx vercel
```

Configure function duration in `vercel.json` (e.g. Pro) if `yt-dlp` is slow. Respect YouTube’s terms and copyright.

## Project layout

- `src/` — React + Vite UI
- `resolve_core.py` — shared `yt-dlp` resolution
- `server.py` — FastAPI + static `dist/` (VPS)
- `api/resolve.py` — Vercel `handler` only
- `vercel.json` — Vercel build, SPA rewrites, Python function settings
- `nixpacks.toml` — Node + Vite + pip + uvicorn for Dokploy/Nixpacks
- `scripts/verify.py` — used by `npm run check`
- `requirements.txt` — `yt-dlp`, `fastapi`, `uvicorn`
