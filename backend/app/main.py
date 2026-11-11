"""nara-web v2 API 진입점: `uvicorn app.main:app --workers 1` (SPEC §11.3).

설정은 환경변수(운영: systemd EnvironmentFile) 또는 NARA_ENV_FILE로만 읽는다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.app import create_app
from app.api.context import AppContext
from app.api.ratelimit import RateLimiter
from app.auth.mail import build_mailer
from app.config import Settings, get_settings
from app.db.session import Database
from app.deps import Deps, utcnow
from app.logging_setup import configure_logging


def build_context(settings: Settings) -> AppContext:
    db = Database(settings.database_url, settings.db_pool_size, settings.lock_pool_size)
    # G2B·LLM·다운로더는 P3에서 연결한다
    deps = Deps(db=db, g2b=None, llm=None, downloader=None, settings=settings, clock=utcnow)
    return AppContext(
        deps=deps,
        mailer=build_mailer(settings),
        limiter=RateLimiter(utcnow, settings.rate_limit_enabled),
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    ctx = build_context(settings or get_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await ctx.deps.db.dispose()

    return create_app(ctx, lifespan=lifespan)


configure_logging()
app = build_app()
