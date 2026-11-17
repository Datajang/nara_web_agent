"""관심 공고 (SPEC §13 P6 관심 공고 1~3). DB만 읽는다(G2B·LLM 호출 없음).

키워드 = 팀 프로필 키워드 ∪ 개인 키워드. 키워드 하나의 단어는 모두 포함(AND), 키워드끼리는 OR로
제목을 맞추고, 진행 중이며 최근 30일 공고를 마감 임박 순으로 낸다. 키워드가 3개 미만이면 비운다.
예산은 기본 1억 원 이상만(예산 없는 공고도 뺀다), 사용자가 설정하면 전부.
화면에서 고른 조건(FeedFilter: 공고명, 일반/사전규격, 내 키워드 중 일부)으로 더 좁힐 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bid, User
from app.profiles.repo import clean_keywords, team_keywords
from app.search.query import _like, not_cancelled, title_contains

WINDOW_DAYS = 30
MIN_KEYWORDS = 3
MIN_BUDGET = 100_000_000  # 기본은 1억 원 이상만, users.feed_include_small이면 전부 (2026-11-16)


@dataclass
class Feed:
    keywords: list[str]
    needs_keywords: bool
    total: int = 0
    bids: list[Bid] = field(default_factory=list)
    matched: dict[int, list[str]] = field(default_factory=dict)
    min_budget: int | None = MIN_BUDGET


@dataclass(frozen=True)
class FeedFilter:
    """관심 공고 안에서 더 좁히기 (2026-11-16). 모두 비우면 전체."""

    q: str | None = None
    source: Literal["all", "regular", "prespec"] = "all"
    keywords: tuple[str, ...] = ()


def _words(kw: str) -> list[str]:
    return [w for w in kw.split() if w]


def _cond(kw: str) -> ColumnElement[bool]:
    return and_(*[Bid.title.ilike(_like(w), escape="\\") for w in _words(kw)])


def matched_keywords(title: str, keywords: list[str]) -> list[str]:
    t = title.casefold()
    return [k for k in keywords if all(w.casefold() in t for w in _words(k))]


async def keywords_for(s: AsyncSession, user: User) -> list[str]:
    personal = [str(k) for k in (user.interest_keywords or [])]
    return clean_keywords(await team_keywords(s, user.team_id) + personal)


async def load_feed(
    s: AsyncSession,
    user: User,
    now: datetime,
    offset: int,
    limit: int,
    flt: FeedFilter | None = None,
) -> Feed:
    flt = flt or FeedFilter()
    keywords = await keywords_for(s, user)
    min_budget = None if user.feed_include_small else MIN_BUDGET
    if len(keywords) < MIN_KEYWORDS:
        return Feed(keywords=keywords, needs_keywords=True, min_budget=min_budget)
    # 고른 키워드는 내 키워드 중에서만. 하나도 안 맞으면(모르는 값뿐이면) 전체 키워드
    chosen = [k for k in keywords if k in set(flt.keywords)] or keywords
    where: tuple[ColumnElement[bool], ...] = (
        Bid.notice_at >= now - timedelta(days=WINDOW_DAYS),
        or_(Bid.deadline_at.is_(None), Bid.deadline_at > now),
        or_(*[_cond(k) for k in chosen]),
        not_cancelled(),
    )
    if min_budget is not None:
        where += (Bid.budget >= min_budget,)
    if flt.source != "all":
        where += (Bid.source == flt.source,)
    if flt.q and (cond := title_contains(flt.q)) is not None:
        where += (cond,)
    total = await s.scalar(select(func.count()).select_from(Bid).where(*where)) or 0
    rows = await s.scalars(
        select(Bid)
        .where(*where)
        .order_by(Bid.deadline_at.asc().nulls_last(), Bid.id)
        .offset(offset)
        .limit(limit)
    )
    bids = list(rows)
    return Feed(
        keywords=keywords,
        needs_keywords=False,
        total=total,
        bids=bids,
        matched={b.id: matched_keywords(b.title, keywords) for b in bids},
        min_budget=min_budget,
    )
