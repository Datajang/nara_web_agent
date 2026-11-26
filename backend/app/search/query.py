"""검색 조건 (SPEC §6.3 SearchQuery)과 DB 질의 (§5.4). 외부 호출 없음."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, aliased

from app.bids.cards import CANCELLED_KIND
from app.db.models import Bid, BidAward, BidOpeningStatus

KST = timezone(timedelta(hours=9))
MAX_DAYS = 90
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class SearchQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    keywords: Annotated[list[Keyword], Field(max_length=10)] = []
    # 공고명(제목) 일부·전체. 띄어쓰기 무시, 적힌 순서대로 들어 있어야 맞음 (2026-11-16)
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    match: Literal["all", "any"] = "all"
    source: Literal["regular", "prespec", "all"] = "all"
    days: int = Field(default=14, ge=1, le=MAX_DAYS)
    date_from: date | None = Field(default=None, alias="from")
    date_to: date | None = Field(default=None, alias="to")
    # 진행중 · 마감(마감일 지남) · 유찰(docs/BID_OUTCOME.md 규칙) · 전체 (2026-11-26)
    status: Literal["open", "closed", "failed", "all"] = "open"
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    org: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    sort: Literal["notice_desc", "deadline_asc", "budget_desc"] = "notice_desc"
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def _range(self) -> Self:
        if (self.date_from is None) != (self.date_to is None):
            raise ValueError("from과 to는 함께 지정해야 합니다")
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                raise ValueError("from이 to보다 늦습니다")
            if (self.date_to - self.date_from).days + 1 > MAX_DAYS:
                raise ValueError(f"기간은 최대 {MAX_DAYS}일입니다")
        return self

    def window(self, now: datetime) -> tuple[datetime, datetime]:
        """조회 창 [start, end). from/to는 KST 날짜(끝 날짜 포함)."""
        if self.date_from and self.date_to:
            start = datetime.combine(self.date_from, time(), KST)
            end = min(now, datetime.combine(self.date_to + timedelta(days=1), time(), KST))
            return start, end
        return now - timedelta(days=self.days), now


def _like(kw: str) -> str:
    return "%" + kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def title_contains(
    text: str, column: ColumnElement[str] | InstrumentedAttribute[str] | None = None
) -> ColumnElement[bool] | None:
    """공고명(기본 Bid.title)에 text가 들어 있는지. 양쪽 띄어쓰기를 모두 무시한다. 빈 값이면 None.
    낙찰 사업명(BidAward.title)에도 같은 규칙을 쓴다(우리 수주 현황 필터, 2026-11-24)."""
    flat = "".join(text.split())
    if not flat:
        return None
    squashed = func.regexp_replace(Bid.title if column is None else column, r"\s+", "", "g")
    return squashed.ilike(_like(flat), escape="\\")


def not_cancelled() -> ColumnElement[bool]:
    """취소공고가 아님. 공고종류가 없는 줄(사전규격 등)은 남긴다 [결정: 2026-11-17]."""
    return Bid.raw["ntceKindNm"].astext.is_distinct_from(CANCELLED_KIND)


def is_open(now: datetime) -> ColumnElement[bool]:
    """진행중: 마감일이 없거나 아직 안 지남(§4)."""
    return or_(Bid.deadline_at.is_(None), Bid.deadline_at > now)


def is_closed(now: datetime) -> ColumnElement[bool]:
    return Bid.deadline_at <= now


def failed_only() -> ColumnElement[bool]:
    """유찰: 카드 배지와 같은 규칙(app/bids/outcome.py). 일반공고의 현재 차수(raw bidNtceOrd)에
    낙찰 행이 없고, 분류마다 마지막 재입찰 행이 모두 '유찰'(행이 하나 이상)."""
    ord_ = func.coalesce(Bid.raw["bidNtceOrd"].astext, "000")
    st, later = BidOpeningStatus, aliased(BidOpeningStatus)
    same = and_(st.bid_ntce_no == Bid.bid_no, st.bid_ntce_ord == ord_)
    not_last = exists().where(
        later.bid_ntce_no == st.bid_ntce_no,
        later.bid_ntce_ord == st.bid_ntce_ord,
        later.bid_clsfc_no == st.bid_clsfc_no,
        later.rbid_no > st.rbid_no,
    )
    awarded = exists().where(BidAward.bid_ntce_no == Bid.bid_no, BidAward.bid_ntce_ord == ord_)
    return and_(
        Bid.source == "regular",
        exists().where(same, st.status == "유찰"),
        ~exists().where(same, st.status != "유찰", ~not_last),
        ~awarded,
    )


def filtered(q: SearchQuery, start: datetime, end: datetime, now: datetime) -> Select[Any]:
    """정렬·상한 없는 검색 조건(건수 세기에도 쓴다).

    키워드는 공백으로 나눠 title ILIKE, match=all이면 AND (§5.4).
    취소공고는 모든 검색(검색 탭·추천·어시스턴트·관심 공고)에서 뺀다 [결정: 2026-11-17].
    """
    stmt = select(Bid).where(Bid.notice_at >= start, Bid.notice_at < end, not_cancelled())
    if q.source != "all":
        stmt = stmt.where(Bid.source == q.source)
    words = [w for kw in q.keywords for w in kw.split() if w]
    if words:
        conds = [Bid.title.ilike(_like(w), escape="\\") for w in words]
        stmt = stmt.where(and_(*conds) if q.match == "all" else or_(*conds))
    if q.title and (cond := title_contains(q.title)) is not None:
        stmt = stmt.where(cond)
    if q.status == "open":
        stmt = stmt.where(is_open(now))
    elif q.status in ("closed", "failed"):
        stmt = stmt.where(is_closed(now))
        if q.status == "failed":
            stmt = stmt.where(failed_only())
    if q.budget_min is not None:
        stmt = stmt.where(Bid.budget >= q.budget_min)
    if q.budget_max is not None:
        stmt = stmt.where(Bid.budget <= q.budget_max)
    if q.org:
        stmt = stmt.where(Bid.org_name.ilike(_like(q.org), escape="\\"))
    return stmt


def build_query(
    q: SearchQuery, start: datetime, end: datetime, now: datetime, limit: int
) -> Select[Any]:
    """filtered + 정렬 + 상한."""
    stmt = filtered(q, start, end, now)
    order: tuple[Any, ...] = {
        "notice_desc": (Bid.notice_at.desc(), Bid.id.desc()),
        "deadline_asc": (Bid.deadline_at.asc().nulls_last(), Bid.id),
        "budget_desc": (Bid.budget.desc().nulls_last(), Bid.id),
    }[q.sort]
    return stmt.order_by(*order).limit(limit)
