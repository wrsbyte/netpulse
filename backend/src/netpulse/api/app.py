"""FastAPI app factory + entrypoint.

Serves the JSON API and, when the frontend has been built, the static SPA from
``frontend/dist``. Localhost-only by default (see :class:`~netpulse.config.Settings`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from netpulse.api.routers import actions, data, raw, report
from netpulse.config import get_settings
from netpulse.db.session import init_engine
from netpulse.logging import configure_logging


class _SpaStatics(StaticFiles):
    """Serve the built SPA, but never let the browser cache the HTML shell — otherwise a stale
    index keeps referencing an old (deleted) hashed bundle after a redeploy. Hashed JS/CSS keep
    their default long-lived caching (their name changes when they change)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path in ("", ".", "index.html") or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_engine(settings.db_path)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="netpulse", version="0.2.0", lifespan=_lifespan)
    app.include_router(data.router)
    app.include_router(actions.router)
    app.include_router(raw.router)
    app.include_router(report.router)

    dist = get_settings().frontend_dist
    if dist.is_dir():
        app.mount("/", _SpaStatics(directory=dist, html=True), name="spa")
    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "netpulse.api.app:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_config=None,
    )
