"""FastAPI 앱 조립 (SPEC §6). 모든 경로는 /api/v1 아래, /healthz만 루트(배포 스크립트 §11.6)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.context import AppContext
from app.api.routers import admin, auth, dev, me, profiles
from app.api.security import OriginCheckMiddleware
from app.auth.mail import MemoryMailer
from app.config import check_startup
from app.errors import ApiError

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
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)

    routers: list[APIRouter] = [auth.router, me.router, profiles.router, admin.router]
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
