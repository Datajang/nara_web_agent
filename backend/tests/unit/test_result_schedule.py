"""결과 감시 확인 간격.

설계: 개찰 전 호출 없음 → 3시간 5분 → 24시간까지 30분 → 3시간, 60일 뒤 끝.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.results.schedule import next_check

OPEN = datetime(2026, 11, 10, 1, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (timedelta(hours=-1), OPEN),  # 개찰 전: 개찰 시각까지 부르지 않음
        (timedelta(minutes=10), OPEN + timedelta(minutes=15)),
        (timedelta(hours=5), OPEN + timedelta(hours=5, minutes=30)),
        (timedelta(hours=30), OPEN + timedelta(hours=33)),
        (timedelta(days=61), None),  # 60일 지나면 그만
    ],
)
def test_next_check_table(after, expected):
    assert next_check(OPEN, OPEN + after) == expected


def test_boundaries():
    """3시간·24시간 경계는 다음 구간 간격, 60일째까지는 확인한다."""
    assert next_check(OPEN, OPEN + timedelta(hours=3)) == OPEN + timedelta(hours=3, minutes=30)
    assert next_check(OPEN, OPEN + timedelta(hours=24)) == OPEN + timedelta(hours=27)
    assert next_check(OPEN, OPEN + timedelta(days=60)) is not None
