"""§11.7 요청 로그: request_id를 만들고 응답 헤더로 돌려주며, 경로에서 쿼리스트링을 뺀다."""

import logging

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.request_log import RequestLogMiddleware
from app.logging_setup import current_context


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLogMiddleware)

    @app.get("/api/v1/x")
    async def x() -> dict[str, object]:
        ctx = current_context()
        ctx["user_id"] = 9  # 인증 의존성이 하는 일
        return {"rid": ctx.get("request_id")}

    @app.get("/healthz")
    async def h() -> dict[str, str]:
        return {"status": "ok"}

    return app


async def _get(path: str, headers: dict[str, str] | None = None):
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as c:
        return await c.get(path, headers=headers)


async def test_request_id_generated_and_returned(caplog):
    caplog.set_level(logging.INFO, logger="app.request")
    r = await _get("/api/v1/x?q=비밀검색어&ServiceKey=ABC")
    rid = r.headers["x-request-id"]
    assert len(rid) >= 8 and r.json()["rid"] == rid
    rec = next(x for x in caplog.records if getattr(x, "event", None) == "http")
    assert rec.path == "/api/v1/x"  # 쿼리스트링(검색어·키)은 남기지 않는다
    assert rec.status == 200 and rec.method == "GET" and rec.user_id == 9
    assert isinstance(rec.duration_ms, int)
    assert "비밀검색어" not in caplog.text and "ABC" not in caplog.text


async def test_safe_incoming_request_id_is_kept_unsafe_is_replaced():
    assert (await _get("/api/v1/x", {"X-Request-ID": "abc-123_DEF"})).headers[
        "x-request-id"
    ] == "abc-123_DEF"
    bad = (await _get("/api/v1/x", {"X-Request-ID": "x\nforged log line"})).headers["x-request-id"]
    assert "\n" not in bad and "forged" not in bad


async def test_health_probes_are_not_logged_at_info(caplog):
    caplog.set_level(logging.INFO, logger="app.request")
    await _get("/healthz")
    assert not [x for x in caplog.records if getattr(x, "event", None) == "http"]


async def test_create_app_installs_middleware():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/healthz")
    assert r.headers.get("x-request-id")
