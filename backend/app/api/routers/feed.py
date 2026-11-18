"""/api/v1/feed — 관심 공고 홈 (SPEC §13 P6). DB만 읽는다."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.common import model_id
from app.api.deps import ActiveUser, Ctx, DbSession
from app.bids.cards import BidCard, build_cards
from app.feed.service import Due, FeedFilter, load_feed

router = APIRouter(tags=["feed"])


class FeedItem(BidCard):
    matched_keywords: list[str]


class FeedOut(BaseModel):
    keywords: list[str]
    needs_keywords: bool  # 키워드가 3개 미만이면 true, 화면은 키워드 설정으로 안내
    total: int
    items: list[FeedItem]
    min_budget: int | None = None  # 이 금액 이상만 보여 줌(원). null이면 금액 제한 없음


@router.get("/feed")
async def get_feed(
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    q: Annotated[str | None, Query(max_length=200)] = None,  # 공고명 일부, 띄어쓰기 무시
    source: Literal["all", "regular", "prespec"] = "all",
    kw: Annotated[list[str] | None, Query()] = None,  # 내 키워드 중 고른 것, 비우면 전부
    due: Due = "all",  # 마감 구간 하나만: today·d3·d7·later (2026-11-18 마감 보드)
) -> FeedOut:
    deps = ctx.deps
    flt = FeedFilter(q=q, source=source, keywords=tuple(kw or ()), due=due)
    f = await load_feed(s, user, deps.clock(), offset, limit, flt)
    cards = await build_cards(s, user.id, f.bids, deps.clock(), model_id(deps))
    by_id = {b.id: b for b in f.bids}
    items = [
        FeedItem(**c.model_dump(), matched_keywords=f.matched[int(c.bid_id[1:])])
        for c in cards
        if int(c.bid_id[1:]) in by_id
    ]
    return FeedOut(
        keywords=f.keywords,
        needs_keywords=f.needs_keywords,
        total=f.total,
        items=items,
        min_budget=f.min_budget,
    )
