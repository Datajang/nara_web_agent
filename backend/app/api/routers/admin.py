"""/api/v1/admin/users (SPEC §6.2, §7.9). 관리자 경로는 users·usage·collector만 (§9.4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, Ctx, DbSession
from app.api.schemas import AdminUserList, AdminUserOut, AdminUserPatch, UserStatus
from app.auth.admin import list_users, update_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def get_users(
    _: AdminUser,
    s: DbSession,
    status: UserStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AdminUserList:
    users, total = await list_users(s, status, limit, offset)
    return AdminUserList(items=[AdminUserOut.model_validate(u) for u in users], total=total)


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: int, body: AdminUserPatch, admin: AdminUser, s: DbSession, ctx: Ctx
) -> AdminUserOut:
    user = await update_user(
        s, admin, user_id, status=body.status, role=body.role, now=ctx.deps.clock()
    )
    return AdminUserOut.model_validate(user)
