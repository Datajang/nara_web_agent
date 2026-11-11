"""프로필 리포지토리 (SPEC §6.1 개인 자원). 모든 함수가 user_id를 필수로 받아 쿼리에 넣는다.
남의 프로필은 존재하지 않는 것과 똑같이 404."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.personal import Profile
from app.errors import ApiError
from app.profiles.hashing import profile_hash

MAX_PROFILES = 20


def clean_keywords(keywords: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for k in keywords:
        k = k.strip()
        if k:
            seen.setdefault(k, None)
    return list(seen)


async def list_profiles(s: AsyncSession, user_id: int) -> list[Profile]:
    rows = await s.scalars(select(Profile).where(Profile.user_id == user_id).order_by(Profile.id))
    return list(rows)


async def get_profile(s: AsyncSession, user_id: int, profile_id: int) -> Profile:
    p = await s.scalar(select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id))
    if p is None:
        raise ApiError(404, "not_found", "프로필을 찾을 수 없어요.")
    return p


async def _clear_default(s: AsyncSession, user_id: int, keep: int | None) -> None:
    q = update(Profile).where(Profile.user_id == user_id, Profile.is_default.is_(True))
    if keep is not None:
        q = q.where(Profile.id != keep)
    await s.execute(q.values(is_default=False))


async def create_profile(
    s: AsyncSession, user_id: int, data: dict[str, Any], now: datetime
) -> Profile:
    count = await s.scalar(
        select(func.count()).select_from(Profile).where(Profile.user_id == user_id)
    )
    if (count or 0) >= MAX_PROFILES:
        raise ApiError(409, "conflict", f"프로필은 {MAX_PROFILES}개까지 만들 수 있어요.")
    if data.get("is_default"):
        await _clear_default(s, user_id, None)
    p = Profile(
        user_id=user_id,
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
    s: AsyncSession, user_id: int, profile_id: int, data: dict[str, Any], now: datetime
) -> Profile:
    p = await get_profile(s, user_id, profile_id)
    if "name" in data:
        p.name = data["name"]
    if "description" in data:
        p.description = data["description"]
        p.profile_hash = profile_hash(data["description"])  # 이전 점수·분석과 분리 (§4)
    if "keywords" in data:
        p.keywords = clean_keywords(data["keywords"])
    if data.get("is_default"):
        await _clear_default(s, user_id, p.id)
        p.is_default = True
    elif data.get("is_default") is False:
        p.is_default = False
    p.updated_at = now
    await s.commit()
    return p


async def delete_profile(s: AsyncSession, user_id: int, profile_id: int) -> None:
    p = await get_profile(s, user_id, profile_id)
    await s.delete(p)
    await s.commit()
