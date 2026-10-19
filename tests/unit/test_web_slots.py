import asyncio

import pytest

from vkr_checker.web.errors import ApiError
from vkr_checker.web.slots import SlotPool


def run(coro):
    return asyncio.run(coro)


def test_acquire_and_release_restores_capacity():
    async def scenario():
        pool = SlotPool(2)
        async with pool.acquire(1):
            assert pool.free == 1
            async with pool.acquire(1):
                assert pool.free == 0
        return pool.free

    assert run(scenario()) == 2


def test_compare_takes_both_slots_and_blocks_check():
    async def scenario():
        pool = SlotPool(2, wait_s=0.05)
        async with pool.acquire(2):
            with pytest.raises(ApiError) as exc:
                async with pool.acquire(1):
                    pass
        return exc.value

    err = run(scenario())
    assert err.code == "server_busy"
    assert err.status == 503
    assert err.retry_after


def test_waiter_gets_slot_after_release():
    async def scenario():
        pool = SlotPool(2, wait_s=2)
        order = []

        async def holder():
            async with pool.acquire(2):
                order.append("holder")
                await asyncio.sleep(0.05)

        async def waiter():
            await asyncio.sleep(0.01)
            async with pool.acquire(1):
                order.append("waiter")

        await asyncio.gather(holder(), waiter())
        return order, pool.free

    order, free = run(scenario())
    assert order == ["holder", "waiter"]
    assert free == 2


def test_slot_released_when_body_raises():
    async def scenario():
        pool = SlotPool(2)
        with pytest.raises(RuntimeError):
            async with pool.acquire(2):
                raise RuntimeError("boom")
        return pool.free

    assert run(scenario()) == 2


def test_request_larger_than_pool_is_programming_error():
    async def scenario():
        async with SlotPool(1).acquire(2):
            pass

    with pytest.raises(ValueError):
        run(scenario())
