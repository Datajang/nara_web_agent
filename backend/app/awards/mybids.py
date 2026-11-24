"""우리 투찰 결과: 낙찰·탈락 (P12, docs/decisions/2026-11-17-p12a-opening-ranks.md).

- 항목 = 우리가 낙찰한 낙찰 행 + 불러온 개찰 결과에 우리 사업자번호가 있는 낙찰 행
  (공고·차수·분류·재입찰)
- 결과: won(낙찰업체가 우리) / lost(순위 있음) / disqualified(순위 없음 = 부적격·탈락, 사유는 비고)
- 순위를 투찰금액으로 추정하지 않는다(P12-a: 빈칸은 누락이 아니라 부적격)
- 유효 업체 수 = 그 공고에서 순위가 있는 업체 수
- 필터(2026-11-24): 기간(등록일 KST, 끝 날 포함)·사업명(띄어쓰기 무시). 목록과 건수에 같은 조건
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import and_, func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.awards.service import kst_start
from app.db.models import Bid, BidAward, BidParticipant, BidParticipantFetch
from app.search.query import title_contains

Result = Literal["won", "lost", "disqualified"]
Filter = Literal["all", "won", "lost"]
AwardKey = tuple[str, str, str, str]


@dataclass
class MyBid:
    award: BidAward
    us: BidParticipant | None  # 개찰 결과의 우리 행(불러오지 않았으면 None)
    bid_id: int | None
    valid_count: int | None = None  # 순위 있는 업체 수(개찰 결과가 있을 때)
    rows: int | None = None  # 개찰 결과 참가 행 수
    fetched: bool = False  # 개찰 결과를 불러온 공고인가

    def result(self, us_bizno: str) -> Result:
        if self.award.bizno == us_bizno:
            return "won"
        return "lost" if self.us is not None and self.us.rank is not None else "disqualified"


def key_of(a: BidAward) -> AwardKey:
    return (a.bid_ntce_no, a.bid_ntce_ord, a.bid_clsfc_no, a.rbid_no)


def _us_join(us: str) -> tuple[Any, Any]:
    p = aliased(BidParticipant)
    on = and_(
        p.bid_ntce_no == BidAward.bid_ntce_no,
        p.bid_ntce_ord == BidAward.bid_ntce_ord,
        p.bid_clsfc_no == BidAward.bid_clsfc_no,
        p.rbid_no == BidAward.rbid_no,
        p.bizno == us,
    )
    return p, on


def _result_cond(p: Any, us: str, flt: Filter) -> Any:
    won = BidAward.bizno == us
    took_part = p.bizno.is_not(None)
    if flt == "won":
        return won
    if flt == "lost":
        return and_(took_part, BidAward.bizno.is_distinct_from(us))
    return or_(won, took_part)


@dataclass(frozen=True)
class Narrow:
    """목록·건수를 좁히는 조건. 기간은 등록일(KST) 기준이고 끝 날을 포함한다."""

    date_from: date | None = None
    date_to: date | None = None
    q: str | None = None

    def conds(self) -> list[Any]:
        out: list[Any] = []
        if self.date_from is not None:
            out.append(BidAward.registered_at >= kst_start(self.date_from))
        if self.date_to is not None:
            out.append(BidAward.registered_at < kst_start(self.date_to + timedelta(days=1)))
        if self.q and (title := title_contains(self.q, BidAward.title)) is not None:
            out.append(title)
        return out


NO_NARROW = Narrow()  # 조건 없음(불변이라 기본값으로 함께 쓴다)


async def counts(s: AsyncSession, us: str, narrow: Narrow = NO_NARROW) -> dict[str, int]:
    p, on = _us_join(us)
    base = select(func.count()).select_from(BidAward).outerjoin(p, on).where(*narrow.conds())
    won = await s.scalar(base.where(_result_cond(p, us, "won")))
    lost = await s.scalar(base.where(_result_cond(p, us, "lost")))
    return {"won": int(won or 0), "lost": int(lost or 0), "all": int(won or 0) + int(lost or 0)}


async def _stats(s: AsyncSession, keys: Sequence[AwardKey]) -> dict[AwardKey, tuple[int, int]]:
    """공고 키별 (순위 있는 업체 수, 참가 행 수)."""
    if not keys:
        return {}
    bp = BidParticipant
    rows = await s.execute(
        select(bp.bid_ntce_no, bp.bid_ntce_ord, bp.bid_clsfc_no, bp.rbid_no)
        .add_columns(func.count(bp.rank), func.count())
        .where(tuple_(bp.bid_ntce_no, bp.bid_ntce_ord, bp.bid_clsfc_no, bp.rbid_no).in_(keys))
        .group_by(bp.bid_ntce_no, bp.bid_ntce_ord, bp.bid_clsfc_no, bp.rbid_no)
    )
    return {(a, b, c, d): (int(v), int(n)) for a, b, c, d, v, n in rows.all()}


async def _fetched(s: AsyncSession, keys: Sequence[AwardKey]) -> set[tuple[str, str]]:
    notices = list({(k[0], k[1]) for k in keys})
    if not notices:
        return set()
    f = BidParticipantFetch
    rows = await s.execute(
        select(f.bid_ntce_no, f.bid_ntce_ord).where(
            tuple_(f.bid_ntce_no, f.bid_ntce_ord).in_(notices)
        )
    )
    return {(a, b) for a, b in rows.all()}


async def _enrich(s: AsyncSession, items: list[MyBid]) -> list[MyBid]:
    keys = [key_of(i.award) for i in items]
    stats = await _stats(s, keys)
    done = await _fetched(s, keys)
    for i in items:
        k = key_of(i.award)
        i.fetched = (k[0], k[1]) in done
        if k in stats:
            i.valid_count, i.rows = stats[k]
        elif i.fetched:
            i.valid_count, i.rows = 0, 0
    return items


async def page(
    s: AsyncSession,
    us: str,
    flt: Filter = "all",
    cursor: tuple[datetime, int] | None = None,
    limit: int = 30,
    narrow: Narrow = NO_NARROW,
) -> tuple[list[MyBid], tuple[datetime, int] | None]:
    """등록일시 최신순 한 쪽과 다음 쪽 커서(등록일시, 낙찰 id)."""
    p, on = _us_join(us)
    conds = [_result_cond(p, us, flt), *narrow.conds()]
    if cursor is not None:
        ts, last_id = cursor
        conds.append(
            or_(
                BidAward.registered_at < ts,
                and_(BidAward.registered_at == ts, BidAward.id < last_id),
            )
        )
    rows = (
        await s.execute(
            select(BidAward, p, Bid.id)
            .outerjoin(p, on)
            .outerjoin(Bid, Bid.bid_key == literal("regular:") + BidAward.bid_ntce_no)
            .where(*conds)
            .order_by(BidAward.registered_at.desc(), BidAward.id.desc())
            .limit(limit + 1)
        )
    ).all()
    items = [MyBid(a, u, bid_id) for a, u, bid_id in rows[:limit]]
    nxt = (items[-1].award.registered_at, items[-1].award.id) if len(rows) > limit else None
    return await _enrich(s, items), nxt


async def one(s: AsyncSession, us: str, key: AwardKey) -> MyBid | None:
    p, on = _us_join(us)
    row = (
        await s.execute(
            select(BidAward, p, Bid.id)
            .outerjoin(p, on)
            .outerjoin(Bid, Bid.bid_key == literal("regular:") + BidAward.bid_ntce_no)
            .where(
                BidAward.bid_ntce_no == key[0],
                BidAward.bid_ntce_ord == key[1],
                BidAward.bid_clsfc_no == key[2],
                BidAward.rbid_no == key[3],
            )
        )
    ).first()
    if row is None:
        return None
    (item,) = await _enrich(s, [MyBid(row[0], row[1], row[2])])
    return item


async def participants(s: AsyncSession, key: AwardKey) -> list[BidParticipant]:
    """참가업체: 순위순, 순위 없는(부적격) 업체는 뒤에 종합점수·투찰금액 순."""
    bp = BidParticipant
    rows = await s.execute(
        select(bp)
        .where(
            bp.bid_ntce_no == key[0],
            bp.bid_ntce_ord == key[1],
            bp.bid_clsfc_no == key[2],
            bp.rbid_no == key[3],
        )
        .order_by(
            bp.rank.asc().nulls_last(),
            bp.total_score.desc().nulls_last(),
            bp.bid_amount.asc().nulls_last(),
            bp.bizno,
        )
    )
    return list(rows.scalars())


async def award_counts(s: AsyncSession, biznos: Sequence[str]) -> dict[str, int]:
    """업체별 수집된 낙찰 수(경쟁사 정보 한 줄)."""
    if not biznos:
        return {}
    rows = await s.execute(
        select(BidAward.bizno, func.count())
        .where(BidAward.bizno.in_(list(set(biznos))))
        .group_by(BidAward.bizno)
    )
    return {b: int(n) for b, n in rows.all() if b is not None}


async def scan_status(s: AsyncSession) -> tuple[datetime | None, int, int]:
    """(개찰 결과를 처음 받은 시각, 받은 공고 수, 낙찰 공고 수)."""
    f = BidParticipantFetch
    since, done = (await s.execute(select(func.min(f.fetched_at), func.count()))).one()
    total = await s.scalar(
        select(func.count()).select_from(
            select(BidAward.bid_ntce_no, BidAward.bid_ntce_ord).distinct().subquery()
        )
    )
    return since, int(done or 0), int(total or 0)
