"""§9.4 첫 관리자는 CLI로 만든다."""

from sqlalchemy import select

from app.cli import create_admin
from app.db.models.personal import User
from tests.helpers import create_user, login


async def test_create_admin_new_user_can_login(api, client):
    assert await create_admin(api.db, "Root@Corp.Example", "admin-password-123") == "created"
    async with api.db.session() as s:
        u = await s.scalar(select(User).where(User.email == "root@corp.example"))
    assert u and u.role == "admin" and u.status == "active" and u.email_verified_at
    r = await login(client, "root@corp.example", "admin-password-123")
    assert r.status_code == 200 and r.json()["role"] == "admin"


async def test_create_admin_existing_user_is_promoted_only(api):
    uid = await create_user(api.db, "m@corp.example")
    async with api.db.session() as s:
        before = await s.scalar(select(User.password_hash).where(User.id == uid))
    assert await create_admin(api.db, "m@corp.example", "ignored-password-1") == "promoted"
    async with api.db.session() as s:
        u = await s.scalar(select(User).where(User.id == uid))
    assert u.role == "admin" and u.password_hash == before


async def test_create_admin_rejects_weak_password(api):
    import pytest

    from app.auth.passwords import PasswordPolicyError

    with pytest.raises(PasswordPolicyError):
        await create_admin(api.db, "x@corp.example", "short")


# ---------- team-assign: 관리자가 계정을 팀에 배정 (2026-11-25) ----------


async def _teams(db):
    from app.db.models.personal import Team

    async with db.session() as s:
        users = (await s.scalars(select(User).order_by(User.email))).all()
        names = {t.id: t.name for t in (await s.scalars(select(Team))).all()}
    return {u.email: (names.get(u.team_id), u.team_role) for u in users}


async def test_assign_team_creates_team_with_owner_and_members(api):
    from app.cli import assign_team
    from app.deps import utcnow

    for e in ("lead@corp.example", "a@corp.example", "b@corp.example"):
        await create_user(api.db, e)
    lines = await assign_team(
        api.db, "AX컨설팅2팀", ["A@corp.example", "b@corp.example"], "lead@corp.example", utcnow()
    )
    assert any("새로 만들었" in x for x in lines)
    assert await _teams(api.db) == {
        "a@corp.example": ("AX컨설팅2팀", "member"),
        "b@corp.example": ("AX컨설팅2팀", "member"),
        "lead@corp.example": ("AX컨설팅2팀", "owner"),
    }


async def test_assign_team_adds_to_existing_team_and_skips_current_members(api):
    from app.cli import assign_team
    from app.deps import utcnow

    for e in ("lead@corp.example", "a@corp.example", "new@corp.example"):
        await create_user(api.db, e)
    await assign_team(api.db, "AX컨설팅1팀", ["a@corp.example"], "lead@corp.example", utcnow())
    lines = await assign_team(
        api.db, "AX컨설팅1팀", ["a@corp.example", "new@corp.example"], None, utcnow()
    )
    assert any("이미" in x and "a@corp.example" in x for x in lines)
    t = await _teams(api.db)
    assert t["new@corp.example"] == ("AX컨설팅1팀", "member")
    assert t["lead@corp.example"] == ("AX컨설팅1팀", "owner")


async def test_assign_team_owner_transfer_demotes_previous_owner(api):
    from app.cli import assign_team
    from app.deps import utcnow

    for e in ("old@corp.example", "new@corp.example"):
        await create_user(api.db, e)
    await assign_team(api.db, "팀", [], "old@corp.example", utcnow())
    await assign_team(api.db, "팀", [], "new@corp.example", utcnow())
    t = await _teams(api.db)
    assert t["new@corp.example"] == ("팀", "owner")
    assert t["old@corp.example"] == ("팀", "member")


async def test_assign_team_rejects_and_changes_nothing(api):
    import pytest

    from app.cli import TeamAssignError, assign_team
    from app.deps import utcnow

    for e in ("lead@corp.example", "other@corp.example", "ok@corp.example"):
        await create_user(api.db, e)
    await create_user(api.db, "wait@corp.example", status="pending_approval")
    await assign_team(api.db, "다른팀", [], "other@corp.example", utcnow())
    before = await _teams(api.db)
    cases = [
        # 다른 팀 소속, 없는 계정, 승인 전 계정, 팀이 없는데 팀장 미지정
        ("AX컨설팅2팀", ["ok@corp.example", "other@corp.example"], "lead@corp.example"),
        ("AX컨설팅2팀", ["ok@corp.example", "nobody@corp.example"], "lead@corp.example"),
        ("AX컨설팅2팀", ["wait@corp.example"], "lead@corp.example"),
        ("AX컨설팅2팀", ["ok@corp.example"], None),
    ]
    for name, emails, owner in cases:
        with pytest.raises(TeamAssignError):
            await assign_team(api.db, name, emails, owner, utcnow())
    assert await _teams(api.db) == before
