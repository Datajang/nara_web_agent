"""FastAPI 의존성 (SPEC §9.4): current_user → require_active → require_admin.

access 토큰은 서명만 믿지 않고 매 요청 DB에서 사용자 상태를 다시 읽는다(비활성화 즉시 반영).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.context import AppContext
from app.api.security import ACCESS_COOKIE
from app.auth.tokens import decode_access_token
from app.db.models.personal import User
from app.errors import ApiError


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


Ctx = Annotated[AppContext, Depends(get_ctx)]


async def get_session(ctx: Ctx) -> AsyncIterator[AsyncSession]:
    async with ctx.deps.db.session() as s:
        yield s


DbSession = Annotated[AsyncSession, Depends(get_session)]


async def current_user(request: Request, ctx: Ctx, s: DbSession) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    settings = ctx.deps.settings
    claims = (
        decode_access_token(token, settings.secret_key.get_secret_value(), ctx.deps.clock())
        if token
        else None
    )
    user = await s.get(User, claims.user_id) if claims else None
    if user is None:
        raise ApiError(401, "unauthorized", "로그인이 필요해요.")
    return user


async def require_active(user: Annotated[User, Depends(current_user)]) -> User:
    if user.status != "active":
        raise ApiError(
            403,
            "forbidden",
            "사용할 수 없는 계정이에요.",
            details=[{"field": "status", "reason": user.status}],
        )
    return user


async def require_admin(user: Annotated[User, Depends(require_active)]) -> User:
    if user.role != "admin":
        raise ApiError(403, "forbidden", "관리자만 사용할 수 있어요.")
    return user


ActiveUser = Annotated[User, Depends(require_active)]
AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
