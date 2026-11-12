"""POST /api/v1/bids/{bid_id}/analyze (SPEC §6.4 analyze 흐름). SSE.

files → extract → summarize → analyze → result → done. 단계별 cache 적중을 status에 싣고,
전부 적중하면 status 없이 result·done만 나간다. 연결이 끊겨도 분석은 끝까지 저장된다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.common import load_bid, require_llm, usage_logger
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.bids import AnalyzeIn
from app.api.schemas.events import SSE_RESPONSES
from app.api.sse import Emitter, sse_response
from app.history import repo as history
from app.pipeline.analyze import get_or_create_analysis
from app.profiles import repo as profiles

router = APIRouter(tags=["analyze"])


@router.post("/bids/{bid_id}/analyze", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def analyze(
    bid_id: str, body: AnalyzeIn, user: ActiveUser, s: DbSession, ctx: Ctx
) -> StreamingResponse:
    ctx.limiter.hit(f"analyze:{user.id}", 10, 60)
    bid = await load_bid(s, bid_id)
    profile = await profiles.get_profile(s, user, body.profile_id)
    deps = ctx.deps
    require_llm(deps)
    uid, pid, text, n = user.id, profile.id, profile.description, bid.id

    async def work(em: Emitter) -> dict[str, Any] | None:
        row, hit = await get_or_create_analysis(deps, n, text)
        async with deps.db.session() as s2:
            await history.link_analysis(s2, uid, row.id, pid)
        em.send(
            {
                "type": "result",
                "analysis_id": row.id,
                "analysis": row.result,
                "markdown": row.markdown,
                "from_cache": hit,
            }
        )
        return None

    return sse_response(work, on_finish=usage_logger(deps, uid, "analyze"))
