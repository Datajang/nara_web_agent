"""POST /api/v1/recommend (SPEC §6.4 recommend 흐름). SSE.

status(search) → status(score, progress) 반복 → cards(점수 내림차순) → done.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.common import model_id, require_llm, usage_logger
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.bids import RecommendIn
from app.api.schemas.events import SSE_RESPONSES
from app.api.sse import Emitter, sse_response
from app.bids.cards import build_cards
from app.db.models import Profile
from app.pipeline.recommend import recommend
from app.profiles import repo as profiles

router = APIRouter(tags=["recommend"])


@router.post("/recommend", response_class=StreamingResponse, responses=SSE_RESPONSES)
async def post_recommend(
    body: RecommendIn, user: ActiveUser, s: DbSession, ctx: Ctx
) -> StreamingResponse:
    ctx.limiter.hit(f"recommend:{user.id}", 10, 60)
    profile = await profiles.get_profile(s, user, body.profile_id)
    deps = ctx.deps
    require_llm(deps)
    uid, pid = user.id, profile.id

    async def work(em: Emitter) -> dict[str, Any] | None:
        async with deps.db.session() as s2:
            prof = await s2.get_one(Profile, pid)
        rec = await recommend(
            deps,
            uid,
            prof,
            days=body.days,
            source=body.source,
            top_n=body.top_n,
            keywords=body.keywords,
        )
        scores = {b.id: (sc.score, sc.reason) for b, sc in rec.ranked}
        async with deps.db.session() as s2:
            cards = await build_cards(
                s2, uid, [b for b, _ in rec.ranked], deps.clock(), model_id(deps), scores
            )
        em.send(
            {
                "type": "cards",
                "items": [c.model_dump(mode="json") for c in cards],
                "run_id": rec.run_id,
            }
        )
        return None

    return sse_response(work, on_finish=usage_logger(deps, uid, "recommend"))
