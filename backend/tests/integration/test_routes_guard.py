"""§9.8-11, §6.5: 모든 경로의 인증 의존성 검사와 관리자 경로 범위."""

import re

import pytest

from app.api.app import iter_routes
from app.api.deps import current_user, require_admin
from tests.conftest import build_api, make_auth_settings

PUBLIC = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/verify-email/resend"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),  # refresh 쿠키만으로 동작(access 만료 후에도 로그아웃 가능)
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
    ("GET", "/healthz"),
}
ADMIN_ALLOWED = re.compile(r"^/api/v1/admin/(users|usage|collector)(/|$)")


def _calls(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _calls(d)


def _routes(app):
    routes = list(iter_routes(app))
    assert len(routes) > 15, "라우트 순회가 비어 있으면 검사가 무의미하다"
    return routes


@pytest.fixture
def app(db):
    return build_api(db, make_auth_settings()).app


def test_every_non_public_route_requires_login(app):
    for method, path, route in _routes(app):
        if (method, path) in PUBLIC or not path.startswith("/api/"):
            continue
        assert current_user in set(_calls(route.dependant)), f"{method} {path} 인증 없음"


def test_admin_routes_require_admin_and_stay_in_scope(app):
    admin_routes = [(m, p, r) for m, p, r in _routes(app) if p.startswith("/api/v1/admin")]
    assert admin_routes
    for method, path, route in admin_routes:
        assert require_admin in set(_calls(route.dependant)), f"{method} {path}"
        # 관리자도 다른 사용자의 프로필·대화·검색어 본문을 보는 API는 없다 (§9.4)
        assert ADMIN_ALLOWED.match(path), path


async def test_unauthenticated_calls_get_401(api, client):
    for method, full, _ in _routes(api.app):
        if (method, full) in PUBLIC or not full.startswith("/api/v1"):
            continue
        path = re.sub(r"\{[^}]+\}", "1", full)
        r = await client.request(method, path, json={})
        assert r.status_code == 401, f"{method} {path} → {r.status_code}"


def test_dev_mail_route_only_in_development_with_memory(db):
    def paths(**kw):
        return {p for _, p, _ in iter_routes(build_api(db, make_auth_settings(**kw)).app)}

    assert "/api/v1/_dev/mail" in paths(env="development", mail_backend="memory")
    assert "/api/v1/_dev/mail" not in paths(env="development", mail_backend="console")
    assert "/api/v1/_dev/mail" not in paths(env="test", mail_backend="memory")


async def test_dev_mail_route_lists_outbox(db):
    api = build_api(db, make_auth_settings(env="development", mail_backend="memory"))
    async with api.client() as c:
        await c.post(
            "/api/v1/auth/register",
            json={"email": "dev@corp.example", "password": "dev-password-123", "display_name": ""},
        )
        items = (await c.get("/api/v1/_dev/mail")).json()["items"]
    assert items[-1]["to"] == "dev@corp.example" and "verify-email?token=" in items[-1]["body"]
