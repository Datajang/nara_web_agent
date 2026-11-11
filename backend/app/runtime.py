"""CLI·앱에서 실제 의존성을 조립한다. 테스트는 이 모듈을 쓰지 않고 가짜를 주입한다."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.config import Settings, get_settings
from app.db.session import Database
from app.deps import Deps
from app.files.download import HttpDownloader
from app.g2b.client import G2BClient
from app.usage.budget import DbCallBudget


@asynccontextmanager
async def real_deps(settings: Settings | None = None) -> AsyncIterator[Deps]:
    settings = settings or get_settings()
    db = Database(settings.database_url, settings.db_pool_size, settings.lock_pool_size)
    keys = {
        "regular": settings.nara_api_key.get_secret_value(),
        "prespec": settings.nara_prespec_api_key.get_secret_value(),
    }
    async with httpx.AsyncClient() as g2b_http, httpx.AsyncClient() as file_http:
        g2b = G2BClient(
            g2b_http,
            keys,
            page_size=settings.g2b_page_size,
            budget=DbCallBudget(db, settings.g2b_daily_call_budget),
        )
        downloader = HttpDownloader(
            file_http, settings.file_hosts, settings.file_max_mb * 1024 * 1024
        )
        try:
            yield Deps(db=db, g2b=g2b, llm=None, downloader=downloader, settings=settings)
        finally:
            await db.dispose()
