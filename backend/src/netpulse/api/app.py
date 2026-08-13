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

from netpulse.api.routers import actions, data
from netpulse.config import get_settings
from netpulse.db.session import init_engine
from netpulse.logging import configure_logging


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_engine(settings.db_path)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="netpulse", version="0.1.0", lifespan=_lifespan)
    app.include_router(data.router)
    app.include_router(actions.router)

    dist = get_settings().frontend_dist
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="spa")
    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)
