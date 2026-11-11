"""수집기 모드 실행 (SPEC §5.3): backfill(과거로 1일 단위), incremental(30분 겹침), fill(요청 중
보충).

창 하나가 끝까지 성공해야 경계를 옮기고, 경계 갱신과 upsert는 같은 트랜잭션이다.
실패하면 경계는 그대로 두고 collector_runs.status=failed, 오류는 마스킹해 남긴다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, update

from app.collector import coverage
from app.collector.upsert import upsert_bids
from app.collector.windows import split_windows
from app.db.models import CollectorRun, UsageLog
from app.deps import Deps
from app.g2b.client import G2BClient, G2BError, count_calls
from app.g2b.mapper import to_record

log = logging.getLogger(__name__)
INCREMENTAL_OVERLAP = timedelta(minutes=30)
FILL_MAX_DAYS = 31
FILL_MAX_CALLS = 40


@dataclass
class RunResult:
    status: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    g2b_calls: int = 0
    error: str | None = None


def _client(deps: Deps) -> G2BClient:
    if deps.g2b is None:
        raise RuntimeError("G2B 클라이언트가 없습니다")
    return deps.g2b


async def _collect(
    deps: Deps,
    source: str,
    mode: str,
    windows: list[tuple[datetime, datetime]],
    max_calls: int | None = None,
) -> RunResult:
    """창들을 순서대로 수집. 창마다 upsert+경계 이동을 한 트랜잭션으로 커밋, 첫 실패에서 멈춘다."""
    g2b = _client(deps)
    result = RunResult(status="ok")
    async with deps.db.transaction() as s:
        run = CollectorRun(
            source=source,
            mode=mode,
            window_from=min(w[0] for w in windows),
            window_to=max(w[1] for w in windows),
        )
        s.add(run)
        await s.flush()
        run_id = run.id
    with count_calls() as calls:
        for start, end in windows:
            if max_calls is not None and calls.value >= max_calls:
                result.status, result.error = "failed", f"호출 상한 {max_calls}회 도달"
                break
            try:
                items = await g2b.fetch(source, start, end)
            except G2BError as e:
                result.status, result.error = "failed", g2b.mask(str(e))
                log.warning("수집 실패 %s %s %s~%s: %s", source, mode, start, end, result.error)
                break
            async with deps.db.transaction() as s:
                stats = await upsert_bids(s, [to_record(source, it) for it in items])
                await coverage.extend(s, source, start, end)
            result.fetched += len(items)
            result.inserted += stats.inserted
            result.updated += stats.updated
    result.g2b_calls = calls.value
    async with deps.db.transaction() as s:
        await s.execute(
            update(CollectorRun)
            .where(CollectorRun.id == run_id)
            .values(
                status=result.status,
                fetched=result.fetched,
                inserted=result.inserted,
                updated=result.updated,
                g2b_calls=result.g2b_calls,
                error=result.error,
                finished_at=func.now(),
            )
        )
        if mode != "fill":  # fill은 검색 요청의 usage_logs에 합산된다
            s.add(UsageLog(event="collector", g2b_calls=result.g2b_calls, cache={}))
    if mode != "fill":
        g2b.settle(result.g2b_calls)
    return result


async def backfill(deps: Deps, source: str, days: int) -> RunResult:
    """현재에서 과거로 1일 단위. 이미 덮은 구간은 건너뛰고 covered_from을 과거로 확장한다(재개
    가능)."""
    now = deps.clock()
    async with deps.db.session() as s:
        cov = await coverage.get(s, source)
    start = now - timedelta(days=days)
    # 최신 쪽 빈 구간(covered_to~now)을 먼저, 그다음 과거 쪽(start~covered_from)
    gaps = coverage.missing(cov, start, now)
    windows = [
        w
        for gap in sorted(gaps, key=lambda g: g[1], reverse=True)
        for w in split_windows(*gap, timedelta(days=1), newest_first=True)
    ]
    if not windows:
        return RunResult(status="ok")
    return await _collect(deps, source, "backfill", windows)


async def incremental(deps: Deps, source: str) -> RunResult:
    now = deps.clock()
    async with deps.db.session() as s:
        cov = await coverage.get(s, source)
    if cov is None:
        return await backfill(deps, source, days=1)
    windows = split_windows(cov.covered_to - INCREMENTAL_OVERLAP, now, timedelta(days=1))
    return await _collect(deps, source, "incremental", windows)


async def fill(deps: Deps, source: str, start: datetime, end: datetime) -> bool:
    """검색 창의 빈 구간을 보충. 31일·40회 상한을 넘으면 가능한 만큼만 하고 False(incomplete)."""
    async with deps.db.session() as s:
        cov = await coverage.get(s, source)
    gaps = coverage.missing(cov, start, end)
    if not gaps:
        return True
    complete = True
    left = timedelta(days=FILL_MAX_DAYS)
    windows: list[tuple[datetime, datetime]] = []
    # 최근 쪽 빈 구간을 먼저. 각 구간은 커버리지 경계에서 바깥쪽으로 채워야 연속 구간이 유지된다.
    for gap_start, gap_end in sorted(gaps, key=lambda g: g[1], reverse=True):
        newer_side = cov is not None and gap_start >= cov.covered_to
        if gap_end - gap_start > left:
            complete = False
            if newer_side:
                gap_end = gap_start + left  # covered_to에서 앞으로
            else:
                gap_start = gap_end - left  # covered_from(또는 요청 끝)에서 뒤로
        if gap_end <= gap_start:
            break
        windows += split_windows(gap_start, gap_end, timedelta(days=1), newest_first=not newer_side)
        left -= gap_end - gap_start
    result = await _collect(deps, source, "fill", windows, max_calls=FILL_MAX_CALLS)
    return complete and result.status == "ok"
