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
