"""개찰 결과 저장: 한 공고 참가 업체가 많아도 PostgreSQL 인자 상한(32767)에 걸리지 않는다."""

from sqlalchemy import func, select

from app.awards import participants
from app.db.models import BidParticipant, BidParticipantFetch
from tests.fakes.g2b import opening_item


async def test_store_many_participants_in_one_notice(db):
    # 13칸 × 3,000행 = 39,000 인자 → 한 번에 넣으면 asyncpg가 거부한다 (운영 2026-11-24)
    n = 3000
    items = [opening_item("R26BK00000001", f"{1000000000 + i}", rank=str(i + 1)) for i in range(n)]
    async with db.transaction() as s:
        stored = await participants.store(s, ("R26BK00000001", "000"), items)
    assert stored == n
    async with db.session() as s:
        rows = await s.scalar(select(func.count()).select_from(BidParticipant))
        fetch = await s.scalar(select(BidParticipantFetch.row_count))
    assert rows == n
    assert fetch == n
