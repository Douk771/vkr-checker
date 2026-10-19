"""Слоты обработки: check = 1, compare = 2; ожидание слота до 30 с, иначе server_busy."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .errors import ApiError

SLOT_WAIT_S = 30.0
RETRY_AFTER_S = 10


class SlotPool:
    def __init__(self, capacity: int, wait_s: float = SLOT_WAIT_S) -> None:
        if capacity < 1:
            raise ValueError("capacity >= 1")
        self.capacity = capacity
        self.wait_s = wait_s
        self._free = capacity
        self._cond: asyncio.Condition | None = None

    def _condition(self) -> asyncio.Condition:
        if self._cond is None:  # создаётся лениво, внутри работающего цикла событий
            self._cond = asyncio.Condition()
        return self._cond

    @property
    def free(self) -> int:
        return self._free

    @asynccontextmanager
    async def acquire(self, n: int = 1) -> AsyncIterator[None]:
        if n > self.capacity:
            raise ValueError("запрошено больше слотов, чем есть в пуле")
        cond = self._condition()

        async def _wait() -> None:
            async with cond:
                await cond.wait_for(lambda: self._free >= n)
                self._free -= n

        try:
            await asyncio.wait_for(_wait(), timeout=self.wait_s)
        except asyncio.TimeoutError:
            raise ApiError("server_busy", retry_after=RETRY_AFTER_S) from None
        try:
            yield
        finally:
            async with cond:
                self._free += n
                cond.notify_all()
