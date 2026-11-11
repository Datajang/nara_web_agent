"""POST /api/v1/feedback (SPEC §6.2, §12.7). 내 자원에만 남길 수 있다(남의 것은 404).

model·prompt_version은 서버가 채운다. 분석은 그 분석을 만든 값, 나머지는 지금 설정값.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.history import FeedbackIn, FeedbackOut
from app.db.models import Analysis, Feedback
from app.history import repo
from app.llm.versions import PROMPT_VERSION, prompt_version

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def post_feedback(body: FeedbackIn, user: ActiveUser, s: DbSession, ctx: Ctx) -> FeedbackOut:
    if not await repo.owns_target(s, user.id, body.target_type, body.target_id):
        raise repo.not_found("피드백 대상")
    model_id = ctx.deps.settings.llm_model_id
    pv = prompt_version(PROMPT_VERSION, model_id)
    if body.target_type == "analysis":
        analysis = await s.get(Analysis, body.target_id)
        if analysis is not None:
            model_id, pv = analysis.model_id, analysis.prompt_version
    fb = Feedback(
        user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        rating=body.rating,
        reason=body.reason,
        comment=body.comment,
        model=model_id,
        prompt_version=pv,
        created_at=ctx.deps.clock(),
    )
    s.add(fb)
    await s.commit()
    return FeedbackOut(id=fb.id)
