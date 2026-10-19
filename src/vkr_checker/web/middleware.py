"""ASGI-middleware: X-Request-Id, перехват необработанных ошибок, лимит тела запроса."""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import ApiError, error_response, new_request_id

log = logging.getLogger("vkr_checker.web")


class RequestContextMiddleware:
    """Присваивает request_id, добавляет X-Request-Id в любой ответ, прячет трассировки."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            # в лог только тип исключения и id запроса: значения переменных и тексты работ не пишем
            log.error("необработанная ошибка request_id=%s type=%s", request_id, type(exc).__name__)
            if started:
                raise
            resp = error_response(ApiError("internal_error"), request_id)
            await resp(scope, receive, send_with_id)


class BodyLimitMiddleware:
    """Потоковый лимит тела по пути: считает байты на лету, не читая тело в память."""

    def __init__(self, app: ASGIApp, limits: dict[tuple[str, str], tuple[int, str]]) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        entry = self.limits.get((scope["method"], scope["path"]))
        if entry is None:
            await self.app(scope, receive, send)
            return
        limit, message = entry
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > limit
            except ValueError:
                too_big = False
            if too_big:
                rid = scope.get("state", {}).get("request_id")
                resp = error_response(ApiError("file_too_large", message), rid)
                await resp(scope, receive, send)
                return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise ApiError("file_too_large", message)
            return message

        await self.app(scope, limited_receive, send)
