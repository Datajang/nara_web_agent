"""마감 공고 사유 (2026-11-26, docs/superpowers/specs/2026-11-26-closed-bid-reason-design.md).

마감된 공고 카드의 배지 하나를 정한다. 공고의 **현재 차수**(raw bidNtceOrd)의 행만 보고,
분류마다 마지막 재입찰 행이 그 분류의 결과다. 순서:
낙찰 → 모든 분류 유찰 → 개찰완료(1순위) → 재입찰·재시담 → 개찰 전 / 결과 대기(개찰일 기준).
진행 중·취소공고·개찰일 없는 마감은 None(지금처럼 '마감'·'취소'만). 사전규격은 '의견 마감'.
화면 요청에서는 DB만 읽는다(G2B 호출 없음).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, BidAward, BidOpeningStatus
from app.g2b.mapper import parse_kst

CANCELLED_KIND = "취소공고"
FAILED, OPENED, REBIDS = "유찰", "개찰완료", ("재입찰", "재시담")
OutcomeKind = Literal[
    "awarded", "failed", "opened", "rebid", "before_opening", "waiting", "prespec_closed"
]


class BidOutcome(BaseModel):
    kind: OutcomeKind
    company: str | None = None  # 낙찰 업체(awarded) 또는 1순위 업체(opened)
    more: int = 0  # 낙찰 업체가 다른 분류 수('외 N')
    reason: str | None = None  # 유찰 사유: 무응찰·단독응찰·낙찰하한선 미달
    opening_at: datetime | None = None  # 개찰일시(before_opening·waiting)


class _Row(Protocol):
    bid_ntce_ord: str
    bid_clsfc_no: str
    rbid_no: str


R = TypeVar("R", bound=_Row)


def is_cancelled(bid: Bid) -> bool:
    return (bid.raw or {}).get("ntceKindNm") == CANCELLED_KIND


def _last_per_class(rows: Iterable[R], ord_: str) -> list[R]:
    """현재 차수의 행을 분류마다 마지막 재입찰 하나로(분류 번호 순)."""
    last: dict[str, R] = {}
    for r in rows:
        if r.bid_ntce_ord != ord_:
            continue
        cur = last.get(r.bid_clsfc_no)
        if cur is None or r.rbid_no >= cur.rbid_no:
            last[r.bid_clsfc_no] = r
    return [last[k] for k in sorted(last)]


def failed_reason(texts: Sequence[str | None], counts: Sequence[int | None]) -> str | None:
    """유찰 문구(자유 문구)를 세 가지로 묶는다. 못 묶으면 None('유찰'만)."""
    for t in texts:
        s = (t or "").replace(" ", "")
        if "무응찰" in s:
            return "무응찰"
        if "단독" in s or "단일" in s:
            return "단독응찰"
        if "하한" in s:
            return "낙찰하한선 미달"
    return "무응찰" if counts and all(c == 0 for c in counts) else None


def decide(
    bid: Bid, now: datetime, awards: Iterable[BidAward], statuses: Iterable[BidOpeningStatus]
) -> BidOutcome | None:
    if bid.deadline_at is None or bid.deadline_at > now or is_cancelled(bid):
        return None
    if bid.source == "prespec":
        return BidOutcome(kind="prespec_closed")
    raw = bid.raw or {}
    ord_ = str(raw.get("bidNtceOrd") or "000")
    won = _last_per_class(awards, ord_)
    if won:
        return BidOutcome(kind="awarded", company=won[0].winner_name, more=len(won) - 1)
    st = _last_per_class(statuses, ord_)
    if st and all(r.status == FAILED for r in st):
        reason = failed_reason([r.result_text for r in st], [r.participant_count for r in st])
        return BidOutcome(kind="failed", reason=reason)
    if opened := next((r for r in st if r.status == OPENED), None):
        return BidOutcome(kind="opened", company=opened.top_name)
    if any(r.status in REBIDS for r in st):
        return BidOutcome(kind="rebid")
    at = parse_kst(str(raw.get("opengDt") or ""))
    if at is None:
        return None
    return BidOutcome(kind="before_opening" if at > now else "waiting", opening_at=at)


async def load_outcomes(
    s: AsyncSession, bids: Sequence[Bid], now: datetime
) -> dict[int, BidOutcome]:
    """마감된 공고만 낙찰·개찰 상태를 한 번에 읽어 판정한다(공고 id → 배지)."""
    closed = [b for b in bids if b.deadline_at is not None and b.deadline_at <= now]
    nos = sorted({b.bid_no for b in closed if b.source == "regular" and not is_cancelled(b)})
    awards: dict[str, list[BidAward]] = defaultdict(list)
    statuses: dict[str, list[BidOpeningStatus]] = defaultdict(list)
    if nos:
        for a in (await s.scalars(select(BidAward).where(BidAward.bid_ntce_no.in_(nos)))).all():
            awards[a.bid_ntce_no].append(a)
        q = select(BidOpeningStatus).where(BidOpeningStatus.bid_ntce_no.in_(nos))
        for r in (await s.scalars(q)).all():
            statuses[r.bid_ntce_no].append(r)
    out: dict[int, BidOutcome] = {}
    for b in closed:
        if (o := decide(b, now, awards[b.bid_no], statuses[b.bid_no])) is not None:
            out[b.id] = o
    return out
