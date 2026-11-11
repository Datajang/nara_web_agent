"""/api/v1/profiles (SPEC §6.2). suggest-keywords(LLM)는 P3."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas import ProfileIn, ProfileList, ProfileOut, ProfilePatch
from app.profiles import repo

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
async def list_profiles(user: ActiveUser, s: DbSession) -> ProfileList:
    rows = await repo.list_profiles(s, user.id)
    return ProfileList(items=[ProfileOut.model_validate(p) for p in rows])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(body: ProfileIn, user: ActiveUser, s: DbSession, ctx: Ctx) -> ProfileOut:
    p = await repo.create_profile(s, user.id, body.model_dump(), ctx.deps.clock())
    return ProfileOut.model_validate(p)


@router.get("/{profile_id}")
async def get_profile(profile_id: int, user: ActiveUser, s: DbSession) -> ProfileOut:
    return ProfileOut.model_validate(await repo.get_profile(s, user.id, profile_id))


@router.patch("/{profile_id}")
async def patch_profile(
    profile_id: int, body: ProfilePatch, user: ActiveUser, s: DbSession, ctx: Ctx
) -> ProfileOut:
    p = await repo.update_profile(
        s, user.id, profile_id, body.model_dump(exclude_unset=True), ctx.deps.clock()
    )
    return ProfileOut.model_validate(p)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: int, user: ActiveUser, s: DbSession) -> Response:
    await repo.delete_profile(s, user.id, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
