"""결과 감시 확인 간격 (설계 2026-11-25, 결과 대기 5분 2026-11-26, 협상 공고 2026-11-27).

개찰 전에는 부르지 않는다. 개찰 결과 대기(waiting):
- 그 외 공고: 개찰 뒤 7일까지 5분·그 뒤 3시간(개찰이 미뤄진 공고가 하루 몫 3,000회를 계속 쓰지 않게)
- 협상 공고(결과가 제안서평가 뒤 — 개찰 뒤 중앙값 8일,
  docs/decisions/2026-11-27-proposal-eval-date.md)
  - 평가 일시를 알면 그때까지 부르지 않고, 평가 시작부터 24시간은 5분·그 뒤 3시간
  - 모르면(수요기관 자체 평가·웹 실패) 30분
개찰 결과를 받은 뒤(opened, 낙찰 대기)는 개찰 뒤 3시간은 5분·24시간까지 30분·그 뒤 3시간.
어느 쪽이든 개찰(협상 평가 일시를 알면 평가) 60일 뒤 그만.
"""

from __future__ import annotations

from datetime import datetime, timedelta

WATCH_MAX_AGE = timedelta(days=7)  # 개찰이 이보다 오래 지난 공고는 감시를 새로 만들지 않는다
GIVE_UP = timedelta(days=60)
RENOTICE_DAYS = 30  # 유찰 뒤 재공고를 DB에서 찾는 기간
Steps = tuple[tuple[timedelta, timedelta], ...]  # (이 나이 전까지, 이 간격)
_WAITING_STEPS: Steps = ((timedelta(days=7), timedelta(minutes=5)),)
_EVAL_STEPS: Steps = ((timedelta(hours=24), timedelta(minutes=5)),)
_NEGOTIATED_NO_DATE = timedelta(minutes=30)
_OPENED_STEPS: Steps = (
    (timedelta(hours=3), timedelta(minutes=5)),
    (timedelta(hours=24), timedelta(minutes=30)),
)
_LAST = timedelta(hours=3)


def next_check(
    opening_at: datetime,
    now: datetime,
    stage: str,
    *,
    eval_at: datetime | None = None,
    negotiated: bool = False,
) -> datetime | None:
    """다음 확인 시각. None이면 그만. stage는 감시 단계(waiting·opened)."""
    waiting_nego = stage == "waiting" and negotiated
    start = max(opening_at, eval_at) if waiting_nego and eval_at is not None else opening_at
    if now < start:
        return start
    age = now - start
    if age > GIVE_UP:
        return None
    if waiting_nego and eval_at is None:
        return now + _NEGOTIATED_NO_DATE
    steps: Steps
    if stage == "opened":
        steps = _OPENED_STEPS
    else:
        steps = _EVAL_STEPS if waiting_nego else _WAITING_STEPS
    for limit, step in steps:
        if age < limit:
            return now + step
    return now + _LAST
