"""개발 전용: 메모리 메일함 조회. ENV=development이고 MAIL_BACKEND=memory일 때만 등록된다
(운영 라우트 목록에 없음을 test_routes_guard가 고정)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Ctx
from app.api.schemas import DevMail, DevMailList
from app.auth.mail import MemoryMailer

router = APIRouter(prefix="/_dev", tags=["dev"])


@router.get("/mail")
async def dev_mail(ctx: Ctx) -> DevMailList:
    assert isinstance(ctx.mailer, MemoryMailer)
    items = [DevMail(to=m.to, subject=m.subject, body=m.body) for m in ctx.mailer.outbox[-50:]]
    return DevMailList(items=items)
