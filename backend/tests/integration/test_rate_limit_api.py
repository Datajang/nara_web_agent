"""§6.1 속도 제한: 로그인은 IP·이메일 기준 분당 5회."""

from tests.conftest import build_api, make_auth_settings
from tests.helpers import login


async def test_login_rate_limited_per_minute(db, clock):
    api = build_api(db, make_auth_settings(rate_limit_enabled=True), clock)
    async with api.client() as c:
        for i in range(5):
            await login(c, f"u{i}@corp.example", "wrong-password-0")
        r = await login(c, "u9@corp.example", "wrong-password-0")
        assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1
        clock.advance(minutes=1)
        assert (await login(c, "u9@corp.example", "wrong-password-0")).status_code == 401


async def test_register_rate_limited_per_hour(db, clock):
    api = build_api(db, make_auth_settings(rate_limit_enabled=True), clock)
    async with api.client() as c:
        for i in range(5):
            r = await c.post(
                "/api/v1/auth/register",
                json={
                    "email": f"r{i}@corp.example",
                    "password": "reg-password-123",
                    "display_name": "",
                },
            )
            assert r.status_code == 201
        r = await c.post(
            "/api/v1/auth/register",
            json={"email": "r9@corp.example", "password": "reg-password-123", "display_name": ""},
        )
        assert r.status_code == 429
