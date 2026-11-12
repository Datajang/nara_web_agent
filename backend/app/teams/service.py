"""팀 (SPEC §13 P6). 관리자 없이 회원이 만들고 초대 코드로 들어온다. 한 계정 한 팀(users.team_id).

권한: 팀원은 팀 정보·초대 코드를 보고 팀 프로필을 만들고 고친다. 팀장(owner)만 이름 변경,
초대 코드 재발급, 팀원 내보내기, 팀 프로필 삭제. 팀장이 나가면 가장 먼저 들어온 팀원이 잇고,
혼자였으면 팀이 사라진다(팀 프로필은 CASCADE).
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Team, User
from app.errors import ApiError

# 헷갈리는 글자(0·O·1·I·L) 제외. 10자 ≈ 50비트, 시도는 사용자당 10회/분으로 제한
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LEN = 10


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


def normalize_code(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def already_in_team() -> ApiError:
    return ApiError(
        409,
        "already_in_team",
        "이미 팀에 속해 있어요. 다른 팀에 들어가려면 먼저 지금 팀에서 나와 주세요.",
    )


def not_owner() -> ApiError:
    return ApiError(403, "not_team_owner", "팀장만 할 수 있어요.")


def no_team() -> ApiError:
    return ApiError(
        409, "no_team", "팀에 속해 있지 않아요. 팀을 만들거나 초대 코드로 들어와 주세요."
    )


async def _set_code(s: AsyncSession, team: Team) -> None:
    for _ in range(5):  # 충돌은 사실상 없지만 UNIQUE라 재시도
        team.invite_code = new_code()
        try:
            async with s.begin_nested():
                await s.flush()
            return
        except IntegrityError:
            continue
    raise ApiError(503, "unavailable", "초대 코드를 만들지 못했어요. 잠시 후 다시 시도해 주세요.")


def _join(user: User, team: Team, role: str, now: datetime) -> None:
    user.team = team
    user.team_role = role
    user.team_joined_at = now


async def create(s: AsyncSession, user: User, name: str, now: datetime) -> Team:
    if user.team_id is not None:
        raise already_in_team()
    team = Team(name=name, invite_code="", created_at=now, updated_at=now)
    s.add(team)
    await _set_code(s, team)
    _join(user, team, "owner", now)
    await s.commit()
    return team


async def join(s: AsyncSession, user: User, code: str, now: datetime) -> Team:
    if user.team_id is not None:
        raise already_in_team()
    team = await s.scalar(select(Team).where(Team.invite_code == normalize_code(code)))
    if team is None:
        raise ApiError(
            404, "invalid_invite", "초대 코드가 맞지 않아요. 팀원에게 새 코드를 받아 주세요."
        )
    _join(user, team, "member", now)
    await s.commit()
    return team


def require_team(user: User) -> Team:
    if user.team is None:
        raise no_team()
    return user.team


def require_owner(user: User) -> Team:
    team = require_team(user)
    if user.team_role != "owner":
        raise not_owner()
    return team


async def members(s: AsyncSession, team_id: int) -> list[User]:
    rows = await s.scalars(
        select(User).where(User.team_id == team_id).order_by(User.team_joined_at, User.id)
    )
    return list(rows)


async def rename(s: AsyncSession, user: User, name: str, now: datetime) -> Team:
    team = require_owner(user)
    team.name = name
    team.updated_at = now
    await s.commit()
    return team


async def rotate_code(s: AsyncSession, user: User, now: datetime) -> Team:
    team = require_owner(user)
    await _set_code(s, team)
    team.updated_at = now
    await s.commit()
    return team


def _leave(u: User) -> None:
    u.team = None
    u.team_role = None
    u.team_joined_at = None


async def remove_member(s: AsyncSession, user: User, member_id: int) -> None:
    team = require_owner(user)
    if member_id == user.id:
        raise ApiError(
            422, "validation_error", "팀장은 자신을 내보낼 수 없어요. 팀에서 나가기를 써 주세요."
        )
    target = await s.scalar(select(User).where(User.id == member_id, User.team_id == team.id))
    if target is None:
        raise ApiError(404, "not_found", "팀원을 찾을 수 없어요.")
    _leave(target)
    await s.commit()


async def leave(s: AsyncSession, user: User) -> None:
    team = require_team(user)
    was_owner = user.team_role == "owner"
    _leave(user)
    await s.flush()
    rest = await members(s, team.id)
    if not rest:
        await s.delete(team)  # 팀 프로필은 CASCADE로 함께 사라진다
    elif was_owner:
        rest[0].team_role = "owner"  # 가장 먼저 들어온 팀원이 잇는다
    await s.commit()


async def member_count(s: AsyncSession, team_id: int) -> int:
    return (
        await s.scalar(select(func.count()).select_from(User).where(User.team_id == team_id)) or 0
    )
