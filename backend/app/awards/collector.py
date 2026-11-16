"""낙찰 수집기 `awards` (SPEC §15.4). 공고 수집기의 규칙(§5.3)을 그대로 따른다.

- 창: KST 자정에 맞춘 날짜 7개(7일). 한 창의 모든 페이지를 받아야 경계를 옮긴다
  (부분 수신은 G2BIncomplete → 실패).
- 커버리지: collector_coverage의 source='awards' 한 행(연속 구간 하나). 등록일시(rgstDt) 기준.
- 증분: 최근 14일을 다시 받아 수정·늦은 등록을 upsert로 흡수한다(+ covered_to 이후 빈 구간).
- 백필: org_settings.backfill_years(기본 5)만큼 과거로. 최신 쪽 빈 구간은 covered_to에서 앞으로,
  과거 쪽은 covered_from에서 뒤로 채워 구간이 끊기지 않게 한다.
  예산을 넘으면 멈추고 다음 실행에서 이어간다.
- collector_runs.mode는 기존 backfill·incremental을 쓴다. fill(요청 중 보충)은 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.awards.fields import clean_keywords
from app.awards.mapper import to_award
from app.awards.store import upsert_awards
from app.collector import coverage
from app.collector.runner import RunResult, Store, _collect
from app.collector.windows import split_dates
from app.db.models import OrgSettings
from app.deps import Deps

SOURCE = "awards"
MAX_DATES = 7  # 창 하나 = KST 날짜 7개 이하 (조회 기간 제한)
INCREMENTAL_SPAN = timedelta(days=14)
DAYS_PER_YEAR = 365


async def load_settings(deps: Deps) -> tuple[int, dict[str, list[str]]]:
    """(backfill_years, field_keywords). 행이 없으면 기본값."""
    async with deps.db.session() as s:
        row = await s.get(OrgSettings, 1)
    if row is None:
        return deps.settings.awards_backfill_years_default, {}
    return row.backfill_years, clean_keywords(row.field_keywords)


def award_store(keywords: dict[str, list[str]]) -> Store:
    async def store(s: AsyncSession, items: list[dict[str, Any]]) -> tuple[int, int]:
        rows = [r for r in (to_award(it) for it in items) if r is not None]
        stats = await upsert_awards(s, rows, keywords)
        return stats.inserted, stats.updated

    return store


def plan_backfill(
    cov: coverage.Coverage | None, start: datetime, now: datetime
) -> list[tuple[datetime, datetime]]:
    """채울 7일 창 목록(실행 순서). 각 창은 앞선 창들과 커버리지에 이어진다."""
    if cov is None:
        return split_dates(start, now, MAX_DATES, newest_first=True)
    windows: list[tuple[datetime, datetime]] = []
    if now > cov.covered_to:  # 최신 쪽: covered_to에서 앞으로
        windows += split_dates(cov.covered_to, now, MAX_DATES)
    if start < cov.covered_from:  # 과거 쪽: covered_from에서 뒤로
        windows += split_dates(start, cov.covered_from, MAX_DATES, newest_first=True)
    return windows


def plan_incremental(
    cov: coverage.Coverage | None, now: datetime, span: timedelta = INCREMENTAL_SPAN
) -> list[tuple[datetime, datetime]]:
    """최근 span(기본 14일)과 covered_to 이후 빈 구간. 커버리지와 겹치거나 이어지는 곳에서 시작."""
    if cov is None:
        return split_dates(now - span, now, MAX_DATES, newest_first=True)
    start = max(cov.covered_from, min(cov.covered_to, now - span))
    return split_dates(start, now, MAX_DATES)


async def backfill(deps: Deps, days: int | None = None) -> RunResult:
    years, keywords = await load_settings(deps)
    now = deps.clock()
    start = now - timedelta(days=days if days is not None else years * DAYS_PER_YEAR)
    async with deps.db.session() as s:
        cov = await coverage.get(s, SOURCE)
    windows = plan_backfill(cov, start, now)
    if not windows:
        return RunResult(status="ok")
    return await _collect(deps, SOURCE, "backfill", windows, store=award_store(keywords))


async def incremental(deps: Deps) -> RunResult:
    _, keywords = await load_settings(deps)
    now = deps.clock()
    async with deps.db.session() as s:
        cov = await coverage.get(s, SOURCE)
    windows = plan_incremental(cov, now)
    return await _collect(deps, SOURCE, "incremental", windows, store=award_store(keywords))
