"""수집 창 분할. 끝은 배타적이라 이웃 창이 경계를 공유하지 않는다 (알려진 문제 #2)."""

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
MINUTE = timedelta(minutes=1)


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


def kst_midnight(dt: datetime) -> datetime:
    """dt가 속한 KST 날짜의 0시 (같은 시간대 정보로)."""
    local = dt.astimezone(KST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt.tzinfo)


def split_dates(
    start: datetime, end: datetime, max_dates: int, newest_first: bool = False
) -> list[tuple[datetime, datetime]]:
    """[start, end)를 KST 날짜 max_dates개 이하로 자른다. 요청은 '끝 - 1분'까지라 그 날짜로 센다.

    낙찰·계약 API는 조회 시작일과 종료일의 날짜 차가 7일 이상이면 resultCode 07이다(분 길이와 무관,
    docs/decisions/2026-11-16-awards-probe.md).
    newest_first면 end에서 과거로 잘라 최신 창이 온전하다.
    """
    span = timedelta(days=max_dates - 1)
    out: list[tuple[datetime, datetime]] = []
    if newest_first:
        cur = end
        while cur > start:
            prev = max(start, kst_midnight(cur - MINUTE) - span)
            out.append((prev, cur))
            cur = prev
        return out
    cur = start
    while cur < end:
        nxt = min(end, kst_midnight(cur) + span + timedelta(days=1))
        out.append((cur, nxt))
        cur = nxt
    return out
