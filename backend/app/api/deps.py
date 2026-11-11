"""FastAPI 의존성 (SPEC §9.4): current_user → require_active → require_admin.

access 토큰은 서명만 믿지 않고 매 요청 DB에서 사용자 상태를 다시 읽는다(비활성화 즉시 반영).
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.context import AppContext
from app.api.security import ACCESS_COOKIE
from app.auth.tokens import decode_access_token
from app.db.models.personal import User
from app.errors import ApiError
from app.logging_setup import current_context


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
    current_context()["user_id"] = user.id  # 요청 로그용 (§11.7)
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


TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})


def client_ip(request: Request) -> str:
    """§11.4: nginx(127.0.0.1)에서 온 요청만 X-Forwarded-For를 믿는다.

    마지막 값을 쓴다. nginx가 붙인 값이라 클라이언트가 앞에 넣은 값으로 속일 수 없다.
    """
    peer = request.client.host if request.client else None
    if peer is None:
        return "unknown"
    if peer in TRUSTED_PROXIES:
        last = request.headers.get("x-forwarded-for", "").rsplit(",", 1)[-1].strip()
        try:
            return str(ipaddress.ip_address(last))
        except ValueError:
            pass
    return peer
