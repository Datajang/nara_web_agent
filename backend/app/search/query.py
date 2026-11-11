"""검색 조건 (SPEC §6.3 SearchQuery)과 DB 질의 (§5.4). 외부 호출 없음."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Select, and_, or_, select

from app.db.models import Bid

KST = timezone(timedelta(hours=9))
MAX_DAYS = 90
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class SearchQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    keywords: Annotated[list[Keyword], Field(max_length=10)] = []
    match: Literal["all", "any"] = "all"
    source: Literal["regular", "prespec", "all"] = "all"
    days: int = Field(default=14, ge=1, le=MAX_DAYS)
    date_from: date | None = Field(default=None, alias="from")
    date_to: date | None = Field(default=None, alias="to")
    status: Literal["open", "all"] = "open"
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


def build_query(
    q: SearchQuery, start: datetime, end: datetime, now: datetime, limit: int
) -> Select[Any]:
    """키워드는 공백으로 나눠 title ILIKE, match=all이면 AND (§5.4). 취소공고도 결과에 남긴다."""
    stmt = select(Bid).where(Bid.notice_at >= start, Bid.notice_at < end)
    if q.source != "all":
        stmt = stmt.where(Bid.source == q.source)
    words = [w for kw in q.keywords for w in kw.split() if w]
    if words:
        conds = [Bid.title.ilike(_like(w), escape="\\") for w in words]
        stmt = stmt.where(and_(*conds) if q.match == "all" else or_(*conds))
    if q.status == "open":
        stmt = stmt.where(or_(Bid.deadline_at.is_(None), Bid.deadline_at > now))
    if q.budget_min is not None:
        stmt = stmt.where(Bid.budget >= q.budget_min)
    if q.budget_max is not None:
        stmt = stmt.where(Bid.budget <= q.budget_max)
    if q.org:
        stmt = stmt.where(Bid.org_name.ilike(_like(q.org), escape="\\"))
    order: tuple[Any, ...] = {
        "notice_desc": (Bid.notice_at.desc(), Bid.id.desc()),
        "deadline_asc": (Bid.deadline_at.asc().nulls_last(), Bid.id),
        "budget_desc": (Bid.budget.desc().nulls_last(), Bid.id),
    }[q.sort]
    return stmt.order_by(*order).limit(limit)
