"""공용 픽스처. DB 테스트는 실제 PostgreSQL을 쓴다 (SPEC §12.1, SQLite 금지).

TEST_DATABASE_URL 환경변수(CI) 또는 backend/.env의 TEST_DATABASE_URL만 읽는다.
저장소 루트 .env(서비스키)는 읽지 않는다. 스키마는 Alembic 마이그레이션으로 만든다.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.db.session import Database
from app.deps import Deps
from app.g2b.client import G2BClient
from tests.fakes.downloader import FakeDownloader
from tests.fakes.g2b import FakeG2B
from tests.fakes.llm import FakeLLM

BACKEND = Path(__file__).resolve().parents[1]
TEST_KEYS = {"regular": "TEST-SERVICE-KEY-REGULAR-1234", "prespec": "TEST-SERVICE-KEY-PRESPEC-5678"}
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)  # KST 15:00


def _test_db_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or dotenv_values(BACKEND / ".env").get(
        "TEST_DATABASE_URL"
    )


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_db_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL 없음: PostgreSQL 테스트 건너뜀")

    async def reset() -> None:
        eng = create_async_engine(url)
        async with eng.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await eng.dispose()

    asyncio.run(reset())
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=BACKEND,
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
async def db(db_url: str) -> AsyncIterator[Database]:
    database = Database(db_url, pool_size=5, lock_pool_size=12)
    yield database
    async with database.engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables"
                    " WHERE schemaname='public' AND tablename <> 'alembic_version'"
                )
            )
        ).scalars()
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    await database.dispose()


@pytest.fixture
def fake_g2b() -> FakeG2B:
    return FakeG2B()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_downloader() -> FakeDownloader:
    return FakeDownloader()


@pytest.fixture
def settings() -> Settings:
    return Settings(g2b_daily_call_budget=10_000)


@pytest.fixture
async def deps(
    db: Database,
    fake_g2b: FakeG2B,
    fake_llm: FakeLLM,
    fake_downloader: FakeDownloader,
    settings: Settings,
) -> AsyncIterator[Deps]:
    http = fake_g2b.http_client()
    g2b = G2BClient(http, TEST_KEYS, page_size=100, retry_delays=(0, 0, 0))
    yield Deps(
        db=db,
        g2b=g2b,
        llm=fake_llm,
        downloader=fake_downloader,
        settings=settings,
        clock=lambda: NOW,
    )
    await http.aclose()
