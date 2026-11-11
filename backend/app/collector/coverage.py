"""커버리지 불변식 (SPEC §5.3): 소스별 연속 구간 하나. 경계 갱신은 upsert와 같은 트랜잭션에서."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CollectorCoverage

# incremental이 10분~1시간 간격이라 covered_to가 조금 오래돼도 '안'으로 본다 [가정]
FRESHNESS = timedelta(hours=1)


@dataclass(frozen=True)
class Coverage:
    covered_from: datetime
    covered_to: datetime

    def contains(self, start: datetime, end: datetime, slack: timedelta = FRESHNESS) -> bool:
        return self.covered_from <= start and end <= self.covered_to + slack


async def get(session: AsyncSession, source: str) -> Coverage | None:
    row = await session.get(CollectorCoverage, source, populate_existing=True)
    return Coverage(row.covered_from, row.covered_to) if row else None


def missing(
    cov: Coverage | None, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """요청 창에서 커버 범위를 뺀 구간. 커버리지와 이어지도록 경계에서 바깥쪽으로 잡는다."""
    if cov is None:
        return [(start, end)]
    out = []
    if start < cov.covered_from:
        out.append((start, cov.covered_from))
    if end > cov.covered_to:
        out.append((cov.covered_to, end))
    return out


async def extend(session: AsyncSession, source: str, start: datetime, end: datetime) -> None:
    """[start, end)를 커버리지에 합친다. 기존 구간과 떨어져 있으면 거부(연속 구간 1개 유지)."""
    cov = await get(session, source)
    if cov is not None and (end < cov.covered_from or start > cov.covered_to):
        raise ValueError(f"커버리지와 떨어진 구간: {start}~{end} vs {cov}")
    new_from = min(start, cov.covered_from) if cov else start
    new_to = max(end, cov.covered_to) if cov else end
    stmt = insert(CollectorCoverage).values(source=source, covered_from=new_from, covered_to=new_to)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[CollectorCoverage.source],
            set_={"covered_from": new_from, "covered_to": new_to, "updated_at": func.now()},
        )
    )
