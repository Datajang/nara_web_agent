"""nara-web v2 API 진입점: `uvicorn app.main:app --workers 1` (SPEC §11.3).

설정은 환경변수(운영: systemd EnvironmentFile) 또는 NARA_ENV_FILE로만 읽는다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.app import create_app
from app.api.context import AppContext
from app.api.ratelimit import RateLimiter
from app.auth.mail import build_mailer
from app.config import Settings, get_settings
from app.db.session import Database
from app.deps import Deps, utcnow
from app.files.download import HttpDownloader
from app.g2b.client import G2BClient
from app.llm.base import LLMClient
from app.llm.client import OpenAICompatLLM
from app.llm.fake import FakeLLM
from app.logging_setup import configure_logging
from app.usage.budget import DbCallBudget


def build_llm(settings: Settings) -> LLMClient | None:
    """LLM_BACKEND: vllm(운영), fake(개발 화면용, 운영 금지), none(LLM 없이 기동)."""
    if settings.llm_backend == "none":
        return None
    if settings.llm_backend == "fake":
        return FakeLLM(model_id="fake-dev")
    return OpenAICompatLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        model_id=settings.llm_model_id,
        timeout_s=settings.llm_timeout_s,
        max_concurrency=settings.llm_max_concurrency,
    )


def build_context(settings: Settings) -> AppContext:
    db = Database(settings.database_url, settings.db_pool_size, settings.lock_pool_size)
    g2b_http, file_http = httpx.AsyncClient(), httpx.AsyncClient()
    keys = {
        "regular": settings.nara_api_key.get_secret_value(),
        "prespec": settings.nara_prespec_api_key.get_secret_value(),
    }
    g2b = (
        G2BClient(
            g2b_http,
            keys,
            page_size=settings.g2b_page_size,
            budget=DbCallBudget(db, settings.g2b_daily_call_budget),
        )
        if any(keys.values())
        else None  # 서비스키가 없으면 DB에 있는 데이터만으로 답한다
    )
    downloader = HttpDownloader(file_http, settings.file_hosts, settings.file_max_mb * 1024 * 1024)
    llm = build_llm(settings)
    deps = Deps(db=db, g2b=g2b, llm=llm, downloader=downloader, settings=settings, clock=utcnow)
    closers: list[Callable[[], Awaitable[None]]] = [g2b_http.aclose, file_http.aclose]
    if isinstance(llm, OpenAICompatLLM):
        closers.append(llm.close)
    return AppContext(
        deps=deps,
        mailer=build_mailer(settings),
        limiter=RateLimiter(utcnow, settings.rate_limit_enabled),
        closers=closers,
    )


def build_app(settings: Settings | None = None) -> FastAPI:
    ctx = build_context(settings or get_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for close in ctx.closers:
            await close()
        await ctx.deps.db.dispose()

    return create_app(ctx, lifespan=lifespan)


configure_logging()
app = build_app()
