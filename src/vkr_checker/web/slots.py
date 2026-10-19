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

    async def take(self, n: int = 1) -> None:
        """Занимает n слотов (ожидание до wait_s, иначе server_busy). Вернуть через give()."""
        if n > self.capacity:
            raise ValueError("запрошено больше слотов, чем есть в пуле")
        cond = self._condition()
        taken = False

        async def _wait() -> None:
            nonlocal taken
            async with cond:
                await cond.wait_for(lambda: self._free >= n)
                self._free -= n
                taken = True

        try:
            await asyncio.wait_for(_wait(), timeout=self.wait_s)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            if taken:  # py3.10: wait_for мог потерять уже занятый слот
                await self.give(n)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise ApiError("server_busy", retry_after=RETRY_AFTER_S) from None

    async def give(self, n: int = 1) -> None:
        async with self._condition():
            self._free += n
            self._condition().notify_all()

    @asynccontextmanager
    async def acquire(self, n: int = 1) -> AsyncIterator[None]:
        await self.take(n)
        try:
            yield
        finally:
            await self.give(n)
