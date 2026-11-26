"""결과 감시 확인 간격 (설계 2026-11-25, 결과 대기 5분은 2026-11-26).

개찰 전에는 부르지 않는다. 개찰 결과 대기(waiting)는 개찰 뒤 7일까지 5분·그 뒤 3시간
(개찰이 미뤄진 공고가 하루 몫 3,000회를 계속 쓰지 않게). 개찰 결과를 받은 뒤(opened, 낙찰 대기)는
개찰 뒤 3시간은 5분·24시간까지 30분·그 뒤 3시간. 어느 쪽이든 개찰 60일 뒤 그만.
"""

from __future__ import annotations

from datetime import datetime, timedelta

WATCH_MAX_AGE = timedelta(days=7)  # 개찰이 이보다 오래 지난 공고는 감시를 새로 만들지 않는다
GIVE_UP = timedelta(days=60)
RENOTICE_DAYS = 30  # 유찰 뒤 재공고를 DB에서 찾는 기간
_WAITING_STEPS = ((timedelta(days=7), timedelta(minutes=5)),)
_OPENED_STEPS = (
    (timedelta(hours=3), timedelta(minutes=5)),
    (timedelta(hours=24), timedelta(minutes=30)),
)
_LAST = timedelta(hours=3)


def next_check(opening_at: datetime, now: datetime, stage: str) -> datetime | None:
    """다음 확인 시각. None이면 그만(개찰 60일 지남). stage는 감시 단계(waiting·opened)."""
    if now < opening_at:
        return opening_at
    age = now - opening_at
    if age > GIVE_UP:
        return None
    for limit, step in _OPENED_STEPS if stage == "opened" else _WAITING_STEPS:
        if age < limit:
            return now + step
    return now + _LAST
