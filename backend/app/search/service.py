"""DB-first 검색 (SPEC §5.4, §6.3). 커버리지 밖이면 fill(single-flight)로 채운 뒤 DB만 읽는다.

- cache_hit = 검색 전에 이미 커버리지 안이었는지. usage_logs.cache.bids_db에 그대로 기록.
- 예산 초과·fill 상한·락 대기 초과면 가진 데이터로 답하고 incomplete=True.
- '수집 중'(P1 결정): fill을 search_fill_wait_s만 기다리고, 끝나지 않으면 가진 결과와
  collecting=True로 바로 답한다. fill은 백그라운드에서 끝까지 돌고, 그동안의 G2B 호출은 끝난 뒤
  usage_logs(event=collector)로 따로 기록한다.
- 스냅샷(search_runs·search_run_items)은 최대 SNAPSHOT_MAX건 [가정]. 넘으면 truncated.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.collector import coverage, runner
from app.db.models import Bid, SearchRun, SearchRunItem, UsageLog
from app.deps import Deps
from app.g2b.client import CallCounter, count_calls
from app.pipeline.singleflight import LockTimeout, single_flight
from app.search.query import SearchQuery, build_query

log = logging.getLogger(__name__)
SOURCES = ("regular", "prespec")
SNAPSHOT_MAX = 500
_background: set[asyncio.Task[Any]] = set()


@dataclass
class Found:
    bids: list[Bid]
    incomplete: bool
    collecting: bool
    data_as_of: datetime | None
    cache_hit: bool
    g2b_calls: int


@dataclass
class SearchResult:
    run_id: int | None
    items: list[Bid]  # 첫 페이지(q.limit건)
    total: int  # 스냅샷에 저장된 건수
    truncated: bool
    incomplete: bool
    collecting: bool
    data_as_of: datetime | None
    cache_hit: bool
    g2b_calls: int


async def _fill(deps: Deps, source: str, start: datetime, end: datetime) -> bool:
    async def check() -> bool | None:
        async with deps.db.session() as s:
            c = await coverage.get(s, source)
        return True if c is not None and c.contains(start, end) else None

    async def compute() -> bool:
        return await runner.fill(deps, source, start, end)

    key = f"fill:{source}:{start:%Y%m%d%H%M}:{end:%Y%m%d%H%M}"
    try:
        complete, _ = await single_flight(deps.db, key, check, compute, wait_s=60)
    except LockTimeout:
        return False
    return complete


async def _log_late_calls(
    deps: Deps, tasks: list[asyncio.Task[bool]], calls: CallCounter, logged: int
) -> None:
    await asyncio.gather(*tasks, return_exceptions=True)
    late = calls.value - logged
    if late <= 0:
        return
    async with deps.db.transaction() as s:
        s.add(UsageLog(user_id=None, event="collector", g2b_calls=late))
    if deps.g2b is not None:
        deps.g2b.settle(late)


async def find_bids(deps: Deps, q: SearchQuery, cap: int) -> Found:
    """조건에 맞는 공고를 최대 cap건. 필요하면 G2B로 커버리지를 채운다."""
    now = deps.clock()
    start, end = q.window(now)
    sources = SOURCES if q.source == "all" else (q.source,)
    cache_hit, incomplete, collecting = True, False, False
    with count_calls() as calls:
        tasks: list[asyncio.Task[bool]] = []
        async with deps.db.session() as s:
            for src in sources:
                cov = await coverage.get(s, src)
                if cov is not None and cov.contains(start, end):
                    continue
                cache_hit = False
                if deps.g2b is None:
                    incomplete = True
                    continue
                tasks.append(asyncio.ensure_future(_fill(deps, src, start, end)))
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=deps.settings.search_fill_wait_s)
            for t in done:
                incomplete |= t.exception() is not None or not t.result()
                if t.exception() is not None:
                    log.warning("search fill failed: %s", type(t.exception()).__name__)
            if pending:
                incomplete = collecting = True
                bg = asyncio.ensure_future(_log_late_calls(deps, tasks, calls, calls.value))
                _background.add(bg)
                bg.add_done_callback(_background.discard)
        g2b_calls = calls.value

    async with deps.db.session() as s:
        bids = list((await s.execute(build_query(q, start, end, now, cap))).scalars())
        covs = [await coverage.get(s, src) for src in sources]
    data_as_of = min((c.covered_to for c in covs if c), default=None)
    return Found(bids, incomplete, collecting, data_as_of, cache_hit, g2b_calls)


async def search_bids(deps: Deps, user_id: int | None, q: SearchQuery) -> SearchResult:
    t0 = time.monotonic()
    found = await find_bids(deps, q, SNAPSHOT_MAX + 1)
    truncated = len(found.bids) > SNAPSHOT_MAX
    kept = found.bids[:SNAPSHOT_MAX]
    async with deps.db.transaction() as s:
        run_id = None
        if user_id is not None:
            run = SearchRun(
                user_id=user_id,
                kind="search",
                query=q.model_dump(mode="json", by_alias=True),
                result_count=len(kept),
                data_as_of=found.data_as_of,
                cache_hit=found.cache_hit,
            )
            s.add(run)
            await s.flush()
            run_id = run.id
            s.add_all(
                SearchRunItem(run_id=run.id, bid_id=b.id, rank=i)
                for i, b in enumerate(kept, start=1)
            )
        s.add(
            UsageLog(
                user_id=user_id,
                event="search",
                cache={"bids_db": found.cache_hit},
                g2b_calls=found.g2b_calls,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        )
    if deps.g2b is not None:
        deps.g2b.settle(found.g2b_calls)
    return SearchResult(
        run_id=run_id,
        items=kept[: q.limit],
        total=len(kept),
        truncated=truncated,
        incomplete=found.incomplete,
        collecting=found.collecting,
        data_as_of=found.data_as_of,
        cache_hit=found.cache_hit,
        g2b_calls=found.g2b_calls,
    )
