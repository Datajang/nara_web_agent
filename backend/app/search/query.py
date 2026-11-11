from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, or_, select

from app.db.models import Bid


class SearchQuery(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    keyword_mode: Literal["and", "or"] = "and"
    days: int = Field(default=7, ge=1, le=365)
    source: Literal["all", "regular", "prespec"] = "all"
    status: Literal["all", "open"] = "all"
    budget_min: int | None = None
    budget_max: int | None = None
    org: str | None = None
    sort: Literal["notice_desc", "deadline_asc", "budget_desc"] = "notice_desc"
    top_n: int = Field(default=100, ge=1, le=100)


def _like(kw: str) -> str:
    return "%" + kw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def build_query(q: SearchQuery, start: datetime, end: datetime, now: datetime) -> Select[Bid]:
    """DB 조회만 (외부 호출 없음). 키워드는 공백으로 나눠 기본 AND로 title ILIKE (§5.4)."""
    stmt = select(Bid).where(Bid.notice_at >= start, Bid.notice_at < end)
    if q.source != "all":
        stmt = stmt.where(Bid.source == q.source)
    words = [w for kw in q.keywords for w in kw.split() if w]
    if words:
        conds = [Bid.title.ilike(_like(w), escape="\\") for w in words]
        stmt = stmt.where(and_(*conds) if q.keyword_mode == "and" else or_(*conds))
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
    return stmt.order_by(*order).limit(q.top_n)
