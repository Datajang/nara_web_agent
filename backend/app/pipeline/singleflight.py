"""같은 키의 작업을 동시에 하나만 실행 (SPEC §5.5).

- 락: 전용 풀 커넥션의 세션 레벨 pg_advisory_lock, 번호는 hashtextextended(key, 0).
- 대기: pg_try_advisory_lock 폴링으로 wait_s 넘으면 LockTimeout.
- 호출자가 취소돼도(SSE 끊김) 작업은 끝까지 진행된다: 락 구간 전체를 별도 태스크로 돌리고 shield로
  기다린다.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import text

from app.db.session import Database

T = TypeVar("T")
POLL_S = 0.05
_background: set[asyncio.Task[Any]] = set()


class LockTimeout(Exception):
    """다른 요청이 같은 작업을 처리 중. API는 오류가 아니라 '처리 중' 상태로 알린다."""


async def _locked(
    db: Database,
    key: str,
    check: Callable[[], Awaitable[T | None]],
    compute: Callable[[], Awaitable[T]],
    wait_s: float,
) -> tuple[T, bool]:
    deadline = time.monotonic() + wait_s
    async with db.lock_engine.connect() as conn:
        while not (
            await conn.execute(
                text("SELECT pg_try_advisory_lock(hashtextextended(:k, 0))"), {"k": key}
            )
        ).scalar():
            if time.monotonic() >= deadline:
                raise LockTimeout(key)
            await asyncio.sleep(POLL_S)
        try:
            if (hit := await check()) is not None:  # 락 획득 후 이중 확인
                return hit, True
            return await compute(), False
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:k, 0))"), {"k": key}
            )
            await conn.commit()


async def single_flight(
    db: Database,
    key: str,
    check: Callable[[], Awaitable[T | None]],
    compute: Callable[[], Awaitable[T]],
    wait_s: float = 120,
) -> tuple[T, bool]:
    """(값, cache_hit). check()는 캐시 조회(없으면 None), compute()는 실제 작업 후 DB 저장."""
    if (hit := await check()) is not None:
        return hit, True
    task = asyncio.ensure_future(_locked(db, key, check, compute, wait_s))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return await asyncio.shield(task)
