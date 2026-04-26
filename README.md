# YouTube → progressive MP4 link (Vite + Python on Vercel)

The UI calls a Vercel Python function that uses **yt-dlp** to find a **single-file (muxed) MP4** with both video and audio. There is **no ffmpeg** in serverless, so DASH (separate A/V) is not merged here. Some videos have no exposed progressive MP4; those will return an error from `/api/resolve`.

## Run locally (full stack)

[Install the Vercel CLI](https://vercel.com/docs/cli), then from the project root:

```bash
npx vercel dev
```

Open the URL the CLI prints (port may vary). The `vercel.json` `devCommand` runs Vite so the app and `api/resolve` share one origin.

## Build only (frontend)

```bash
npm install
npm run build
```

`npm run dev` serves the Vite app only; without `vercel dev`, `/api/resolve` is not available locally.

## Deploy

```bash
npx vercel
```

- Set a **function max duration** that fits your plan (Hobby: 10s, Pro: up to 60s with the config in `vercel.json`). `yt-dlp` can be slow; upgrade or relax timeouts if you see 504s.
- Respect **YouTube’s terms** and only use for content you’re allowed to access.

## Project layout

- `src/` — React + Vite (Cursor-style dark UI)
- `api/resolve.py` — serverless `handler` (yt-dlp)
- `vercel.json` — build output, SPA rewrite, Python function settings
- `requirements.txt` — `yt-dlp`
