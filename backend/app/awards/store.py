"""낙찰 저장: companies·bid_awards 멱등 upsert (SPEC §15.3·§15.4).

- 고유키 (공고번호, 차수, 분류, 재입찰). 같은 창을 다시 받아도 행이 늘지 않는다.
- 같은 낙찰의 내용이 바뀌면(협상 후 낙찰자 변경 등) 그 행을 갱신한다.
  is_joint는 계약정보(bid_joint_members)가 있으면 true로 맞춘다(mark_joint, 수집 순서와 무관).
- 업체는 사업자번호로 upsert. 이름은 더 최근 낙찰의 상호로만 바꾼다(백필은 과거로 가므로).
- estimated_price는 같은 공고가 bids에 있을 때 추정가격(presmptPrce)을 가져오고, award_ratio는
  낙찰금액·추정가격이 둘 다 있을 때만 계산한다 (§15.1 원칙 4). 비율이 RATIO_MAX를 넘으면 추정가격이
  잘못된 값이라 비운다(실측 2026-11-17: 추정가격 1원 → 비율 16,490, 열 넘침으로 백필 배치 실패).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import case, exists, func, literal_column, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.awards.fields import classify
from app.awards.mapper import AwardRow, normalize_name
from app.db.models import Bid, BidAward, BidJointMember, Company
from app.g2b.mapper import _amount

# asyncpg 인자 상한(32767)을 넘지 않게 나눠 넣는다 (행당 약 18개)
CHUNK = 500
_UPDATABLE = (
    "bizno",
    "winner_name",
    "title",
    "award_amount",
    "g2b_award_rate",
    "estimated_price",
    "award_ratio",
    "participant_count",
    "dminstt_cd",
    "dminstt_name",
    "opened_at",
    "awarded_on",
    "registered_at",
    "fields",
)


@dataclass
class AwardStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    unidentified: int = 0  # 사업자번호 없음(업체 통계 제외)


# 낙찰금액(부가세 포함)/추정가격(부가세 제외)은 보통 0.6~1.2 (개발 DB 99%가 1.1 이하)
RATIO_MAX = Decimal(2)


def award_ratio(amount: int | None, estimated: int | None) -> Decimal | None:
    if not amount or not estimated or estimated <= 0:
        return None
    ratio = (Decimal(amount) / Decimal(estimated)).quantize(Decimal("0.00001"), ROUND_HALF_UP)
    return ratio if ratio <= RATIO_MAX else None


def _dedupe(rows: Iterable[AwardRow]) -> list[AwardRow]:
    """한 배치 안에서 같은 키는 등록일시가 가장 늦은 행만."""
    best: dict[tuple[str, str, str, str], AwardRow] = {}
    for r in rows:
        cur = best.get(r.key)
        if cur is None or r.registered_at >= cur.registered_at:
            best[r.key] = r
    return list(best.values())


async def estimated_prices(session: AsyncSession, bid_nos: Iterable[str]) -> dict[str, int]:
    """bids(일반공고)의 추정가격. 없는 공고는 빠진다."""
    keys = [f"regular:{n}" for n in set(bid_nos)]
    if not keys:
        return {}
    rows = await session.execute(
        select(Bid.bid_no, Bid.raw["presmptPrce"].astext).where(Bid.bid_key.in_(keys))
    )
    out: dict[str, int] = {}
    for no, price in rows.all():
        v = _amount(price)
        if v:
            out[no] = v
    return out


async def upsert_companies(session: AsyncSession, rows: Sequence[AwardRow]) -> None:
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.bizno is None or not r.winner_name:
            continue
        cur = agg.get(r.bizno)
        if cur is None:
            agg[r.bizno] = {
                "bizno": r.bizno,
                "name": r.winner_name,
                "name_norm": normalize_name(r.winner_name),
                "first_seen_at": r.seen_at,
                "last_seen_at": r.seen_at,
            }
            continue
        cur["first_seen_at"] = min(cur["first_seen_at"], r.seen_at)
        if r.seen_at >= cur["last_seen_at"]:
            cur.update(
                last_seen_at=r.seen_at, name=r.winner_name, name_norm=normalize_name(r.winner_name)
            )
    values = sorted(agg.values(), key=lambda v: v["bizno"])  # 잠금 순서 고정
    for i in range(0, len(values), CHUNK):
        ins = insert(Company).values(values[i : i + CHUNK])
        ex = ins.excluded
        newer = ex.last_seen_at >= Company.last_seen_at
        await session.execute(
            ins.on_conflict_do_update(
                index_elements=[Company.bizno],
                set_={
                    "first_seen_at": func.least(Company.first_seen_at, ex.first_seen_at),
                    "last_seen_at": func.greatest(Company.last_seen_at, ex.last_seen_at),
                    "name": case((newer, ex.name), else_=Company.name),
                    "name_norm": case((newer, ex.name_norm), else_=Company.name_norm),
                    "updated_at": func.now(),
                },
            )
        )


async def upsert_awards(
    session: AsyncSession, rows: Sequence[AwardRow], keywords: Mapping[str, list[str]]
) -> AwardStats:
    stats = AwardStats()
    rows = _dedupe(rows)
    if not rows:
        return stats
    await upsert_companies(session, rows)
    prices = await estimated_prices(session, (r.bid_ntce_no for r in rows))
    values = []
    for r in sorted(rows, key=lambda r: r.key):
        est = prices.get(r.bid_ntce_no)
        stats.unidentified += r.bizno is None
        values.append(
            {
                "bid_ntce_no": r.bid_ntce_no,
                "bid_ntce_ord": r.bid_ntce_ord,
                "bid_clsfc_no": r.bid_clsfc_no,
                "rbid_no": r.rbid_no,
                "bizno": r.bizno,
                "winner_name": r.winner_name,
                "title": r.title,
                "award_amount": r.award_amount,
                "g2b_award_rate": r.g2b_award_rate,
                "estimated_price": est,
                "award_ratio": award_ratio(r.award_amount, est),
                "participant_count": r.participant_count,
                "dminstt_cd": r.dminstt_cd,
                "dminstt_name": r.dminstt_name,
                "opened_at": r.opened_at,
                "awarded_on": r.awarded_on,
                "registered_at": r.registered_at,
                "fields": classify(r.title, keywords),
            }
        )
    changed = 0
    for i in range(0, len(values), CHUNK):
        ins = insert(BidAward).values(values[i : i + CHUNK])
        ex = ins.excluded
        stmt: Any = ins.on_conflict_do_update(
            constraint="uq_bid_awards_bid_ntce_no_bid_ntce_ord_bid_clsfc_no_rbid_no",
            set_={**{c: getattr(ex, c) for c in _UPDATABLE}, "updated_at": func.now()},
            where=or_(*(getattr(BidAward, c).is_distinct_from(getattr(ex, c)) for c in _UPDATABLE)),
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        flags = (await session.execute(stmt)).scalars().all()
        stats.inserted += sum(1 for f in flags if f)
        changed += len(flags)
    stats.updated = changed - stats.inserted
    stats.unchanged = len(values) - changed
    await mark_joint(session, {r.bid_ntce_no for r in rows})
    return stats


async def mark_joint(session: AsyncSession, bid_nos: Iterable[str]) -> int:
    """공동수급 구성원이 있는 공고의 낙찰을 is_joint=true로.

    차수 ''(신체계 계약)는 모든 차수와 잇는다.
    """
    nos = sorted(set(bid_nos))
    if not nos:
        return 0
    m = BidJointMember
    has_members = exists().where(
        m.bid_ntce_no == BidAward.bid_ntce_no,
        or_(m.bid_ntce_ord == "", m.bid_ntce_ord == BidAward.bid_ntce_ord),
    )
    res: Any = await session.execute(
        update(BidAward)
        .where(BidAward.bid_ntce_no.in_(nos), BidAward.is_joint.is_(False), has_members)
        .values(is_joint=True, updated_at=func.now())
    )
    return int(res.rowcount or 0)
