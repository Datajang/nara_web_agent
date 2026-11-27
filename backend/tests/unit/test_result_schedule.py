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


# ---------- 협상 공고 (2026-11-27, docs/decisions/2026-11-27-proposal-eval-date.md) ----------
EVAL = OPEN + timedelta(days=8, hours=-1)  # 개찰 8일 뒤 평가 시작


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (timedelta(hours=1), EVAL),  # 개찰 뒤라도 평가 전에는 부르지 않음
        (timedelta(days=7, hours=22), EVAL),
        (timedelta(days=7, hours=23), EVAL + timedelta(minutes=5)),  # 평가 시작부터 5분
        (timedelta(days=8, hours=22), OPEN + timedelta(days=8, hours=22, minutes=5)),  # 23시간째
        (timedelta(days=8, hours=23), OPEN + timedelta(days=8, hours=26)),  # 24시간 지나면 3시간
        (timedelta(days=61), OPEN + timedelta(days=61, hours=3)),  # 60일은 평가 시작부터 센다
        (timedelta(days=69), None),
    ],
)
def test_negotiated_with_eval_date(after, expected):
    assert next_check(OPEN, OPEN + after, "waiting", eval_at=EVAL, negotiated=True) == expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (timedelta(hours=-1), OPEN),
        (timedelta(minutes=10), OPEN + timedelta(minutes=40)),  # 평가일 모르면 30분
        (timedelta(days=20), OPEN + timedelta(days=20, minutes=30)),
        (timedelta(days=61), None),
    ],
)
def test_negotiated_without_eval_date(after, expected):
    assert next_check(OPEN, OPEN + after, "waiting", negotiated=True) == expected


def test_negotiated_opened_keeps_opened_schedule():
    """개찰 결과를 받은 뒤(낙찰 대기)는 협상이어도 지금 간격."""
    at = OPEN + timedelta(hours=30)
    assert next_check(OPEN, at, "opened", eval_at=EVAL, negotiated=True) == at + timedelta(hours=3)


def test_eval_date_ignored_when_not_negotiated():
    at = OPEN + timedelta(hours=1)
    assert next_check(OPEN, at, "waiting", eval_at=EVAL) == at + timedelta(minutes=5)
