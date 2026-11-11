"""DB-first 검색 (SPEC §5.4). 커버리지 밖이면 fill(single-flight)로 채운 뒤 DB만 읽는다.

- cache_hit = 검색 전에 이미 커버리지 안이었는지. usage_logs.cache.bids_db에 그대로 기록.
- 예산 초과·fill 상한·락 대기 초과면 가진 데이터로 답하고 incomplete=True.
- user_id가 있으면 스냅샷(search_runs, search_run_items)을 같은 트랜잭션에 저장한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.collector import coverage, runner
from app.db.models import Bid, SearchRun, SearchRunItem, UsageLog
from app.deps import Deps
from app.g2b.client import count_calls
from app.pipeline.singleflight import LockTimeout, single_flight
from app.search.query import SearchQuery, build_query

SOURCES = ("regular", "prespec")


@dataclass
class SearchResult:
    run_id: int | None
    items: list[Bid]
    incomplete: bool
    data_as_of: datetime | None
    cache_hit: bool
    g2b_calls: int


async def _ensure_coverage(
    deps: Deps, source: str, start: datetime, end: datetime
) -> tuple[bool, bool]:
    """(이미 커버돼 있었나, 채운 뒤 완전한가)."""
    async with deps.db.session() as s:
        cov = await coverage.get(s, source)
    if cov is not None and cov.contains(start, end):
        return True, True
    if deps.g2b is None:
        return False, False

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
        complete = False
    return False, complete


async def search_bids(deps: Deps, user_id: int | None, q: SearchQuery) -> SearchResult:
    t0 = time.monotonic()
    now = deps.clock()
    start = now - timedelta(days=q.days)
    sources = SOURCES if q.source == "all" else (q.source,)
    cache_hit, incomplete = True, False
    with count_calls() as calls:
        for src in sources:
            was_covered, complete = await _ensure_coverage(deps, src, start, now)
            cache_hit &= was_covered
            incomplete |= not complete

    async with deps.db.transaction() as s:
        items = list((await s.execute(build_query(q, start, now, now))).scalars())
        covs = [await coverage.get(s, src) for src in sources]
        data_as_of = min((c.covered_to for c in covs if c), default=None)
        run_id = None
        if user_id is not None:
            run = SearchRun(
                user_id=user_id,
                kind="search",
                query=q.model_dump(),
                result_count=len(items),
                data_as_of=data_as_of,
                cache_hit=cache_hit,
            )
            s.add(run)
            await s.flush()
            run_id = run.id
            s.add_all(
                SearchRunItem(run_id=run.id, bid_id=b.id, rank=i)
                for i, b in enumerate(items, start=1)
            )
        s.add(
            UsageLog(
                user_id=user_id,
                event="search",
                cache={"bids_db": cache_hit},
                g2b_calls=calls.value,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        )
    if deps.g2b is not None:
        deps.g2b.settle(calls.value)
    return SearchResult(run_id, items, incomplete, data_as_of, cache_hit, calls.value)
