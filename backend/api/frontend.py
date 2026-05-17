from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

try:
    from ..core.config import FRONTEND_OUT_DIR
except ImportError:
    from core.config import FRONTEND_OUT_DIR


def get_frontend_file(path: str) -> Path | None:
    frontend_root = FRONTEND_OUT_DIR.resolve()
    requested_path = path.strip("/")
    candidates = [
        FRONTEND_OUT_DIR / requested_path,
        FRONTEND_OUT_DIR / f"{requested_path}.html",
        FRONTEND_OUT_DIR / requested_path / "index.html",
    ]

    for candidate_path in candidates:
        candidate = candidate_path.resolve()
        try:
            candidate.relative_to(frontend_root)
        except ValueError:
            continue

        if candidate.is_file():
            return candidate

    return None


def register_frontend_routes(app: FastAPI) -> None:
    @app.get("/")
    @app.get("/{path:path}")
    def serve_frontend(path: str = ""):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        requested_file = get_frontend_file(path) if path else None
        if requested_file is not None:
            return FileResponse(requested_file)

        index_file = FRONTEND_OUT_DIR / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)

        return JSONResponse(
            {
                "message": "Frontend has not been built yet. Run `npm run build` in frontend first.",
                "healthApi": "/api/health",
                "cacheStatsApi": "/api/cache/stats?limit=10",
            },
            status_code=503,
        )
