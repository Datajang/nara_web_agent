"""DB 접속. 요청용 풀과 advisory lock 전용 풀을 분리한다 (§5.5)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    def __init__(self, url: str, pool_size: int = 10, lock_pool_size: int = 10) -> None:
        self.engine: AsyncEngine = create_async_engine(url, pool_size=pool_size, max_overflow=5)
        # 세션 레벨 advisory lock은 커넥션에 묶이므로 별도 풀에서 빌린다
        self.lock_engine: AsyncEngine = create_async_engine(
            url, pool_size=lock_pool_size, max_overflow=0
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as s:
            yield s

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as s, s.begin():
            yield s

    async def dispose(self) -> None:
        await self.engine.dispose()
        await self.lock_engine.dispose()
