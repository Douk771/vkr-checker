"""Точка входа: create_app() и CLI `vkr-checker`."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings, get_settings
from .layout.soffice import SofficeInfo, probe_soffice
from .web.auth import Authenticator, session_router
from .web.errors import install_error_handlers
from .web.middleware import BodyLimitMiddleware, RequestContextMiddleware
from .web.routes import router
from .web.slots import SlotPool
from .web.stub import StubPipeline

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
REQUEST_OVERHEAD_BYTES = 1024 * 1024
SESSION_BODY_LIMIT = 64 * 1024


def _body_limits(s: Settings) -> dict[tuple[str, str], tuple[int, str]]:
    file_msg = f"Файл больше {s.max_upload_mb} МБ."
    return {
        ("POST", "/api/check"): (s.max_upload_bytes + REQUEST_OVERHEAD_BYTES, file_msg),
        ("POST", "/api/compare"): (2 * s.max_upload_bytes + REQUEST_OVERHEAD_BYTES, file_msg),
        ("POST", "/api/export/matrix.xlsx"): (
            s.max_json_bytes,
            f"Тело запроса больше {s.max_json_mb} МБ.",
        ),
        ("POST", "/api/session"): (SESSION_BODY_LIMIT, "Слишком большое тело запроса."),
    }


def create_app(settings: Settings | None = None, layout_info: SofficeInfo | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    app = FastAPI(title="vkr-checker", version=__version__, separate_input_output_schemas=False)
    app.state.settings = settings
    app.state.layout_info = layout_info or probe_soffice(settings.soffice_path)
    app.state.authenticator = Authenticator(settings)
    app.state.slots = SlotPool(settings.max_concurrent_jobs)
    app.state.pipeline = StubPipeline()  # заменяется настоящим конвейером в B-23

    install_error_handlers(app)
    app.include_router(router)
    app.include_router(session_router)
    app.add_middleware(BodyLimitMiddleware, limits=_body_limits(settings))
    app.add_middleware(RequestContextMiddleware)  # последним: он внешний и ставит X-Request-Id
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
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
