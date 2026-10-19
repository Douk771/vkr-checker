"""Авторизация server-режима (API_CONTRACT.md §3): общий пароль, stateless-токен, cookie, Bearer.

Токен: `<exp>.<hmac_sha256(K, exp)>`, K = HMAC(пароль, boot_secret). boot_secret случайный при
старте, поэтому рестарт или смена пароля обнуляют все сессии. Пароль и токен в логи не пишутся.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import APIRouter, Request, Response
from pydantic import ValidationError

from vkr_checker.config import Settings
from vkr_checker.report.schema import ErrorResponse, LoginRequest

from .errors import ApiError

COOKIE_NAME = "vkr_session"
RATE_WINDOW_S = 60


class LoginRateLimiter:
    """Неудачные попытки входа на IP за скользящую минуту (память процесса)."""

    def __init__(self, limit_per_min: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit_per_min
        self._clock = clock
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, ip: str) -> deque[float]:
        q = self._fails[ip]
        now = self._clock()
        while q and now - q[0] >= RATE_WINDOW_S:
            q.popleft()
        if not q:
            self._fails.pop(ip, None)
        return q

    def retry_after(self, ip: str) -> int | None:
        """Секунды до разблокировки или None, если попытки ещё есть."""
        q = self._prune(ip)
        if len(q) < self._limit:
            return None
        return max(1, int(RATE_WINDOW_S - (self._clock() - q[0])) + 1)

    def register_failure(self, ip: str) -> None:
        self._prune(ip)
        self._fails[ip].append(self._clock())

    def reset(self, ip: str) -> None:
        self._fails.pop(ip, None)


class Authenticator:
    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        self.settings = settings
        self._clock = clock
        self._password = settings.password or ""
        boot_secret = secrets.token_bytes(32)
        self._key = hmac.new(self._password.encode(), boot_secret, hashlib.sha256).digest()
        self.limiter = LoginRateLimiter(settings.login_rate_per_min)

    # --- пароль и токены -------------------------------------------------------------------
    def check_password(self, candidate: str) -> bool:
        if not self.settings.auth_required:
            return True
        return hmac.compare_digest(candidate.encode(), self._password.encode())

    def _sign(self, exp: str) -> str:
        return hmac.new(self._key, exp.encode(), hashlib.sha256).hexdigest()

    def issue_token(self) -> str:
        exp = str(int(self._clock()) + self.settings.session_ttl_h * 3600)
        return f"{exp}.{self._sign(exp)}"

    def verify_token(self, token: str | None) -> bool:
        if not token:
            return False
        exp, sep, sig = token.partition(".")
        if not sep or not exp.isdigit():
            return False
        if not hmac.compare_digest(sig.encode(), self._sign(exp).encode()):
            return False
        return int(exp) > self._clock()

    # --- запрос ----------------------------------------------------------------------------
    def is_authenticated(self, request: Request) -> bool:
        """Local: авторизации нет, запрос авторизован. Server: валидная cookie или Bearer."""
        if not self.settings.auth_required:
            return True
        if self.verify_token(request.cookies.get(COOKIE_NAME)):
            return True
        header = request.headers.get("authorization", "")
        scheme, _, value = header.partition(" ")
        return scheme.lower() == "bearer" and self.check_password(value.strip())

    def client_ip(self, request: Request) -> str:
        if self.settings.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"


async def require_auth(request: Request) -> None:
    auth: Authenticator = request.app.state.authenticator
    if not auth.is_authenticated(request):
        raise ApiError("auth_required")


session_router = APIRouter(prefix="/api", tags=["auth"])


_ERR = {"model": ErrorResponse}
_LOGIN_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LoginRequest"}}},
    }
}


async def _read_login(request: Request) -> LoginRequest:
    try:
        return LoginRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise ApiError("validation_error", field="password") from None


@session_router.post(
    "/session",
    status_code=204,
    operation_id="createSession",
    responses={401: _ERR, 422: _ERR, 429: _ERR},
    openapi_extra=_LOGIN_BODY,
)
async def create_session(request: Request) -> Response:
    auth: Authenticator = request.app.state.authenticator
    body = await _read_login(request)
    if not auth.settings.auth_required:
        return Response(status_code=204)
    ip = auth.client_ip(request)
    wait = auth.limiter.retry_after(ip)
    if wait is not None:
        raise ApiError("too_many_attempts", retry_after=wait)
    if not auth.check_password(body.password):
        auth.limiter.register_failure(ip)
        raise ApiError("invalid_password")
    auth.limiter.reset(ip)
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE_NAME,
        auth.issue_token(),
        max_age=auth.settings.session_ttl_h * 3600,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api",
    )
    return response


@session_router.delete("/session", status_code=204, operation_id="deleteSession")
async def delete_session() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/api", secure=True, httponly=True, samesite="strict")
    return response
