"""결과 감시 행 만들기·맞추기 (설계 2026-11-25).

- 북마크(알림 켬)된 일반공고 중 개찰 예정이 있는 것만. 개찰 7일 넘게 지난 공고는 새로 만들지 않는다
- 정정공고로 차수·개찰일이 바뀌면 새 값으로 다시 기다린다(최종 결과가 나오기 전까지)
- sync_watches: 타이머가 매번 부른다. 기존 북마크와 수집기가 받은 정정공고를 여기서 맞춘다
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, BidResultWatch, Bookmark
from app.g2b.mapper import parse_kst
from app.results.schedule import WATCH_MAX_AGE, next_check

ACTIVE = ("waiting", "opened")


def opening_of(bid: Bid) -> tuple[str, datetime] | None:
    """(차수, 개찰 시각 UTC). 개찰일이 없거나 해석이 안 되면 None."""
    raw = bid.raw or {}
    at = parse_kst(str(raw.get("opengDt") or ""))
    if at is None:
        return None
    return str(raw.get("bidNtceOrd") or "000"), at


async def ensure_watch(s: AsyncSession, bid: Bid, now: datetime) -> BidResultWatch | None:
    if bid.source != "regular":
        return None
    found = opening_of(bid)
    if found is None:
        return None
    ord_, at = found
    w = await s.get(BidResultWatch, bid.id)
    if w is None:
        nc = next_check(at, now)
        if at < now - WATCH_MAX_AGE or nc is None:
            return None
        w = BidResultWatch(
            bid_id=bid.id, stage="waiting", notice_ord=ord_, opening_at=at, next_check_at=nc
        )
        s.add(w)
        await s.flush()
        return w
    if w.stage in ACTIVE and (w.notice_ord != ord_ or w.opening_at != at):
        w.notice_ord, w.opening_at, w.stage, w.opened_at = ord_, at, "waiting", None
        w.next_check_at = next_check(at, now) or now
        w.updated_at = now
    return w


async def sync_watches(s: AsyncSession, now: datetime) -> int:
    """알림 켠 북마크의 감시 행을 만들고(새로 만든 수를 돌려줌) 진행 중 감시를 공고와 맞춘다."""
    missing = (
        await s.execute(
            select(Bid)
            .where(
                Bid.source == "regular",
                exists().where(Bookmark.bid_id == Bid.id, Bookmark.notify_result.is_(True)),
                ~exists().where(BidResultWatch.bid_id == Bid.id),
            )
            .order_by(Bid.id)
        )
    ).scalars()
    created = 0
    for bid in list(missing):
        if await ensure_watch(s, bid, now) is not None:
            created += 1
    active = (
        await s.execute(
            select(Bid)
            .join(BidResultWatch, BidResultWatch.bid_id == Bid.id)
            .where(BidResultWatch.stage.in_(ACTIVE))
        )
    ).scalars()
    for bid in list(active):
        await ensure_watch(s, bid, now)
    return created
