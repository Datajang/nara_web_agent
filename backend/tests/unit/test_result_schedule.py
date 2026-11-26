"""결과 감시 확인 간격.

설계: 개찰 전 호출 없음. 개찰 결과 대기(waiting)는 개찰 뒤 7일까지 5분·그 뒤 3시간(2026-11-26).
개찰 결과를 받은 뒤(opened, 낙찰 대기)는 3시간 5분 → 24시간까지 30분 → 3시간. 60일 뒤 끝.
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
def test_opened_table(after, expected):
    assert next_check(OPEN, OPEN + after, "opened") == expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (timedelta(hours=-1), OPEN),
        (timedelta(minutes=10), OPEN + timedelta(minutes=15)),
        (timedelta(hours=5), OPEN + timedelta(hours=5, minutes=5)),  # 3시간 뒤에도 5분
        (timedelta(hours=30), OPEN + timedelta(hours=30, minutes=5)),  # 하루 뒤에도 5분
        (timedelta(days=6, hours=23), OPEN + timedelta(days=6, hours=23, minutes=5)),
        (timedelta(days=8), OPEN + timedelta(days=8, hours=3)),  # 7일 지나면 3시간
        (timedelta(days=61), None),
    ],
)
def test_waiting_table(after, expected):
    assert next_check(OPEN, OPEN + after, "waiting") == expected


def test_boundaries():
    """3시간·24시간·7일 경계는 다음 구간 간격, 60일째까지는 확인한다."""
    assert next_check(OPEN, OPEN + timedelta(hours=3), "opened") == OPEN + timedelta(
        hours=3, minutes=30
    )
    assert next_check(OPEN, OPEN + timedelta(hours=24), "opened") == OPEN + timedelta(hours=27)
    assert next_check(OPEN, OPEN + timedelta(days=7), "waiting") == OPEN + timedelta(
        days=7, hours=3
    )
    assert next_check(OPEN, OPEN + timedelta(days=60), "waiting") is not None
    assert next_check(OPEN, OPEN + timedelta(days=60), "opened") is not None
