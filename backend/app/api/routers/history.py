"""/api/v1 내 기록: search-runs, analyses, bookmarks (SPEC §6.2). 외부 호출 없음."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.common import load_bid, model_id
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.history import (
    AnalysisDetail,
    AnalysisList,
    AnalysisSummaryOut,
    BookmarkIn,
    BookmarkList,
    BookmarkOut,
    SearchRunDetail,
    SearchRunList,
    SearchRunOut,
)
from app.bids.cards import build_cards
from app.db.models import SearchRun
from app.history import repo
from app.llm.schemas import AnalysisResult
from app.llm.versions import bid_ref

router = APIRouter(tags=["history"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def _run_out(r: SearchRun) -> SearchRunOut:
    return SearchRunOut(
        id=r.id,
        kind=r.kind,  # type: ignore[arg-type]
        profile_id=r.profile_id,
        query=r.query,
        result_count=r.result_count,
        data_as_of=r.data_as_of,
        from_cache=r.cache_hit,
        created_at=r.created_at,
    )


@router.get("/search-runs")
async def list_runs(
    user: ActiveUser,
    s: DbSession,
    kind: Literal["search", "recommend"] | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> SearchRunList:
    rows, total = await repo.list_runs(s, user.id, kind, limit, offset)
    return SearchRunList(items=[_run_out(r) for r in rows], total=total)


@router.get("/search-runs/{run_id}")
async def get_run(
    run_id: int, user: ActiveUser, s: DbSession, ctx: Ctx, limit: Limit = 50, offset: Offset = 0
) -> SearchRunDetail:
    run = await repo.get_run(s, user.id, run_id)
    rows = await repo.run_items(s, run.id, limit, offset)
    scores = {b.id: (i.score, i.reason) for b, i in rows}
    cards = await build_cards(
        s, user.id, [b for b, _ in rows], ctx.deps.clock(), model_id(ctx.deps), scores
    )
    return SearchRunDetail(**_run_out(run).model_dump(), items=cards, offset=offset, limit=limit)


@router.delete("/search-runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: int, user: ActiveUser, s: DbSession) -> Response:
    await repo.delete_run(s, user.id, run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/analyses")
async def list_analyses(
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    limit: Limit = 50,
    offset: Offset = 0,
    scope: Literal["mine", "team"] = "mine",
) -> AnalysisList:
    """scope=team이면 팀 프로필로 만든 팀원의 분석(§13 P6). 팀이 없으면 빈 목록."""
    if scope == "team":
        if user.team_id is None:
            return AnalysisList(items=[], total=0)
        rows, total = await repo.list_team_analyses(s, user.team_id, limit, offset)
    else:
        rows, total = await repo.list_analyses(s, user.id, limit, offset)
    cards = await build_cards(
        s, user.id, [b for _, _, b, _ in rows], ctx.deps.clock(), model_id(ctx.deps)
    )
    return AnalysisList(
        items=[
            AnalysisSummaryOut(
                analysis_id=a.id,
                bid=card,
                profile_id=ua.profile_id,
                profile_name=name,
                fit_score=a.result["fit"]["score"],
                verdict=a.result["fit"]["verdict"],
                created_at=ua.created_at,
            )
            for (ua, a, _, name), card in zip(rows, cards, strict=True)
        ],
        total=total,
    )


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: int, user: ActiveUser, s: DbSession) -> AnalysisDetail:
    ua, a = await repo.get_analysis(s, user.id, analysis_id, user.team_id)
    return AnalysisDetail(
        analysis_id=a.id,
        bid_id=bid_ref(a.bid_id),
        profile_id=ua.profile_id,
        analysis=AnalysisResult.model_validate(a.result),
        markdown=a.markdown,
        created_at=ua.created_at,
    )


@router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(analysis_id: int, user: ActiveUser, s: DbSession) -> Response:
    await repo.delete_analysis(s, user.id, analysis_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/bookmarks")
async def list_bookmarks(user: ActiveUser, s: DbSession, ctx: Ctx) -> BookmarkList:
    rows = await repo.list_bookmarks(s, user.id)
    cards = await build_cards(
        s, user.id, [b for _, b in rows], ctx.deps.clock(), model_id(ctx.deps)
    )
    return BookmarkList(
        items=[
            BookmarkOut(
                bid=card, note=bm.note, analysis_id=bm.analysis_id, created_at=bm.created_at
            )
            for (bm, _), card in zip(rows, cards, strict=True)
        ]
    )


@router.put("/bookmarks/{bid_id}", status_code=status.HTTP_204_NO_CONTENT)
async def put_bookmark(
    bid_id: str, body: BookmarkIn, user: ActiveUser, s: DbSession, ctx: Ctx
) -> Response:
    bid = await load_bid(s, bid_id)
    await repo.put_bookmark(s, user.id, bid.id, body.note, body.analysis_id, ctx.deps.clock())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/bookmarks/{bid_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(bid_id: str, user: ActiveUser, s: DbSession) -> Response:
    bid = await load_bid(s, bid_id)
    await repo.delete_bookmark(s, user.id, bid.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
