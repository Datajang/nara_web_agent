"""/api/v1/me (SPEC §6.2)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas import MeOut, MePatch
from app.api.security import set_auth_cookies
from app.auth.service import AuthService
from app.errors import ApiError

router = APIRouter(tags=["me"])


@router.get("/me")
async def get_me(user: ActiveUser) -> MeOut:
    return MeOut.model_validate(user)


@router.patch("/me")
async def patch_me(
    body: MePatch, user: ActiveUser, request: Request, response: Response, s: DbSession, ctx: Ctx
) -> MeOut:
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.new_password is not None:
        if body.current_password is None:
            raise ApiError(
                422,
                "validation_error",
                "현재 비밀번호를 입력해 주세요.",
                details=[{"field": "current_password", "reason": "missing"}],
            )
        svc = AuthService(s, ctx.deps.settings, ctx.mailer, ctx.deps.clock())
        session = await svc.change_password(
            user, body.current_password, body.new_password, request.headers.get("user-agent")
        )
        set_auth_cookies(response, session, ctx.deps.settings)
    await s.commit()
    return MeOut.model_validate(user)
