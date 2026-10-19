"""Точка входа: create_app() и CLI `vkr-checker`."""

from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="vkr-checker", version=__version__)
    app.state.settings = settings
    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host or "127.0.0.1",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
