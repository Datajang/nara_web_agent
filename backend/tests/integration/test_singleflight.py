"""advisory lock 기반 single-flight (SPEC §5.5). 서로 다른 커넥션 두 개 이상을 실제로 쓴다."""

import asyncio

import pytest

from app.pipeline.singleflight import LockTimeout, single_flight


async def test_concurrent_same_key_computes_once(db):
    store: dict[str, int] = {}
    computed = 0

    async def check():
        return store.get("v")

    async def compute():
        nonlocal computed
        computed += 1
        await asyncio.sleep(0.2)
        store["v"] = 42
        return 42

    results = await asyncio.gather(*(single_flight(db, "test:k", check, compute) for _ in range(8)))
    assert computed == 1
    assert sorted(hit for _, hit in results) == [False] + [True] * 7
    assert {v for v, _ in results} == {42}


async def test_different_keys_run_in_parallel(db):
    started = asyncio.Event()
    both = asyncio.Event()
    count = 0

    async def compute():
        nonlocal count
        count += 1
        if count == 2:
            both.set()
        started.set()
        await asyncio.wait_for(both.wait(), 2)
        return 1

    async def miss():
        return None

    await asyncio.gather(
        single_flight(db, "k:a", miss, compute), single_flight(db, "k:b", miss, compute)
    )
    assert count == 2


async def test_lock_timeout(db):
    release = asyncio.Event()

    async def slow():
        await release.wait()
        return 1

    async def miss():
        return None

    holder = asyncio.create_task(single_flight(db, "k:slow", miss, slow))
    await asyncio.sleep(0.1)
    with pytest.raises(LockTimeout):
        await single_flight(db, "k:slow", miss, slow, wait_s=0.3)
    release.set()
    await holder


async def test_waiter_is_told_once_that_it_is_waiting(db):
    """2026-11-16 리뷰: 다른 요청이 같은 요약을 만드는 동안 진행률이 안 와 로딩바가 10%에 멈춤
    → 기다리기 시작할 때 on_wait를 한 번 부른다(앞선 요청은 부르지 않음)."""
    store: dict[str, int] = {}
    waits: list[str] = []
    release = asyncio.Event()

    async def check():
        return store.get("v")

    async def compute():
        await release.wait()
        store["v"] = 1
        return 1

    first = asyncio.create_task(
        single_flight(db, "test:w", check, compute, on_wait=lambda: waits.append("a"))
    )
    await asyncio.sleep(0.2)
    second = asyncio.create_task(
        single_flight(db, "test:w", check, compute, on_wait=lambda: waits.append("b"))
    )
    await asyncio.sleep(0.3)
    release.set()
    await asyncio.gather(first, second)
    assert waits == ["b"]
