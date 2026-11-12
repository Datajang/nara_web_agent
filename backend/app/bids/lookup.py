"""공고번호로 열기 (SPEC §6.2 lookup). DB에 없으면 G2B 단건 조회로 가져와 저장한다.

일반 공고 번호를 먼저, 없으면 사전규격 등록번호로 본다(최대 2회 호출). 저장은 수집기와 같은
`upsert_bids`라 정정 차수 최대 행만 남는다. 호출 수는 usage_logs(event=search)에 남겨 일일
예산에 포함한다.
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.upsert import upsert_bids
from app.db.models import Bid, UsageLog
from app.deps import Deps
from app.g2b.client import count_calls
from app.g2b.mapper import to_record


async def find_in_db(s: AsyncSession, number: str) -> int | None:
    found = await s.scalar(
        select(Bid.id)
        .where((Bid.bid_no == number) | (Bid.prespec_reg_no == number))
        .order_by(Bid.revision.desc(), Bid.id.desc())
        .limit(1)
    )
    return int(found) if found is not None else None


async def fetch_from_g2b(deps: Deps, user_id: int | None, number: str) -> int | None:
    """G2B에서 찾아 저장하고 bid_id를 돌려준다. 없으면 None, 호출 실패는 G2BError."""
    g2b = deps.g2b
    assert g2b is not None
    started = time.monotonic()
    calls = 0
    try:
        with count_calls() as counter:
            try:
                for source in ("regular", "prespec"):
                    items = await g2b.lookup(source, number)
                    if items:
                        async with deps.db.transaction() as s:
                            await upsert_bids(s, [to_record(source, it) for it in items])
                        break
            finally:
                calls = counter.value
    finally:
        if calls:
            async with deps.db.transaction() as s:
                s.add(
                    UsageLog(
                        user_id=user_id,
                        event="search",
                        g2b_calls=calls,
                        duration_ms=int((time.monotonic() - started) * 1000),
                    )
                )
            g2b.settle(calls)
    async with deps.db.session() as s:
        return await find_in_db(s, number)
