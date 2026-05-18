import httpx
from datetime import datetime, timedelta
from typing import Optional
from app.config import settings

BID_BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
PRESPEC_BASE = "http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"


def get_date_range(days: int = 7) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    fmt = "%Y%m%d%H%M"
    return start.strftime(fmt), end.strftime(fmt)


def get_date_chunks(days: int, chunk_size: int = 15) -> list[tuple[str, str]]:
    end = datetime.now()
    start = end - timedelta(days=days)
    chunks = []
    chunk_start = start
    while chunk_start < end:
        chunk_end = min(chunk_start + timedelta(days=chunk_size), end)
        chunks.append((chunk_start.strftime("%Y%m%d%H%M"), chunk_end.strftime("%Y%m%d%H%M")))
        chunk_start = chunk_end
    return chunks


def is_bid_open(close_dt: Optional[str]) -> bool:
    if not close_dt:
        return False
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d"):
        try:
            return datetime.strptime(close_dt.strip(), fmt) > datetime.now()
        except ValueError:
            continue
    return False


def _parse_items(data: dict) -> list[dict]:
    try:
        if data["response"]["header"]["resultCode"] not in ("00",):
            return []
        item = data["response"]["body"].get("items", {})
        if not item:
            return []
        raw = item.get("item") if isinstance(item, dict) else None
        if not raw:
            return []
        return raw if isinstance(raw, list) else [raw]
    except (KeyError, TypeError):
        return []


async def search_bids(keyword: str, days: int = 7) -> list[dict]:
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for start, end in get_date_chunks(days):
            params = {
                "ServiceKey": settings.nara_api_key,
                "type": "json",
                "inqryDiv": "1",
                "bidNtceNm": keyword,
                "inqryBgnDt": start,
                "inqryEndDt": end,
                "numOfRows": "30",
                "pageNo": "1",
            }
            try:
                resp = await client.get(
                    f"{BID_BASE}/getBidPblancListInfoServcPPSSrch", params=params
                )
                results.extend(_parse_items(resp.json()))
            except Exception:
                pass
    return results


async def search_prespec(keyword: str, days: int = 7) -> list[dict]:
    start, end = get_date_range(days)
    params = {
        "ServiceKey": settings.nara_prespec_api_key,
        "type": "json",
        "inqryDiv": "1",
        "prdctClsfcNoNm": keyword,
        "inqryBgnDt": start,
        "inqryEndDt": end,
        "numOfRows": "30",
        "pageNo": "1",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"{PRESPEC_BASE}/getPublicPrcureThngInfoServcPPSSrch", params=params
            )
            return _parse_items(resp.json())
        except Exception:
            return []
