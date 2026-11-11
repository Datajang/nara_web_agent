"""관리자 사용자 관리 (SPEC §9.4, §7.9). 집계·계정 정보만 다루고 개인 본문은 보지 않는다."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import revoke_all_sessions
from app.db.models.personal import User
from app.errors import ApiError


async def list_users(
    s: AsyncSession, status: str | None, limit: int, offset: int
) -> tuple[list[User], int]:
    q = select(User)
    if status:
        q = q.where(User.status == status)
    total = await s.scalar(select(func.count()).select_from(q.subquery()))
    rows = await s.scalars(
        q.order_by(User.created_at.desc(), User.id.desc()).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def update_user(
    s: AsyncSession,
    actor: User,
    target_id: int,
    *,
    status: str | None,
    role: str | None,
    now: datetime,
) -> User:
    user = await s.get(User, target_id)
    if user is None:
        raise ApiError(404, "not_found", "사용자를 찾을 수 없어요.")
    if user.id == actor.id and (status == "disabled" or role == "member"):
        raise ApiError(400, "cannot_modify_self", "자기 자신의 권한은 해제할 수 없어요.")
    if status is not None and status != user.status:
        if status == "active" and user.email_verified_at is None:
            user.email_verified_at = now  # 관리자가 직접 활성화하면 인증을 대신한 것으로 본다
        user.status = status
        if status == "disabled":
            await revoke_all_sessions(s, user.id, now)
    if role is not None:
        user.role = role
    await s.commit()
    return user
