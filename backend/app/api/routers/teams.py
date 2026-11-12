"""/api/v1/teams (SPEC §13 P6). 회원이 만들고 초대 코드로 들어오는 팀. 관리자는 관여하지 않는다."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.teams import JoinIn, MemberOut, MyTeamOut, TeamIn, TeamOut
from app.db.models import User
from app.teams import service

router = APIRouter(prefix="/teams", tags=["teams"])


async def _my_team(s: AsyncSession, user: User) -> MyTeamOut:
    if user.team is None:
        return MyTeamOut()
    rows = await service.members(s, user.team.id)
    return MyTeamOut(
        team=TeamOut.model_validate(user.team),
        role=user.team_role,  # type: ignore[arg-type]
        members=[
            MemberOut(
                user_id=m.id,
                display_name=m.display_name,  # 이메일은 팀원에게도 보이지 않는다
                role=m.team_role,  # type: ignore[arg-type]
                joined_at=m.team_joined_at,
            )
            for m in rows
        ],
    )


@router.get("/me")
async def get_my_team(user: ActiveUser, s: DbSession) -> MyTeamOut:
    return await _my_team(s, user)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(body: TeamIn, user: ActiveUser, s: DbSession, ctx: Ctx) -> MyTeamOut:
    await service.create(s, user, body.name, ctx.deps.clock())
    return await _my_team(s, user)


@router.post("/join")
async def join_team(body: JoinIn, user: ActiveUser, s: DbSession, ctx: Ctx) -> MyTeamOut:
    ctx.limiter.hit(f"team-join:{user.id}", 10, 60)
    await service.join(s, user, body.code, ctx.deps.clock())
    return await _my_team(s, user)


@router.patch("/me")
async def rename_team(body: TeamIn, user: ActiveUser, s: DbSession, ctx: Ctx) -> MyTeamOut:
    await service.rename(s, user, body.name, ctx.deps.clock())
    return await _my_team(s, user)


@router.post("/me/invite-code")
async def rotate_invite_code(user: ActiveUser, s: DbSession, ctx: Ctx) -> MyTeamOut:
    await service.rotate_code(s, user, ctx.deps.clock())
    return await _my_team(s, user)


@router.delete("/me/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(member_id: int, user: ActiveUser, s: DbSession) -> Response:
    await service.remove_member(s, user, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(user: ActiveUser, s: DbSession) -> Response:
    await service.leave(s, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
