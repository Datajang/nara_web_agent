"""API 앱이 쓰는 의존성 묶음. 테스트는 가짜 메일러·고정 시계를 넣는다."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.api.ratelimit import RateLimiter
from app.auth.mail import Mailer
from app.deps import Deps


@dataclass
class AppContext:
    deps: Deps
    mailer: Mailer
    limiter: RateLimiter
    closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)  # 종료 시 정리
