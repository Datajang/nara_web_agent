"""/api/v1/bids (SPEC §6.2, §6.3). 상세·파일 본문 조회는 LLM·G2B를 호출하지 않는다.

lookup만 DB에 없을 때 G2B 단건 조회를 1~2회 한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.common import bid_not_found, load_bid, model_id
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.bids import (
    BidDetail,
    FileOut,
    FileTextOut,
    LookupOut,
    SearchQuery,
    SearchResultOut,
)
from app.bids.cards import build_cards
from app.bids.lookup import fetch_from_g2b, find_in_db
from app.db.models import Bid, BidFile, BidSummary, FileText
from app.errors import ApiError
from app.g2b.client import G2BError
from app.history import repo as history
from app.llm.schemas import BidSummary as BidSummaryOut
from app.llm.versions import SUMMARY_PROMPT, bid_ref, prompt_version
from app.pipeline.summarize import source_inputs
from app.search.service import search_bids

router = APIRouter(prefix="/bids", tags=["bids"])


@router.post("/search")
async def search(body: SearchQuery, user: ActiveUser, s: DbSession, ctx: Ctx) -> SearchResultOut:
    ctx.limiter.hit(f"search:{user.id}", 30, 60)
    deps = ctx.deps
    res = await search_bids(deps, user.id, body)
    assert res.run_id is not None
    cards = await build_cards(s, user.id, res.items, deps.clock(), model_id(deps))
    return SearchResultOut(
        run_id=res.run_id,
        data_as_of=res.data_as_of,
        incomplete=res.incomplete,
        collecting=res.collecting,
        from_cache=res.cache_hit,
        total=res.total,
        truncated=res.truncated,
        items=cards,
    )


# /bids/{bid_id}보다 먼저 선언한다 (§6.2)
@router.get("/lookup")
async def lookup(
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    bid_no: Annotated[str, Query(min_length=1, max_length=40)],
) -> LookupOut:
    """DB → 없으면 G2B 단건 조회(Q5 확인, docs/decisions/2026-11-12-g2b-single-lookup.md)."""
    no = bid_no.strip()
    found = await find_in_db(s, no)
    if found is None and no and ctx.deps.g2b is not None:
        ctx.limiter.hit(f"lookup:{user.id}", 30, 60)
        try:
            found = await fetch_from_g2b(ctx.deps, user.id, no)
        except G2BError as e:
            raise ApiError(
                503, "g2b_unavailable", "나라장터 조회에 실패했어요. 잠시 후 다시 시도해 주세요."
            ) from e
    if found is None:
        raise bid_not_found()
    return LookupOut(bid_id=bid_ref(found))


@router.get("/{bid_id}")
async def detail(bid_id: str, user: ActiveUser, s: DbSession, ctx: Ctx) -> BidDetail:
    deps = ctx.deps
    bid = await load_bid(s, bid_id)
    (card,) = await build_cards(s, user.id, [bid], deps.clock(), model_id(deps))
    files = (
        await s.execute(select(BidFile).where(BidFile.bid_id == bid.id).order_by(BidFile.id))
    ).scalars()
    source_hash, _, _ = await source_inputs(deps, bid)
    raw = await s.scalar(
        select(BidSummary.summary).where(
            BidSummary.bid_id == bid.id,
            BidSummary.source_hash == source_hash,
            BidSummary.prompt_version == prompt_version(SUMMARY_PROMPT, model_id(deps)),
        )
    )
    related = None
    if bid.prespec_reg_no:
        related = await s.scalar(
            select(Bid.id)
            .where(Bid.prespec_reg_no == bid.prespec_reg_no, Bid.source != bid.source)
            .order_by(Bid.notice_at.desc().nulls_last(), Bid.id.desc())
            .limit(1)
        )
    return BidDetail(
        **card.model_dump(),
        prespec_reg_no=bid.prespec_reg_no,
        related_bid_id=bid_ref(related) if related else None,
        files=[
            FileOut(file_id=f.id, name=f.name, kind=f.kind, status=f.status)  # type: ignore[arg-type]
            for f in files
        ],
        summary=BidSummaryOut.model_validate(raw) if raw else None,
        my_analysis_id=await history.my_latest_analysis_id(s, user.id, bid.id),
    )


@router.get("/{bid_id}/files/{file_id}/text")
async def file_text(
    bid_id: str,
    file_id: int,
    _: ActiveUser,
    s: DbSession,
    max_chars: Annotated[int, Query(ge=1, le=200_000)] = 20_000,
) -> FileTextOut:
    bid = await load_bid(s, bid_id)
    row = (
        await s.execute(
            select(BidFile, FileText)
            .join(FileText, FileText.sha256 == BidFile.sha256)
            .where(BidFile.id == file_id, BidFile.bid_id == bid.id, BidFile.status == "ok")
        )
    ).first()
    if row is None:
        raise bid_not_found()
    f, t = row
    return FileTextOut(
        file_id=f.id,
        name=f.name,
        text=t.text[:max_chars],
        char_count=t.char_count,
        truncated=len(t.text) > max_chars,
    )
