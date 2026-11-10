"""G2B 응답 파싱용 순수 함수.

v1 `nara_server/g2b_api.py`에서 네트워크 호출 없는 부분만 옮겼다.
HTTP 클라이언트(페이지네이션·오류 처리)는 P1에서 SPEC §5.2에 맞춰 새로 쓴다.
"""

from datetime import datetime, timedelta

G2B_DT_FORMAT = "%Y%m%d%H%M"

# docs/g2b/API.md: 응답에 섞여 나오는 날짜 형식 4종.
# "%Y%m%d"를 "%Y%m%d%H%M"보다 먼저 시도한다. 반대 순서면 strptime이 "20261116"을
# 2026-01-01 01:06으로 읽어 진행중 공고를 마감으로 판정한다(v1 버그).
_DEADLINE_FORMATS = ("%Y%m%d", "%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def get_date_range(days: int = 7) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime(G2B_DT_FORMAT), end.strftime(G2B_DT_FORMAT)


def get_date_chunks(days: int, chunk_size: int = 15) -> list[tuple[str, str]]:
    """조회 기간을 chunk_size일 단위로 자른다 (약 15일 초과 구간은 G2B가 404).

    알려진 문제 #2: 경계 시각이 앞뒤 청크에 공유된다. P1에서 bid_key upsert로 해소.
    """
    end = datetime.now()
    start = end - timedelta(days=days)
    chunks = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=chunk_size), end)
        chunks.append((chunk_start.strftime(G2B_DT_FORMAT), chunk_end.strftime(G2B_DT_FORMAT)))
        chunk_start = chunk_end
    return chunks


def is_bid_open(close_dt: str | None) -> bool:
    """마감 전이면 True.

    SPEC §4: 마감이 비었거나 해석할 수 없으면 '마감 미정'이며 진행중(True)으로 본다.
    """
    if not close_dt:
        return True
    for fmt in _DEADLINE_FORMATS:
        try:
            return datetime.strptime(close_dt.strip(), fmt) > datetime.now()
        except ValueError:
            continue
    return True


def parse_items(data: dict) -> list[dict]:
    """`response.body.items`의 세 가지 모양(list, {"item": ...}, "null")을 목록으로 정규화."""
    try:
        if data["response"]["header"]["resultCode"] not in ("00",):
            return []
        items = data["response"]["body"].get("items") or {}
        if isinstance(items, list):
            return items
        if isinstance(items, dict):
            raw = items.get("item")
            if not raw:
                return []
            return raw if isinstance(raw, list) else [raw]
        return []
    except (KeyError, TypeError):
        return []
