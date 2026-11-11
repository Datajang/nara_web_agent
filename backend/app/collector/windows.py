"""수집 창 분할. 끝은 배타적이라 이웃 창이 경계를 공유하지 않는다 (알려진 문제 #2)."""

from datetime import datetime, timedelta


def split_windows(
    start: datetime, end: datetime, step: timedelta, newest_first: bool = False
) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    cur = start
    while cur < end:
        nxt = min(cur + step, end)
        out.append((cur, nxt))
        cur = nxt
    return out[::-1] if newest_first else out
