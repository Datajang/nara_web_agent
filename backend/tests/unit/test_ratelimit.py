"""§6.1 인메모리 토큰 버킷."""

from datetime import UTC, datetime, timedelta

import pytest

from app.api.ratelimit import RateLimiter
from app.errors import ApiError


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 10, tzinfo=UTC)

    def __call__(self):
        return self.now


def test_bucket_allows_limit_then_429_with_retry_after():
    clock = Clock()
    rl = RateLimiter(clock)
    for _ in range(5):
        rl.hit("login:ip:1.2.3.4", 5, 60)
    with pytest.raises(ApiError) as e:
        rl.hit("login:ip:1.2.3.4", 5, 60)
    assert e.value.status == 429 and e.value.code == "rate_limited"
    assert e.value.retry_after is not None and 1 <= e.value.retry_after <= 60


def test_bucket_refills_and_keys_are_independent():
    clock = Clock()
    rl = RateLimiter(clock)
    for _ in range(5):
        rl.hit("k1", 5, 60)
    rl.hit("k2", 5, 60)  # 다른 키는 영향 없음
    clock.now += timedelta(seconds=12)  # 1개 회복
    rl.hit("k1", 5, 60)
    with pytest.raises(ApiError):
        rl.hit("k1", 5, 60)


def test_disabled_limiter_never_blocks():
    rl = RateLimiter(Clock(), enabled=False)
    for _ in range(100):
        rl.hit("k", 1, 3600)
