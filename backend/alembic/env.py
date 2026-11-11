"""Alembic 환경. URL은 `-x url=...` 또는 환경변수 DATABASE_URL (NARA_ENV_FILE 경유)."""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

import app.db.models  # noqa: F401  (모델 등록)
from alembic import context
from app.config import get_settings
from app.db.base import Base

target_metadata = Base.metadata


def _url() -> str:
    return context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is not None:  # 테스트가 커넥션을 직접 넘긴 경우
        _run(connectable)
        return
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
