"""/api/v1 비교·경쟁사 레이더·관심 경쟁사 (SPEC §15.6, P10). DB만 읽는다. 판정은 LLM 없이 규칙으로.

- GET /compare/{bizno}
- GET /competitors/candidates
- GET /competitors/watch, PUT·DELETE /competitors/watch/{bizno} (계정별, 팀 목록은 팀원 것을 모음)
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import require_llm, usage_logger
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.competitors import (
    CandidateListOut,
    CandidateOut,
    CompanyRefOut,
    CompareOut,
    TeamWatchedOut,
    WatchedListOut,
    WatchedOut,
)
from app.api.schemas.events import SSE_RESPONSES
from app.api.sse import Emitter, sse_response
from app.awards import competitors as comp
from app.awards import service as svc
from app.awards import views
from app.db.models import User
from app.deps import Deps
from app.pipeline.explain import explain

router = APIRouter(tags=["competitors"])
Bizno = Annotated[str, Path(pattern=r"^\d{10}$")]
NOTE = "두 회사 모두 수집 완료된 기간"


@router.get("/compare/{bizno}")
async def get_compare(user: ActiveUser, s: DbSession, ctx: Ctx, bizno: Bizno) -> CompareOut:
    return await views.compare_out(s, ctx.deps, bizno, user.id)


@router.post("/compare/{bizno}/explain", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def explain_compare(
    user: ActiveUser, s: DbSession, ctx: Ctx, bizno: Bizno
) -> StreamingResponse:
    """AI 해설(SSE, §15.8). 입력은 GET /compare 응답뿐. 숫자 검증에 두 번 실패하면 해설 없이."""
    ctx.limiter.hit(f"compare-explain:{user.id}", 10, 60)
    deps = ctx.deps
    llm = require_llm(deps)
    compare = (await views.compare_out(s, deps, bizno)).model_dump(mode="json", by_alias=True)
    await s.commit()

    async def work(em: Emitter) -> dict[str, Any] | None:
        em.send({"type": "status", "stage": "explain", "message": "비교 표를 풀어 쓰고 있어요"})
        r = await explain(llm, compare)
        em.send(
            {
                "type": "explain",
                "explanation": r.explanation.model_dump() if r.explanation else None,
                "verified": r.explanation is not None,
            }
        )
        return None

    return sse_response(work, on_finish=usage_logger(deps, user.id, "compare_explain"))


@router.get("/competitors/candidates")
async def get_candidates(
    user: ActiveUser,
    s: DbSession,
    ctx: Ctx,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    field: Annotated[str | None, Query(max_length=30)] = None,
    org: Annotated[str | None, Query(max_length=20)] = None,
) -> CandidateListOut:
    cfg, us, us_name = await views.us_config(s, ctx.deps)
    period, _cov = await svc.award_period(s, cfg.backfill_years, ctx.deps.clock())
    items = await comp.candidates(
        s, us, period, user_id=user.id, field_tag=field or None, org=org or None, limit=limit
    )
    our_count = len(await comp.load_facts(s, us, period))
    return CandidateListOut(
        period=views.period_out(period),
        us=CompanyRefOut(bizno=us, name=us_name),
        our_count=our_count,
        items=[CandidateOut(**vars(c)) for c in items],
    )


async def _watched_out(s: AsyncSession, deps: Deps, user: User) -> WatchedListOut:
    """내 목록 + 팀이 있으면 팀원(나 포함) 목록을 회사별로 묶어 담은 사람과 함께."""
    cfg = await svc.load_org(s, deps.settings.awards_backfill_years_default)
    period, _cov = await svc.award_period(s, cfg.backfill_years, deps.clock())
    mine = await comp.list_watched(s, period, [user.id])
    team = None
    if user.team_id is not None and user.team is not None:
        ids = list(await s.scalars(select(User.id).where(User.team_id == user.team_id)))
        rows = await comp.list_watched(s, period, ids, with_names=True)
        team = TeamWatchedOut(name=user.team.name, items=[WatchedOut(**vars(w)) for w in rows])
    return WatchedListOut(items=[WatchedOut(**vars(w)) for w in mine], team=team)


@router.get("/competitors/watch")
async def get_watched(user: ActiveUser, s: DbSession, ctx: Ctx) -> WatchedListOut:
    return await _watched_out(s, ctx.deps, user)


@router.put("/competitors/watch/{bizno}")
async def put_watched(user: ActiveUser, s: DbSession, ctx: Ctx, bizno: Bizno) -> WatchedListOut:
    """내 관심 경쟁사에 추가(이미 있으면 그대로). 계정별 (2026-11-23)."""
    if await svc.get_company(s, bizno) is None:
        raise views.company_not_found()
    await comp.watch(s, bizno, user.id)
    await s.commit()
    return await _watched_out(s, ctx.deps, user)


@router.delete("/competitors/watch/{bizno}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watched(user: ActiveUser, s: DbSession, bizno: Bizno) -> Response:
    await comp.unwatch(s, bizno, user.id)
    await s.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
