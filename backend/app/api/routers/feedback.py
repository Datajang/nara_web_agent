"""POST /api/v1/feedback (SPEC §6.2, §12.7). 내 자원에만 남길 수 있다(남의 것은 404)."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import ActiveUser, DbSession
from app.api.schemas.history import FeedbackIn, FeedbackOut
from app.db.models import Feedback
from app.history import repo

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def post_feedback(body: FeedbackIn, user: ActiveUser, s: DbSession) -> FeedbackOut:
    if not await repo.owns_target(s, user.id, body.target_type, body.target_id):
        raise repo.not_found("피드백 대상")
    fb = Feedback(
        user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        rating=body.rating,
        comment=body.comment,
    )
    s.add(fb)
    await s.commit()
    return FeedbackOut(id=fb.id)
