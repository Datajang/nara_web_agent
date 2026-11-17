"""CLI·앱에서 실제 의존성을 조립한다. 테스트는 이 모듈을 쓰지 않고 가짜를 주입한다."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.config import Settings, get_settings
from app.db.session import Database
from app.deps import Deps
from app.files.download import HttpDownloader
from app.g2b.client import AWARD_SOURCES, OPENINGS_SOURCE, G2BClient
from app.usage.budget import DbCallBudget


def g2b_keys(settings: Settings) -> dict[str, str]:
    """소스별 서비스키. 낙찰·계약은 NARA_AWARD_API_KEY, 없으면 NARA_API_KEY (§15.2)."""
    award_key = (
        settings.nara_award_api_key.get_secret_value() or settings.nara_api_key.get_secret_value()
    )
    return {
        "regular": settings.nara_api_key.get_secret_value(),
        "prespec": settings.nara_prespec_api_key.get_secret_value(),
        **dict.fromkeys(AWARD_SOURCES, award_key),
        OPENINGS_SOURCE: award_key,
    }


def build_g2b(http: httpx.AsyncClient, db: Database, settings: Settings) -> G2BClient:
    """전체 일일 예산 + 낙찰·계약 몫 예산(G2B_AWARDS_DAILY_BUDGET)을 함께 거는 클라이언트."""
    awards_budget = DbCallBudget(
        db, settings.g2b_awards_daily_budget, sources=AWARD_SOURCES, label="낙찰"
    )
    return G2BClient(
        http,
        g2b_keys(settings),
        page_size=settings.g2b_page_size,
        budget=DbCallBudget(db, settings.g2b_daily_call_budget),
        source_budgets={
            **dict.fromkeys(AWARD_SOURCES, awards_budget),
            # 개찰 결과 자동 수집(P12)은 낙찰 몫과 따로 센다
            OPENINGS_SOURCE: DbCallBudget(
                db,
                settings.g2b_openings_daily_budget,
                sources=[OPENINGS_SOURCE],
                label="개찰 결과",
            ),
        },
    )


@asynccontextmanager
async def real_deps(settings: Settings | None = None) -> AsyncIterator[Deps]:
    settings = settings or get_settings()
    db = Database(settings.database_url, settings.db_pool_size, settings.lock_pool_size)
    async with httpx.AsyncClient() as g2b_http, httpx.AsyncClient() as file_http:
        g2b = build_g2b(g2b_http, db, settings)
        downloader = HttpDownloader(
            file_http, settings.file_hosts, settings.file_max_mb * 1024 * 1024
        )
        try:
            yield Deps(db=db, g2b=g2b, llm=None, downloader=downloader, settings=settings)
        finally:
            await db.dispose()
