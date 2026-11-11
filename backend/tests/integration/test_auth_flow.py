"""§9.8 수용 기준 1~8, 10, 12. 메일은 MAIL_BACKEND=memory (P2 지시)."""

from __future__ import annotations

import logging

import bcrypt
from sqlalchemy import select

from app.db.models.personal import RefreshToken, User
from tests.conftest import Api, build_api, make_auth_settings
from tests.helpers import PASSWORD, admin_client, create_user, last_token, login

A = "alice@corp.example"


async def register(client, email=A, password=PASSWORD):
    return await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "앨리스"},
    )


async def verify(client, token):
    return await client.post("/api/v1/auth/verify-email", json={"token": token})


async def raw_refresh(api: Api, token: str):
    async with api.client() as c:
        return await c.post("/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={token}"})


async def user_row(api: Api, email: str) -> User:
    async with api.db.session() as s:
        u = await s.scalar(select(User).where(User.email == email))
    assert u is not None
    return u


# 1. 가입 → 인증 → (승인) → 로그인, 상태별 거부 코드
async def test_register_verify_approve_login_flow(api, client):
    r = await register(client, "Alice@Corp.Example ")
    assert r.status_code == 201
    u = await user_row(api, A)  # 소문자 정규화
    assert u.status == "pending_verification" and u.password_hash.startswith("$argon2id$")

    r = await login(client, A)
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_not_verified"

    r = await verify(client, last_token(api.mailer, A))
    assert r.status_code == 200 and r.json()["status"] == "pending_approval"
    r = await login(client, A)
    assert r.status_code == 403 and r.json()["error"]["code"] == "pending_approval"

    admin = await admin_client(api)
    try:
        r = await admin.patch(f"/api/v1/admin/users/{u.id}", json={"status": "active"})
        assert r.status_code == 200 and r.json()["status"] == "active"
        r = await login(client, A)
        assert r.status_code == 200
        assert r.json()["email"] == A and r.json()["role"] == "member"
        assert {"access_token", "refresh_token"} <= set(r.cookies.keys())
        assert (await client.get("/api/v1/me")).json()["email"] == A

        await admin.patch(f"/api/v1/admin/users/{u.id}", json={"status": "disabled"})
        async with api.client() as fresh:
            r = await login(fresh, A)
        assert r.status_code == 403 and r.json()["error"]["code"] == "disabled"
    finally:
        await admin.aclose()


async def test_set_cookie_attributes(api, client):
    await create_user(api.db, A)
    r = await login(client, A)
    cookies = {h.split("=", 1)[0]: h for h in r.headers.get_list("set-cookie")}
    access, refresh = cookies["access_token"].lower(), cookies["refresh_token"].lower()
    for c in (access, refresh):
        assert "httponly" in c and "secure" in c and "samesite=lax" in c
    assert "path=/api;" in access + ";" and "max-age=900" in access
    assert "path=/api/v1/auth" in refresh and "max-age=1209600" in refresh


async def test_allowed_domain_policy_skips_approval(db, clock):
    api = build_api(db, make_auth_settings(allowed_email_domains="corp.example"), clock)
    async with api.client() as c:
        r = await register(c, "bob@other.example")
        assert r.status_code == 422
        assert r.json()["error"]["details"][0]["reason"] == "domain_not_allowed"
        assert (await register(c, "bob@corp.example")).status_code == 201
        r = await verify(c, last_token(api.mailer, "bob@corp.example"))
        assert r.json()["status"] == "active"
        assert (await login(c, "bob@corp.example")).status_code == 200


async def test_weak_password_rejected_with_field_detail(client):
    r = await register(client, password="1234567890")
    assert r.status_code == 422
    assert r.json()["error"]["details"] == [{"field": "password", "reason": "too_common"}]


# 2. 열거 방지
async def test_register_existing_email_same_response(api, client):
    r1 = await register(client)
    r2 = await register(client, password="another-password-xyz")
    assert (r1.status_code, r1.json()) == (r2.status_code, r2.json())
    subjects = [m.subject for m in api.mailer.outbox if m.to == A]
    assert subjects == ["[나라장터 도우미] 이메일 인증", "[나라장터 도우미] 이미 가입된 계정입니다"]


# 3. 5회 실패 → 15분 잠금, 응답은 존재 여부와 무관
async def test_lockout_after_five_failures_same_for_unknown_email(api, client):
    await create_user(api.db, A)
    bodies = []
    for email in (A, "ghost@corp.example"):
        for _ in range(5):
            r = await login(client, email, "wrong-password-0")
            assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
            bodies.append(r.json())
        r = await login(client, email, PASSWORD)  # 맞는 비밀번호여도 잠김
        assert r.status_code == 429 and r.json()["error"]["code"] == "account_locked"
        assert int(r.headers["retry-after"]) > 0
        bodies.append(r.json())
    assert bodies[:6] == bodies[6:]

    api.clock.advance(minutes=15, seconds=1)
    assert (await login(client, A)).status_code == 200


async def test_success_resets_failure_count(api, client):
    await create_user(api.db, A)
    for _ in range(4):
        await login(client, A, "wrong-password-0")
    assert (await login(client, A)).status_code == 200
    for _ in range(4):
        await login(client, A, "wrong-password-0")
    assert (await login(client, A)).status_code == 200


# 4. 만료·사용된 토큰은 400, 새 토큰이 이전 토큰을 무효화
async def test_verify_token_single_use_expiry_and_supersede(api, client):
    await register(client)
    t1 = last_token(api.mailer, A)
    r = await client.post("/api/v1/auth/verify-email/resend", json={"email": A})
    assert r.status_code == 202
    t2 = last_token(api.mailer, A)
    assert t1 != t2
    r = await verify(client, t1)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_token"
    api.clock.advance(hours=24, minutes=1)
    assert (await verify(client, t2)).status_code == 400
    await client.post("/api/v1/auth/verify-email/resend", json={"email": A})
    t3 = last_token(api.mailer, A)
    assert (await verify(client, t3)).status_code == 200
    assert (await verify(client, t3)).status_code == 400  # 재사용


async def test_resend_and_forgot_do_not_reveal_existence(api, client):
    for path in ("/api/v1/auth/verify-email/resend", "/api/v1/auth/password/forgot"):
        r1 = await client.post(path, json={"email": "ghost@corp.example"})
        r2 = await client.post(path, json={"email": A})
        assert r1.status_code == r2.status_code == 202 and r1.content == r2.content


async def test_reset_token_single_use_expiry_and_supersede(api, client):
    await create_user(api.db, A)
    await client.post("/api/v1/auth/password/forgot", json={"email": A})
    t1 = last_token(api.mailer, A)
    await client.post("/api/v1/auth/password/forgot", json={"email": A})
    t2 = last_token(api.mailer, A)
    reset = "/api/v1/auth/password/reset"
    new_pw = "brand-new-password-1"
    r = await client.post(reset, json={"token": t1, "password": new_pw})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_token"
    assert (await client.post(reset, json={"token": t2, "password": new_pw})).status_code == 204
    assert (await client.post(reset, json={"token": t2, "password": new_pw})).status_code == 400
    assert (await login(client, A, new_pw)).status_code == 200

    await client.post("/api/v1/auth/password/forgot", json={"email": A})
    t3 = last_token(api.mailer, A)
    api.clock.advance(minutes=61)
    assert (await client.post(reset, json={"token": t3, "password": new_pw})).status_code == 400


# 5. refresh 재사용 → 같은 가족 전부 폐기
async def test_refresh_rotation_and_reuse_detection(api, client):
    await create_user(api.db, A)
    r = await login(client, A)
    r1 = r.cookies["refresh_token"]
    rr = await raw_refresh(api, r1)
    assert rr.status_code == 200
    r2 = rr.cookies["refresh_token"]
    assert r2 != r1 and "access_token" in rr.cookies

    reuse = await raw_refresh(api, r1)
    assert reuse.status_code == 401
    assert (await raw_refresh(api, r2)).status_code == 401  # 가족 전체 폐기
    async with api.db.session() as s:
        rows = (await s.scalars(select(RefreshToken))).all()
    assert rows and all(t.revoked_at is not None for t in rows)


async def test_refresh_expired_is_401(api, client):
    await create_user(api.db, A)
    r1 = (await login(client, A)).cookies["refresh_token"]
    api.clock.advance(days=14, seconds=1)
    assert (await raw_refresh(api, r1)).status_code == 401


async def test_access_expiry_then_refresh(api, client):
    await create_user(api.db, A)
    await login(client, A)
    api.clock.advance(minutes=16)
    r = await client.get("/api/v1/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200
    assert (await client.get("/api/v1/me")).status_code == 200


# 6. 비밀번호 변경·재설정 → 기존 refresh 전부 무효
async def test_password_change_revokes_other_sessions(api):
    await create_user(api.db, A)
    async with api.client() as c1, api.client() as c2:
        await login(c1, A)
        other = (await login(c2, A)).cookies["refresh_token"]
        r = await c1.patch(
            "/api/v1/me",
            json={"current_password": PASSWORD, "new_password": "changed-password-77"},
        )
        assert r.status_code == 200
        assert (await raw_refresh(api, other)).status_code == 401
        assert (await c1.post("/api/v1/auth/refresh")).status_code == 200  # 바꾼 쪽은 유지
        bad = await c1.patch(
            "/api/v1/me",
            json={"current_password": "not-the-password", "new_password": "x-changed-pass-9"},
        )
        assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_password"


async def test_password_reset_revokes_sessions(api, client):
    await create_user(api.db, A)
    old = (await login(client, A)).cookies["refresh_token"]
    await client.post("/api/v1/auth/password/forgot", json={"email": A})
    await client.post(
        "/api/v1/auth/password/reset",
        json={"token": last_token(api.mailer, A), "password": "after-reset-pass-1"},
    )
    assert (await raw_refresh(api, old)).status_code == 401


async def test_patch_me_display_name(api, client):
    await create_user(api.db, A)
    await login(client, A)
    r = await client.patch("/api/v1/me", json={"display_name": "새 이름"})
    assert r.status_code == 200 and r.json()["display_name"] == "새 이름"


async def test_logout_revokes_and_clears(api, client):
    await create_user(api.db, A)
    rt = (await login(client, A)).cookies["refresh_token"]
    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert all("max-age=0" in h.lower() for h in r.headers.get_list("set-cookie"))
    assert (await raw_refresh(api, rt)).status_code == 401


# 7. 비활성화하면 이미 받은 access 토큰으로도 403
async def test_disable_blocks_existing_access_token(api, client):
    uid = await create_user(api.db, A)
    await login(client, A)
    assert (await client.get("/api/v1/me")).status_code == 200
    admin = await admin_client(api)
    try:
        await admin.patch(f"/api/v1/admin/users/{uid}", json={"status": "disabled"})
    finally:
        await admin.aclose()
    r = await client.get("/api/v1/me")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


# 8. Origin 검사
async def test_state_change_requires_matching_origin(api):
    await create_user(api.db, A)
    async with api.client(origin=None) as c:
        r = await login(c, A)
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    async with api.client(origin="https://evil.example") as c:
        assert (await login(c, A)).status_code == 403
    async with api.client(origin=None) as c:
        assert (await c.get("/healthz")).status_code == 200  # GET은 검사하지 않음


# 10. bcrypt 해시 이전
async def test_bcrypt_hash_upgraded_on_login(api, client):
    legacy = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
    await create_user(api.db, A, password_hash=legacy)
    assert (await login(client, A)).status_code == 200
    assert (await user_row(api, A)).password_hash.startswith("$argon2id$")


# 12. 로그 샘플에 비밀번호·토큰·쿠키 값이 없다
async def test_logs_contain_no_secrets(api, client, caplog):
    caplog.set_level(logging.DEBUG)
    await register(client)
    token = last_token(api.mailer, A)
    await verify(client, token)
    admin = await admin_client(api)
    uid = (await user_row(api, A)).id
    await admin.patch(f"/api/v1/admin/users/{uid}", json={"status": "active"})
    await admin.aclose()
    r = await login(client, A)
    await client.post("/api/v1/auth/refresh")
    await login(client, A, "wrong-password-0")
    secrets = [PASSWORD, token, r.cookies["refresh_token"], r.cookies["access_token"]]
    assert caplog.records  # 무언가는 남긴다
    for secret in secrets:
        assert secret not in caplog.text
