"""테스트 공용 도우미: 실제 코드 경로(mapper → upsert)로 공고를 넣는다."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.collector.upsert import upsert_bids
from app.db.models import Bid
from app.deps import Deps
from app.g2b.mapper import to_record


async def seed(deps: Deps, source: str, *items: dict[str, Any]) -> list[int]:
    records = [to_record(source, it) for it in items]
    async with deps.db.transaction() as s:
        await upsert_bids(s, records)
    async with deps.db.session() as s:
        keys = [r.bid_key for r in records]
        rows = (await s.execute(select(Bid.bid_key, Bid.id).where(Bid.bid_key.in_(keys)))).all()
    ids = dict(rows)
    return [ids[k] for k in keys]
