"""HTTP-слой без бизнес-логики: приём, лимиты, слоты, таймауты, перевод ошибок (API_CONTRACT §2)."""

from __future__ import annotations

import asyncio
import logging
import shutil
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
from vkr_checker.report.docx_export import build_report_docx, report_filename
from vkr_checker.report.schema import (
    CheckReport,
    CompareReport,
    ErrorResponse,
    Health,
    MatrixExportRequest,
    ReportExportRequest,
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
        authenticated=request.app.state.authenticator.has_valid_session(request),
        layout_available=layout.available,
        layout_engine=layout.engine if layout.available else None,
        limits={
            "max_upload_mb": s.max_upload_mb,
            "check_timeout_s": s.check_timeout_s,
            "compare_timeout_s": s.compare_timeout_s,
        },
    )


def _translate(exc: Exception, field: str) -> ApiError:
    if isinstance(exc, DocxError):
        return ApiError(exc.code, exc.message, field=field)
    if isinstance(exc, InputFileError):
        return ApiError(exc.code, exc.message, field=exc.field)
    if isinstance(exc, ApiError):
        return exc
    # значения и тексты работ в лог не попадают: только тип исключения
    log.error("сбой конвейера type=%s", type(exc).__name__, exc_info=False)
    return ApiError("internal_error")


async def _run_job(
    request: Request,
    fields: tuple[str, ...],
    slots_needed: int,
    timeout_s: int,
    fn: Callable[..., T],
    max_bytes: int,
    *,
    field: str = "file",
) -> T:
    """Приём файлов, слоты и конвейер в рабочем потоке.

    Таймаут отвечает клиенту 503, но слот и каталог загрузки освобождаются только когда поток
    действительно закончил: иначе лимит одновременных задач не действует, а каталог исчезает
    под работающим потоком.
    """
    slots = request.app.state.slots
    tmp = Path(tempfile.mkdtemp(prefix="vkr-"))
    slot_taken = False
    started = False
    try:
        files = await receive_files(request, fields, tmp, max_bytes)
        await slots.take(slots_needed)
        slot_taken = True
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, lambda: fn(*[files[f] for f in fields]))
        started = True

        def _finished(_: Any) -> None:
            shutil.rmtree(tmp, ignore_errors=True)
            loop.create_task(slots.give(slots_needed))

        future.add_done_callback(_finished)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise ApiError("processing_timeout", retry_after=None) from None
        except Exception as exc:
            raise _translate(exc, field) from exc
    finally:
        if not started:
            shutil.rmtree(tmp, ignore_errors=True)
            if slot_taken:
                await slots.give(slots_needed)


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
    return await _run_job(
        request,
        ("file",),
        1,
        s.check_timeout_s,
        request.app.state.pipeline.check,
        s.max_upload_bytes,
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
    return await _run_job(
        request,
        ("old", "new"),
        2,
        s.compare_timeout_s,
        request.app.state.pipeline.compare,
        s.max_upload_bytes,
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


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post(
    "/export/report.docx",
    operation_id="exportReportDocx",
    tags=["export"],
    responses={
        200: {"content": {DOCX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}}},
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
                "application/json": {"schema": {"$ref": "#/components/schemas/ReportExportRequest"}}
            },
        }
    },
    dependencies=[Depends(require_auth)],
)
async def export_report_docx(request: Request) -> Response:
    try:
        payload = ReportExportRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise ApiError("validation_error", field="report") from None
    try:
        data = await to_thread.run_sync(build_report_docx, payload.check, payload.compare)
    except Exception as exc:
        log.error("сбой выгрузки отчёта в docx type=%s", type(exc).__name__)
        raise ApiError("internal_error") from exc
    name_src = payload.compare.new.file.name if payload.compare else payload.check.file.name  # type: ignore[union-attr]
    name = report_filename(name_src, compare=payload.compare is not None)
    return Response(
        content=data,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
