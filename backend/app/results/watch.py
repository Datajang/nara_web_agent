"""결과 감시 행 만들기·맞추기 (설계 2026-11-25).

- 북마크(알림 켬)된 일반공고 중 개찰 예정이 있는 것만. 개찰 7일 넘게 지난 공고는 새로 만들지 않는다
- 정정공고로 차수·개찰일이 바뀌면 새 값으로 다시 기다린다(최종 결과가 나오기 전까지)
- sync_watches: 타이머가 매번 부른다. 기존 북마크와 수집기가 받은 정정공고를 여기서 맞춘다.
  개찰일이 없거나 7일 넘게 지난 북마크는 SQL에서 먼저 걸러 매번 다시 읽지 않는다
- 북마크 저장과 타이머가 동시에 만들어도 충돌하지 않게 INSERT ... ON CONFLICT DO NOTHING
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, BidResultWatch, Bookmark
from app.g2b.mapper import KST, parse_kst
from app.results.schedule import WATCH_MAX_AGE, next_check

ACTIVE = ("waiting", "opened")
NEGOTIATED = "협상"  # 낙찰방법(sucsfbidMthdNm)에 이 말이 있으면 결과가 제안서평가 뒤에 나온다


def is_negotiated(bid: Bid) -> bool:
    return NEGOTIATED in str((bid.raw or {}).get("sucsfbidMthdNm") or "")


def plan_next(w: BidResultWatch, bid: Bid, now: datetime) -> datetime | None:
    """감시 행의 다음 확인 시각(협상 공고면 평가 일시를 본다)."""
    return next_check(w.opening_at, now, w.stage, eval_at=w.eval_at, negotiated=is_negotiated(bid))


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
    first = at if now < at else now  # 개찰이 지났으면 바로 확인
    if w is None:
        if at < now - WATCH_MAX_AGE or next_check(at, now, "waiting") is None:
            return None
        await s.execute(
            insert(BidResultWatch)
            .values(
                bid_id=bid.id, stage="waiting", notice_ord=ord_, opening_at=at, next_check_at=first
            )
            .on_conflict_do_nothing(index_elements=["bid_id"])
        )
        # 다른 쪽이 먼저 만들었으면 그 행을 받아 아래에서 맞춘다
        w = await s.get_one(BidResultWatch, bid.id)
    if w.stage in ACTIVE and (w.notice_ord != ord_ or w.opening_at != at):
        w.notice_ord, w.opening_at, w.stage, w.opened_at = ord_, at, "waiting", None
        w.eval_at = w.eval_checked_at = None  # 차수가 바뀌면 평가 일시도 다시 읽는다
        w.next_check_at = first
        w.updated_at = now
    return w


def _maybe_watchable(now: datetime) -> ColumnElement[bool]:
    """개찰일 숫자(YYYYMMDD…)가 7일(+하루 여유) 안쪽인 공고만. 정확한 판정은 ensure_watch가 한다."""
    digits = func.regexp_replace(Bid.raw["opengDt"].astext, "[^0-9]", "", "g")
    cutoff = (now - WATCH_MAX_AGE - timedelta(days=1)).astimezone(KST).strftime("%Y%m%d")
    return func.left(digits, 8) >= cutoff


async def sync_watches(s: AsyncSession, now: datetime) -> int:
    """알림 켠 북마크의 감시 행을 만들고(새로 만든 수를 돌려줌) 진행 중 감시를 공고와 맞춘다."""
    missing = (
        await s.execute(
            select(Bid)
            .where(
                Bid.source == "regular",
                _maybe_watchable(now),
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
