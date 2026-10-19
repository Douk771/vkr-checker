"""HTTP-слой без бизнес-логики: приём, лимиты, слоты, таймауты, перевод ошибок (API_CONTRACT §2)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

from anyio import to_thread
from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError

from vkr_checker import __version__
from vkr_checker.docx.package import DocxError
from vkr_checker.matrix.xlsx import build_matrix_xlsx, export_filename
from vkr_checker.report.schema import (
    CheckReport,
    CompareReport,
    ErrorResponse,
    Health,
    MatrixExportRequest,
)

from .auth import require_auth
from .errors import ApiError
from .ports import InputFileError
from .upload import receive_files

log = logging.getLogger("vkr_checker.web")
T = TypeVar("T")

router = APIRouter(prefix="/api")

_ERR = {"model": ErrorResponse}
_PROCESSING_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {**_ERR, "description": "bad_request / missing_file"},
    401: {**_ERR, "description": "auth_required / invalid_password"},
    413: {**_ERR, "description": "file_too_large"},
    415: {**_ERR, "description": "unsupported_format"},
    422: {**_ERR, "description": "invalid_docx / docx_limits_exceeded"},
    500: {**_ERR, "description": "internal_error"},
    503: {**_ERR, "description": "server_busy / processing_timeout"},
}


def _multipart_body(fields: list[str]) -> dict[str, Any]:
    """Тело запроса для OpenAPI: файлы читаются из Request вручную, поэтому описываем явно."""
    return {
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": fields,
                        "properties": {f: {"type": "string", "format": "binary"} for f in fields},
                    }
                }
            },
        }
    }


@router.get("/health", response_model=Health, operation_id="getHealth", tags=["service"])
async def get_health(request: Request) -> Health:
    s = request.app.state.settings
    layout = request.app.state.layout_info
    return Health(
        status="ok",
        service_version=__version__,
        mode=s.mode,
        auth_required=s.auth_required,
        authenticated=request.app.state.authenticator.is_authenticated(request),
        layout_available=layout.available,
        layout_engine=layout.engine if layout.available else None,
        limits={
            "max_upload_mb": s.max_upload_mb,
            "check_timeout_s": s.check_timeout_s,
            "compare_timeout_s": s.compare_timeout_s,
        },
    )


async def _run_blocking(fn: Callable[..., T], *args: Any, timeout_s: int, field: str = "file") -> T:
    """Синхронный конвейер в рабочем потоке с жёстким таймаутом; сбои переводятся в ApiError."""
    try:
        return await asyncio.wait_for(to_thread.run_sync(fn, *args), timeout=timeout_s)
    except asyncio.TimeoutError:
        raise ApiError("processing_timeout", retry_after=None) from None
    except DocxError as exc:
        raise ApiError(exc.code, exc.message, field=field) from exc
    except InputFileError as exc:
        raise ApiError(exc.code, exc.message, field=exc.field) from exc
    except ApiError:
        raise
    except Exception as exc:
        # значения и тексты работ в лог не попадают: только тип исключения
        log.error("сбой конвейера type=%s", type(exc).__name__, exc_info=False)
        raise ApiError("internal_error") from exc


@router.post(
    "/check",
    response_model=CheckReport,
    operation_id="checkDocument",
    tags=["check"],
    responses=_PROCESSING_ERRORS,
    openapi_extra=_multipart_body(["file"]),
    dependencies=[Depends(require_auth)],
)
async def check_document(request: Request) -> Any:
    s = request.app.state.settings
    with tempfile.TemporaryDirectory(prefix="vkr-") as tmp:
        files = await receive_files(request, ("file",), Path(tmp), s.max_upload_bytes)
        async with request.app.state.slots.acquire(1):
            return await _run_blocking(
                request.app.state.pipeline.check, files["file"], timeout_s=s.check_timeout_s
            )


@router.post(
    "/compare",
    response_model=CompareReport,
    operation_id="compareVersions",
    tags=["check"],
    responses=_PROCESSING_ERRORS,
    openapi_extra=_multipart_body(["old", "new"]),
    dependencies=[Depends(require_auth)],
)
async def compare_versions(request: Request) -> Any:
    s = request.app.state.settings
    with tempfile.TemporaryDirectory(prefix="vkr-") as tmp:
        files = await receive_files(request, ("old", "new"), Path(tmp), s.max_upload_bytes)
        async with request.app.state.slots.acquire(2):
            return await _run_blocking(
                request.app.state.pipeline.compare,
                files["old"],
                files["new"],
                timeout_s=s.compare_timeout_s,
            )


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "/export/matrix.xlsx",
    operation_id="exportMatrixXlsx",
    tags=["export"],
    responses={
        200: {"content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}}},
        401: _ERR,
        413: _ERR,
        422: _ERR,
        500: _ERR,
    },
    response_class=Response,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/MatrixExportRequest"}}
            },
        }
    },
    dependencies=[Depends(require_auth)],
)
async def export_matrix_xlsx(request: Request) -> Response:
    try:
        payload = MatrixExportRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise ApiError("validation_error", field="matrix") from None
    try:
        data = await to_thread.run_sync(
            build_matrix_xlsx,
            payload.matrix,
            payload.file_name,
            payload.service_version,
            payload.checked_at,
        )
    except Exception as exc:
        log.error("сбой выгрузки матрицы type=%s", type(exc).__name__)
        raise ApiError("internal_error") from exc
    name = export_filename(payload.file_name)
    return Response(
        content=data,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
