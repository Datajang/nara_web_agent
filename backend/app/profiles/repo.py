"""프로필 리포지토리 (SPEC §6.1 개인 자원, §13 P6 팀 프로필).

개인 프로필은 본인만, 팀 프로필은 같은 팀원만 본다. 볼 수 없는 프로필은 존재하지 않는 것과
똑같이 404. 팀 프로필은 팀원 누구나 만들고 고치며 삭제는 팀장만 한다. '기본 프로필'은
개인·팀 범위마다 하나다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, false, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.personal import Profile, User
from app.errors import ApiError
from app.profiles.hashing import profile_hash
from app.teams.service import no_team, not_owner

MAX_PROFILES = 20


def clean_keywords(keywords: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for k in keywords:
        k = k.strip()
        if k:
            seen.setdefault(k, None)
    return list(seen)


def visible_to(user_id: int, team_id: int | None) -> ColumnElement[bool]:
    """이 사용자가 볼 수 있는 프로필: 내 개인 프로필 + 내 팀의 팀 프로필."""
    mine = Profile.user_id == user_id
    return mine | (Profile.team_id == team_id) if team_id is not None else mine


def _scope_where(p_or_scope: Profile | str, user: User) -> ColumnElement[bool]:
    scope = p_or_scope if isinstance(p_or_scope, str) else p_or_scope.scope
    if scope == "team":
        return Profile.team_id == user.team_id if user.team_id is not None else false()
    return Profile.user_id == user.id


async def list_profiles(s: AsyncSession, user: User) -> list[Profile]:
    rows = await s.scalars(
        select(Profile)
        .where(visible_to(user.id, user.team_id))
        .order_by(Profile.team_id.is_(None), Profile.id)  # 팀 프로필 먼저
    )
    return list(rows)


async def get_profile(s: AsyncSession, user: User, profile_id: int) -> Profile:
    p = await s.scalar(
        select(Profile).where(Profile.id == profile_id, visible_to(user.id, user.team_id))
    )
    if p is None:
        raise ApiError(404, "not_found", "프로필을 찾을 수 없어요.")
    return p


async def _clear_default(s: AsyncSession, where: ColumnElement[bool], keep: int | None) -> None:
    q = update(Profile).where(where, Profile.is_default.is_(True))
    if keep is not None:
        q = q.where(Profile.id != keep)
    await s.execute(q.values(is_default=False))


async def create_profile(
    s: AsyncSession, user: User, data: dict[str, Any], now: datetime
) -> Profile:
    scope = data.get("scope", "personal")
    if scope == "team" and user.team_id is None:
        raise no_team()
    where = _scope_where(scope, user)
    count = await s.scalar(select(func.count()).select_from(Profile).where(where))
    if (count or 0) >= MAX_PROFILES:
        raise ApiError(409, "conflict", f"프로필은 {MAX_PROFILES}개까지 만들 수 있어요.")
    if data.get("is_default"):
        await _clear_default(s, where, None)
    p = Profile(
        user_id=None if scope == "team" else user.id,
        team_id=user.team_id if scope == "team" else None,
        name=data["name"],
        description=data.get("description", ""),
        keywords=clean_keywords(data.get("keywords", [])),
        profile_hash=profile_hash(data.get("description", "")),
        is_default=bool(data.get("is_default")),
        created_at=now,
        updated_at=now,
    )
    s.add(p)
    await s.commit()
    return p


async def update_profile(
    s: AsyncSession, user: User, profile_id: int, data: dict[str, Any], now: datetime
) -> Profile:
    p = await get_profile(s, user, profile_id)
    if "name" in data:
        p.name = data["name"]
    if "description" in data:
        p.description = data["description"]
        p.profile_hash = profile_hash(data["description"])  # 이전 점수·분석과 분리 (§4)
    if "keywords" in data:
        p.keywords = clean_keywords(data["keywords"])
    if data.get("is_default"):
        await _clear_default(s, _scope_where(p, user), p.id)
        p.is_default = True
    elif data.get("is_default") is False:
        p.is_default = False
    p.updated_at = now
    await s.commit()
    return p


async def delete_profile(s: AsyncSession, user: User, profile_id: int) -> None:
    p = await get_profile(s, user, profile_id)
    if p.team_id is not None and user.team_role != "owner":
        raise not_owner()
    await s.delete(p)
    await s.commit()


async def team_keywords(s: AsyncSession, team_id: int | None) -> list[str]:
    """팀 프로필 키워드 합집합 (관심 공고, §13 P6)."""
    if team_id is None:
        return []
    rows = await s.scalars(
        select(Profile.keywords).where(Profile.team_id == team_id).order_by(Profile.id)
    )
    return clean_keywords([str(k) for kws in rows for k in kws])
