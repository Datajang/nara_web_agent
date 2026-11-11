"""요청 로그 미들웨어 (§11.7). 순수 ASGI라 SSE 스트림을 버퍼링하지 않는다.

- request_id: 안전한 X-Request-ID가 오면 그대로, 아니면 새로 만든다. 응답 헤더로 돌려준다.
- 경로만 남기고 쿼리스트링은 남기지 않는다(검색어·토큰이 실릴 수 있음).
- /healthz·/readyz는 점검이 자주 부르므로 DEBUG로 남긴다.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_setup import log_context

log = logging.getLogger("app.request")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_QUIET = frozenset({"/healthz", "/readyz"})


class RequestLogMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex[:16]
        status = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"] = [
                    *message["headers"],
                    (b"x-request-id", rid.encode()),
                ]
            await send(message)

        with log_context(request_id=rid) as ctx:
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                path = scope["path"]
                log.log(
                    logging.DEBUG if path in _QUIET else logging.INFO,
                    "%s %s %d",
                    scope["method"],
                    path,
                    status,
                    extra={
                        "event": "http",
                        "method": scope["method"],
                        "path": path,
                        "status": status,
                        "duration_ms": int((time.perf_counter() - started) * 1000),
                        "request_id": rid,
                        "user_id": ctx.get("user_id"),
                    },
                )
