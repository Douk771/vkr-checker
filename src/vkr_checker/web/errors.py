"""Единый формат ошибок (API_CONTRACT.md §5): 13 кодов, подмена {"detail": ...}."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("vkr_checker.web")

# код -> (HTTP-статус, сообщение по умолчанию)
ERRORS: dict[str, tuple[int, str]] = {
    "bad_request": (400, "Некорректный запрос."),
    "missing_file": (400, "Выберите файл .docx."),
    "auth_required": (401, "Требуется вход по паролю."),
    "invalid_password": (401, "Неверный пароль."),
    "file_too_large": (413, "Файл или тело запроса превышает допустимый размер."),
    "unsupported_format": (
        415,
        "Нужен файл .docx. Сохраните документ в Word как .docx и загрузите снова.",
    ),
    "invalid_docx": (422, "Файл повреждён или не является документом Word (.docx)."),
    "docx_limits_exceeded": (422, "Файл превышает допустимые пределы для .docx."),
    "validation_error": (422, "Данные запроса не соответствуют схеме."),
    "too_many_attempts": (429, "Слишком много попыток. Повторите позже."),
    "server_busy": (503, "Сервис занят. Повторите запрос позже."),
    "processing_timeout": (503, "Файл обрабатывался слишком долго."),
    "internal_error": (500, "Не удалось обработать файл."),
}


class ApiError(Exception):
    """Ошибка API с кодом из контракта; сообщение — по-русски, без содержимого работы."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        field: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        if code not in ERRORS:
            raise ValueError(f"неизвестный код ошибки: {code}")
        super().__init__(code)
        self.code = code
        self.status = ERRORS[code][0]
        self.message = message or ERRORS[code][1]
        self.field = field
        self.retry_after = retry_after


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def request_id_of(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(err: ApiError, request_id: str | None) -> JSONResponse:
    body: dict[str, Any] = {"code": err.code, "message": err.message, "field": err.field}
    if request_id:
        body["request_id"] = request_id
    headers = {}
    if request_id:
        headers["X-Request-Id"] = request_id
    if err.retry_after is not None:
        headers["Retry-After"] = str(err.retry_after)
    return JSONResponse({"error": body}, status_code=err.status, headers=headers)


def _validation_field(exc: RequestValidationError) -> str | None:
    for item in exc.errors():
        loc = [str(p) for p in item.get("loc", ()) if p not in ("body", "query", "path")]
        if loc:
            return ".".join(loc)
    return None


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc, request_id_of(request))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # текст ошибок pydantic может содержать присланные значения, поэтому отдаём только путь поля
        err = ApiError("validation_error", field=_validation_field(exc))
        return error_response(err, request_id_of(request))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            err = ApiError("bad_request", "Ресурс не найден.")
            resp = error_response(err, request_id_of(request))
            resp.status_code = 404
            return resp
        if exc.status_code == 405:
            err = ApiError("bad_request", "Метод не поддерживается для этого пути.")
            resp = error_response(err, request_id_of(request))
            resp.status_code = 405
            if exc.headers:
                resp.headers.update(exc.headers)
            return resp
        return error_response(ApiError("bad_request"), request_id_of(request))
