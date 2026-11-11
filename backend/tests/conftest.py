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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.app import create_app
from app.api.context import AppContext
from app.api.ratelimit import RateLimiter
from app.auth.mail import MemoryMailer
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
ORIGIN = "https://testserver"
TEST_SECRET = "test-secret-key-0123456789-abcdefghijklmnop"


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


# ---------- P2: API·인증 ----------


class Clock:
    """테스트가 앞으로 돌릴 수 있는 시계 (토큰 만료·잠금 해제)."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        self.now += timedelta(**kw)


def make_auth_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "env": "test",
        "secret_key": SecretStr(TEST_SECRET),
        "app_origin": ORIGIN,
        "cookie_secure": True,
        "mail_backend": "memory",
        "allowed_email_domains": "",
        "rate_limit_enabled": False,
        "g2b_daily_call_budget": 10_000,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@dataclass
class Api:
    app: FastAPI
    ctx: AppContext
    mailer: MemoryMailer
    clock: Clock
    db: Database

    def client(self, origin: str | None = ORIGIN) -> httpx.AsyncClient:
        headers = {"Origin": origin} if origin else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url=ORIGIN,
            headers=headers,
        )


def build_api(db: Database, settings: Settings, clock: Clock | None = None) -> Api:
    clock = clock or Clock()
    mailer = MemoryMailer()
    deps = Deps(db=db, g2b=None, llm=None, downloader=None, settings=settings, clock=clock)
    ctx = AppContext(
        deps=deps, mailer=mailer, limiter=RateLimiter(clock, settings.rate_limit_enabled)
    )
    return Api(app=create_app(ctx), ctx=ctx, mailer=mailer, clock=clock, db=db)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def api(db: Database, clock: Clock) -> Api:
    return build_api(db, make_auth_settings(), clock)


@pytest.fixture
async def client(api: Api) -> AsyncIterator[httpx.AsyncClient]:
    async with api.client() as c:
        yield c
