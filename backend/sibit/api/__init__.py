"""FastAPI application factory. Serves the API and the built React app."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .hits_routes import router as hits_router
from .routes import router
from .state import AppState


def web_dir() -> Path:
    """Built frontend: sibit/web (source tree) or <bundle>/sibit/web (PyInstaller)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    for cand in (base / "sibit" / "web", Path(__file__).resolve().parents[1] / "web"):
        if (cand / "index.html").is_file():
            return cand
    return Path(__file__).resolve().parents[1] / "web"


def create_app(state: AppState | None = None) -> FastAPI:
    app = FastAPI(title="Sibit", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.sibit = state or AppState()
    # Local-only tool: reject requests whose Host is not localhost (DNS-rebinding guard).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.include_router(router)
    app.include_router(hits_router)

    web = web_dir()
    if (web / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = (web / path).resolve()
        if path and f.is_file() and web.resolve() in f.parents:
            return FileResponse(f)
        index = web / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Frontend not built. Run: cd frontend && npm run build"}, status_code=404)

    return app
