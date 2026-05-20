import httpx
from datetime import datetime, timedelta
from typing import Optional
from app.config import settings

BID_BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
PRESPEC_BASE = "http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
EORDER_ENDPOINT = "getBidPblancListInfoEorderAtchFileInfo"


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
        return True
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d"):
        try:
            return datetime.strptime(close_dt.strip(), fmt) > datetime.now()
        except ValueError:
            continue
    return True


def _parse_items(data: dict) -> list[dict]:
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


async def fetch_eorder_files(bid_no: str) -> list[tuple[str, str]]:
    """e-발주 첨부파일 조회. 제안요청 관련 파일만 반환."""
    params = {
        "ServiceKey": settings.nara_api_key,
        "type": "json",
        "inqryDiv": "2",
        "bidNtceNo": bid_no,
        "numOfRows": "10",
        "pageNo": "1",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"{BID_BASE}/{EORDER_ENDPOINT}", params=params)
            items = _parse_items(resp.json())
            result = []
            for it in items:
                fname = it.get("eorderAtchFileNm", "")
                furl = it.get("eorderAtchFileUrl", "")
                doc_div = it.get("eorderDocDivNm", "")
                if fname and furl and ("제안요청" in doc_div or "제안요청" in fname):
                    result.append((furl, fname))
            return result
        except Exception:
            return []


async def search_prespec(keyword: str, days: int = 7) -> list[dict]:
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for start, end in get_date_chunks(days):
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
            try:
                resp = await client.get(
                    f"{PRESPEC_BASE}/getPublicPrcureThngInfoServcPPSSrch", params=params
                )
                results.extend(_parse_items(resp.json()))
            except Exception:
                pass
    return results
