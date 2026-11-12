"""FastAPI 앱 조립 (SPEC §6). 모든 경로는 /api/v1 아래, /healthz만 루트(배포 스크립트 §11.6)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager
from typing import Any, get_args

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic.json_schema import models_json_schema
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.context import AppContext
from app.api.request_log import RequestLogMiddleware
from app.api.routers import (
    admin,
    analyze,
    assistant,
    auth,
    bids,
    dev,
    feed,
    feedback,
    history,
    me,
    profiles,
    recommend,
    teams,
)
from app.api.schemas.events import EVENT_MODELS
from app.api.security import OriginCheckMiddleware
from app.auth.mail import MemoryMailer
from app.config import check_startup
from app.errors import ApiError
from app.llm.base import LLMInvalidOutput, LLMUnavailable
from app.ops.status import collector_state, last_collector_ok

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "rate_limited",
}


def _json(err: ApiError) -> JSONResponse:
    headers = {"Retry-After": str(err.retry_after)} if err.retry_after else None
    return JSONResponse(err.body(), status_code=err.status, headers=headers)


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return _json(exc)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "reason": e["type"]}
        for e in exc.errors()
    ]
    return _json(ApiError(422, "validation_error", "입력값을 확인해 주세요.", details=details))


async def _llm_error(_: Request, exc: Exception) -> JSONResponse:
    """SSE가 아닌 경로의 LLM 실패 (§8.7). SSE는 api/sse.py가 error 이벤트로 바꾼다."""
    if isinstance(exc, LLMUnavailable):
        return _json(ApiError(503, "llm_unavailable", "지금은 AI 응답이 어려워요."))
    return _json(ApiError(502, "llm_invalid_output", "AI 응답 형식이 올바르지 않았어요."))


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "error")
    return _json(ApiError(exc.status_code, code, str(exc.detail)))


def create_app(
    ctx: AppContext,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[Any]] | None = None,
) -> FastAPI:
    settings = ctx.deps.settings
    for warning in check_startup(settings):  # 운영에서 위험한 설정이면 ConfigError로 멈춘다
        log.warning("config: %s", warning)

    app = FastAPI(title="nara-web", version="2.0.0.dev0", lifespan=lifespan)
    app.state.ctx = ctx
    app.add_middleware(OriginCheckMiddleware, origin=settings.app_origin)
    app.add_middleware(RequestLogMiddleware)  # 가장 바깥: 403·422 응답도 기록한다
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(LLMUnavailable, _llm_error)
    app.add_exception_handler(LLMInvalidOutput, _llm_error)

    routers: list[APIRouter] = [
        auth.router,
        me.router,
        profiles.router,
        teams.router,
        feed.router,
        bids.router,
        analyze.router,
        recommend.router,
        assistant.router,
        history.router,
        feedback.router,
        admin.router,
    ]
    if (
        settings.env == "development"
        and settings.mail_backend == "memory"
        and isinstance(ctx.mailer, MemoryMailer)
    ):
        routers.append(dev.router)
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)
    app.state.api_routers = routers

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz() -> JSONResponse:
        """DB·LLM·마지막 수집 성공 시각 (§6.2, §11.7). LLM만 불가면 200, DB 불가면 503."""
        db_ok = True
        try:
            async with ctx.deps.db.session() as s:
                await s.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        llm = ctx.deps.llm
        llm_state = "disabled" if llm is None else ("ok" if await llm.health() else "unavailable")
        last_ok = await last_collector_ok(ctx.deps) if db_ok else None
        body: dict[str, Any] = {
            "db": "ok" if db_ok else "error",
            "llm": llm_state,
            "collector": collector_state(ctx.deps, last_ok),
            "collector_last_ok_at": last_ok.isoformat() if last_ok else None,
        }
        # 수집 지연은 경보(app.ops.check)가 잡는다. DB가 살아 있으면 검색은 되므로 200.
        return JSONResponse(body, status_code=200 if db_ok else 503)

    base_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        """SSE 이벤트 모델을 components에 추가해 프론트 타입으로 내보낸다 (§6.4)."""
        schema = base_openapi()
        comps = schema.setdefault("components", {}).setdefault("schemas", {})
        if "SseEvent" not in comps:
            _, defs = models_json_schema(
                [(m, "serialization") for m in EVENT_MODELS],
                ref_template="#/components/schemas/{model}",
            )
            comps.update(defs.get("$defs", {}))
            comps["SseEvent"] = {
                "oneOf": [{"$ref": f"#/components/schemas/{m.__name__}"} for m in EVENT_MODELS],
                "discriminator": {
                    "propertyName": "type",
                    "mapping": {
                        get_args(m.model_fields["type"].annotation)[0]: (
                            f"#/components/schemas/{m.__name__}"
                        )
                        for m in EVENT_MODELS
                    },
                },
            }
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


def iter_routes(app: FastAPI) -> Iterator[tuple[str, str, APIRoute]]:
    """(메서드, 전체 경로, 라우트) 목록. 권한 검사 테스트용.

    FastAPI 0.16x는 include_router를 지연 포함해 app.routes에 하위 라우트가 펼쳐지지 않는다.
    그래서 create_app이 기록한 라우터를 직접 순회한다.
    """
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in r.methods or ():
                yield m, r.path, r
    for router in app.state.api_routers:
        for r in router.routes:
            if isinstance(r, APIRoute):
                for m in r.methods or ():
                    yield m, API_PREFIX + r.path, r
