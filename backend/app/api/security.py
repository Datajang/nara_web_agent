"""쿠키와 CSRF(Origin 검사) (SPEC §9.3). 쿠키 이름·경로는 이 파일에서만 정의한다."""

from __future__ import annotations

import json

from fastapi import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.service import AuthSession
from app.config import Settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
ACCESS_PATH = "/api"
REFRESH_PATH = "/api/v1/auth"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def set_auth_cookies(resp: Response, session: AuthSession, settings: Settings) -> None:
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax"}
    resp.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=settings.access_token_minutes * 60,
        path=ACCESS_PATH,
        **common,  # type: ignore[arg-type]
    )
    resp.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=settings.refresh_token_days * 86400,
        path=REFRESH_PATH,
        **common,  # type: ignore[arg-type]
    )


def clear_auth_cookies(resp: Response, settings: Settings) -> None:
    for name, path in ((ACCESS_COOKIE, ACCESS_PATH), (REFRESH_COOKIE, REFRESH_PATH)):
        resp.delete_cookie(
            name, path=path, secure=settings.cookie_secure, httponly=True, samesite="lax"
        )


class OriginCheckMiddleware:
    """상태를 바꾸는 /api 요청은 Origin이 APP_ORIGIN과 같아야 한다. 없으면 403 (§9.3)."""

    def __init__(self, app: ASGIApp, origin: str) -> None:
        self.app = app
        self.origin = origin.rstrip("/").encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in UNSAFE_METHODS
            and scope["path"].startswith("/api/")
        ):
            origin = dict(scope["headers"]).get(b"origin")
            if origin != self.origin:
                body = json.dumps(
                    {
                        "error": {
                            "code": "forbidden",
                            "message": "허용되지 않은 출처의 요청이에요.",
                            "details": [{"field": "origin", "reason": "origin_mismatch"}],
                        }
                    },
                    ensure_ascii=False,
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
