"""속도 제한 (SPEC §6.1): 단일 서버 인메모리 토큰 버킷. uvicorn 워커 1개 전제(§11.3)."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime

from app.errors import ApiError

_MAX_KEYS = 50_000  # 메모리 상한. 넘으면 가득 찬(=오래 안 쓴) 버킷부터 정리


class RateLimiter:
    def __init__(self, clock: Callable[[], datetime], enabled: bool = True) -> None:
        self.clock = clock
        self.enabled = enabled
        self._buckets: dict[str, tuple[float, float]] = {}  # key → (토큰, 마지막 시각)

    def hit(self, key: str, limit: int, per_seconds: int) -> None:
        """한도를 넘으면 ApiError(429, rate_limited, retry_after)."""
        if not self.enabled:
            return
        now = self.clock().timestamp()
        rate = limit / per_seconds
        tokens, last = self._buckets.get(key, (float(limit), now))
        tokens = min(float(limit), tokens + (now - last) * rate)
        if tokens < 1:
            self._buckets[key] = (tokens, now)
            retry = max(1, math.ceil((1 - tokens) / rate))
            raise ApiError(
                429,
                "rate_limited",
                "요청이 너무 많아요. 잠시 후 다시 시도해 주세요.",
                retry_after=retry,
            )
        self._buckets[key] = (tokens - 1, now)
        if len(self._buckets) > _MAX_KEYS:
            self._prune(now)

    def _prune(self, now: float) -> None:
        for k, (_, last) in list(self._buckets.items()):
            if now - last > 3600:
                del self._buckets[k]
