"""VPS / Dokploy: FastAPI + static Vite `dist/`, one process (uvicorn)."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from resolve_core import get_resolve_info, post_resolve_from_body

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/resolve")
def api_resolve_get() -> dict:
    return get_resolve_info()


@app.post("/api/resolve")
async def api_resolve_post(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {
                "ok": False,
                "error": "Invalid JSON",
                "hint": 'Use body: { "url": "https://www.youtube.com/watch?v=…" }',
            }
        )
    return JSONResponse(post_resolve_from_body(body))


if os.path.isdir(DIST) and any(os.scandir(DIST)):
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
else:

    @app.get("/{full_path:path}")
    def _missing_build(full_path: str) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            {
                "ok": False,
                "error": "Frontend not built",
                "hint": "Run `npm run build` so the `dist/` directory exists, then start again.",
            },
            status_code=503,
        )
