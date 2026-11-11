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
