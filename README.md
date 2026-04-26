# YouTube → progressive MP4 link (Vite + Python)

The UI calls **yt-dlp** over `POST /api/resolve` to find a **single-file (muxed) MP4** (video + audio in one stream). This stack has **no ffmpeg** merge, so DASH-only formats are not combined. Some videos have no progressive MP4; the API returns a clear error.

## Deploy on a VPS (Dokploy + Nixpacks)

1. In Dokploy, use **Nixpacks** as the build type (default for many app templates; see [Dokploy build type](https://docs.dokploy.com/docs/core/applications/build-type) and [Nixpacks on Dokploy](https://nixpacks.com/docs/deploying/dokploy)).
2. Point the app at this repo. **Do not** set *Publish directory* to `dist` for this project: the container must keep the full tree so **Python + `dist/`** are both present. The process is one **uvicorn** that serves the built SPA and the API.
3. Map the container’s HTTP port to what Nixpacks uses: **`3000` by default** (override with the `PORT` environment variable). The start command runs  
   `uvicorn server:app --host 0.0.0.0 --port $PORT` (default `3000` if `PORT` is unset).
4. If the Nix build skips Node or pip, set in Dokploy (or use `nixpacks.toml` only after tuning):

   - `NIXPACKS_INSTALL_CMD` = `npm ci && python3 -m pip install -r requirements.txt` (or `npm install` if you have no lock file discipline)
   - `NIXPACKS_START_CMD` = `sh -c 'uvicorn server:app --host 0.0.0.0 --port ${PORT:-3000}'`

### Run locally (same as production)

```bash
npm install
python3 -m pip install -r requirements.txt
npm run build
npm start
# or: uvicorn server:app --host 0.0.0.0 --port 3000
```

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
- `requirements.txt` — `yt-dlp`, `fastapi`, `uvicorn`
