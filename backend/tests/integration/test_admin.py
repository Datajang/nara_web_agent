"""§9.4 권한, §7.9 관리자 사용자 관리."""

from sqlalchemy import select

from app.db.models.personal import RefreshToken
from tests.helpers import admin_client, create_user, login


async def test_admin_routes_require_admin(api, client):
    assert (await client.get("/api/v1/admin/users")).status_code == 401
    await create_user(api.db, "m@corp.example")
    await login(client, "m@corp.example")
    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_list_users_filters_by_status(api):
    await create_user(api.db, "p@corp.example", status="pending_approval")
    await create_user(api.db, "d@corp.example", status="disabled")
    admin = await admin_client(api)
    try:
        r = await admin.get("/api/v1/admin/users", params={"status": "pending_approval"})
        assert r.status_code == 200
        body = r.json()
        assert [u["email"] for u in body["items"]] == ["p@corp.example"]
        assert body["total"] == 1
        assert set(body["items"][0]) == {
            "id",
            "email",
            "display_name",
            "role",
            "status",
            "email_verified_at",
            "last_login_at",
            "created_at",
            "team",
            "team_role",
        }
        r = await admin.get("/api/v1/admin/users", params={"limit": 2, "offset": 0})
        assert len(r.json()["items"]) == 2 and r.json()["total"] == 3
    finally:
        await admin.aclose()


async def test_admin_cannot_demote_or_disable_self(api):
    admin = await admin_client(api)
    try:
        me = (await admin.get("/api/v1/me")).json()
        for patch in ({"role": "member"}, {"status": "disabled"}):
            r = await admin.patch(f"/api/v1/admin/users/{me['id']}", json=patch)
            assert r.status_code == 400 and r.json()["error"]["code"] == "cannot_modify_self"
    finally:
        await admin.aclose()


async def test_role_change_and_unknown_user(api):
    uid = await create_user(api.db, "m@corp.example")
    admin = await admin_client(api)
    try:
        r = await admin.patch(f"/api/v1/admin/users/{uid}", json={"role": "admin"})
        assert r.status_code == 200 and r.json()["role"] == "admin"
        assert (
            await admin.patch("/api/v1/admin/users/99999", json={"role": "admin"})
        ).status_code == 404
        r = await admin.patch(f"/api/v1/admin/users/{uid}", json={"status": "pending_verification"})
        assert r.status_code == 422
    finally:
        await admin.aclose()


async def test_disabling_revokes_refresh_tokens(api, client):
    uid = await create_user(api.db, "m@corp.example")
    await login(client, "m@corp.example")
    admin = await admin_client(api)
    try:
        await admin.patch(f"/api/v1/admin/users/{uid}", json={"status": "disabled"})
    finally:
        await admin.aclose()
    async with api.db.session() as s:
        rows = (await s.scalars(select(RefreshToken).where(RefreshToken.user_id == uid))).all()
    assert rows and all(t.revoked_at is not None for t in rows)


async def test_list_users_shows_team_and_role(api):
    # 사용자 관리 '활성'에서 소속 팀·팀장 여부를 본다 (2026-11-25 사용자 요청)
    from app.cli import assign_team
    from app.deps import utcnow

    await create_user(api.db, "lead@corp.example")
    await create_user(api.db, "mem@corp.example")
    await create_user(api.db, "solo@corp.example")
    await assign_team(api.db, "AX컨설팅2팀", ["mem@corp.example"], "lead@corp.example", utcnow())
    admin = await admin_client(api)
    try:
        r = await admin.get("/api/v1/admin/users", params={"status": "active"})
        by = {u["email"]: u for u in r.json()["items"]}
        assert by["lead@corp.example"]["team"]["name"] == "AX컨설팅2팀"
        assert by["lead@corp.example"]["team_role"] == "owner"
        assert by["mem@corp.example"]["team_role"] == "member"
        assert by["solo@corp.example"]["team"] is None
        assert by["solo@corp.example"]["team_role"] is None
    finally:
        await admin.aclose()
