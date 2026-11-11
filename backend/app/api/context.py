"""API 앱이 쓰는 의존성 묶음. 테스트는 가짜 메일러·고정 시계를 넣는다."""

from __future__ import annotations

from dataclasses import dataclass

from app.api.ratelimit import RateLimiter
from app.auth.mail import Mailer
from app.deps import Deps


@dataclass
class AppContext:
    deps: Deps
    mailer: Mailer
    limiter: RateLimiter
