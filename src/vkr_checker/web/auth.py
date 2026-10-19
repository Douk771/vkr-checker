"""Авторизация: пока только точка подключения, полная реализация - B-04.

До B-04 server-режим закрыт целиком (fail closed): защищённые эндпоинты дают 401.
"""

from __future__ import annotations

from fastapi import Request

from vkr_checker.config import Settings

from .errors import ApiError


class Authenticator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_authenticated(self, request: Request) -> bool:
        """Local: авторизации нет, запрос считается авторизованным. Server: до B-04 - нет."""
        return not self.settings.auth_required


async def require_auth(request: Request) -> None:
    auth: Authenticator = request.app.state.authenticator
    if not auth.is_authenticated(request):
        raise ApiError("auth_required")
